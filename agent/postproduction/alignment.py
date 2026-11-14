from __future__ import annotations

import os
from pathlib import Path

from agent.core.errors import ProcessingError

MAX_CUE_SECONDS = 4.5
MAX_CUE_CHARS = 84
SENTENCE_BREAKS = (".", "!", "?", "...")


def transcribe_words(audio_path: Path, *, model_size: str | None = None) -> list[dict]:
    """Word-level timestamps for a narration track via faster-whisper."""
    import torch
    from faster_whisper import WhisperModel

    size = model_size or os.environ.get("WHISPER_MODEL", "base")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = WhisperModel(size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        str(audio_path),
        language="en",
        word_timestamps=True,
        vad_filter=False,
        beam_size=1,
    )
    words: list[dict] = []
    for segment in segments:
        for word in segment.words or []:
            tokens = (word.word or "").strip().split()
            if not tokens:
                continue
            words.append(
                {
                    "start": float(word.start),
                    "end": float(word.end),
                    "word": (word.word or "").strip(),
                }
            )
    if not words:
        raise ProcessingError("Whisper alignment produced no words")
    return words


def build_cues(words: list[dict], *, max_seconds: float = MAX_CUE_SECONDS, max_chars: int = MAX_CUE_CHARS) -> list[dict]:
    """Group word timestamps into subtitle cues at sentence/clause boundaries."""
    cues: list[dict] = []
    current: list[dict] = []
    current_chars = 0

    def _flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        text = " ".join(item["word"] for item in current).strip()
        text = text.replace(" ,", ",").replace(" .", ".").replace(" !", "!").replace(" ?", "?")
        cues.append(
            {
                "start": current[0]["start"],
                "end": current[-1]["end"],
                "text": text,
            }
        )
        current = []
        current_chars = 0

    for index, word in enumerate(words):
        current.append(word)
        current_chars += len(word["word"]) + 1
        is_last = index == len(words) - 1
        ends_sentence = word["word"].endswith(SENTENCE_BREAKS)
        span = word["end"] - current[0]["start"]
        pause_after = False
        if not is_last:
            pause_after = words[index + 1]["start"] - word["end"] > 0.45
        if ends_sentence or is_last or span >= max_seconds or current_chars >= max_chars:
            if pause_after or ends_sentence or span >= max_seconds or current_chars >= max_chars or is_last:
                _flush()
    return cues


def write_srt(cues: list[dict], destination: Path) -> Path:
    def _ts(seconds: float) -> str:
        total = max(0, int(round(seconds)))
        hours, rem = divmod(total, 3600)
        minutes, secs = divmod(rem, 60)
        ms = int(round((seconds - int(seconds)) * 1000)) % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        lines += [str(index), f"{_ts(cue['start'])} --> {_ts(cue['end'])}", cue["text"], ""]
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination
