from __future__ import annotations

import os
from pathlib import Path

from agent.core.errors import ProviderDisabledError, ProcessingError

DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "a"
DEFAULT_SAMPLE_RATE = 24000


def narration_enabled() -> bool:
    return os.environ.get("KOKORO_ENABLED", "0") == "1"


def synthesize_narration(
    text: str,
    output_path: Path,
    *,
    voice: str | None = None,
    lang: str | None = None,
    speed: float = 1.0,
) -> Path:
    """Generate English narration audio with the local Kokoro TTS model."""
    if not narration_enabled():
        raise ProviderDisabledError("Kokoro narration is disabled (KOKORO_ENABLED=0)")
    if not text.strip():
        raise ProcessingError("Narration text is empty")
    import soundfile as sf
    from kokoro import KPipeline

    pipeline = KPipeline(
        lang_code=lang or os.environ.get("KOKORO_LANG", DEFAULT_LANG),
        repo_id=os.environ.get("KOKORO_REPO", "hexgrad/Kokoro-82M"),
    )
    audio_parts = []
    for _gs, _ps, audio in pipeline(
        text,
        voice=voice or os.environ.get("KOKORO_VOICE", DEFAULT_VOICE),
        speed=speed,
    ):
        audio_parts.append(audio)
    if not audio_parts:
        raise ProcessingError("Kokoro produced no audio")
    import numpy as np

    combined = np.concatenate(audio_parts) if len(audio_parts) > 1 else audio_parts[0]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, combined, DEFAULT_SAMPLE_RATE)
    return output_path


def synthesize_fit(
    text: str,
    output_path: Path,
    *,
    target_seconds: float,
    voice: str | None = None,
    lang: str | None = None,
    min_speed: float = 0.85,
    max_speed: float = 1.15,
) -> tuple[Path, float, float]:
    """Synthesize narration auto-fit to a target window.

    Generates at speed 1.0, and if the audio overruns the target, regenerates
    with an adjusted speed clamped to [min_speed, max_speed]. Returns
    (path, actual_duration, speed_used).
    """
    import soundfile as sf

    def _duration(path: Path) -> float:
        audio, rate = sf.read(path)
        return len(audio) / rate

    synthesize_narration(text, output_path, voice=voice, lang=lang, speed=1.0)
    duration = _duration(output_path)
    speed_used = 1.0
    if duration > target_seconds:
        needed = duration / max(0.1, target_seconds)
        speed_used = min(max_speed, max(min_speed, needed))
        if duration / speed_used > target_seconds * 1.02:
            synthesize_narration(text, output_path, voice=voice, lang=lang, speed=speed_used)
            duration = _duration(output_path)
    return output_path, duration, speed_used
