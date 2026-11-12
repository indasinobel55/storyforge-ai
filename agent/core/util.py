from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import av


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(text: str, fallback: str = "video") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return value[:64] or fallback


def redact(text: str) -> str:
    return re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[redacted-email]", text or "")


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", normalize_text(text))
    return [part.strip() for part in parts if part.strip()]


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(temp, path)


def extract_json_object(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object found")
    candidate = value[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        try:
            from json_repair import loads as repair_loads  # optional

            repaired = repair_loads(candidate)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_video(path: Path) -> dict[str, Any]:
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError(f"No video stream in {path}")
        video = container.streams.video[0]
        audio_streams = list(container.streams.audio)
        duration = None
        if container.duration is not None:
            duration = float(container.duration / av.time_base)
        fps = None
        if video.average_rate:
            fps = float(video.average_rate)
        return {
            "width": int(video.codec_context.width),
            "height": int(video.codec_context.height),
            "fps": fps,
            "has_audio": bool(audio_streams),
            "duration": duration,
            "codec": video.codec_context.name,
        }


def extract_last_frame(video_path: Path, image_path: Path) -> Path:
    image_path.parent.mkdir(parents=True, exist_ok=True)
    last_frame = None
    with av.open(str(video_path)) as container:
        for frame in container.decode(video=0):
            last_frame = frame
    if last_frame is None:
        raise ValueError(f"No decodable video frames in {video_path}")
    image = last_frame.to_image()
    image.save(image_path)
    return image_path


def extract_thumbnail(video_path: Path, image_path: Path, at_seconds: float = 1.0) -> Path:
    from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg

    image_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            find_ffmpeg(),
            "-y",
            "-ss",
            str(max(0.0, at_seconds)),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(image_path),
        ]
    )
    return image_path
