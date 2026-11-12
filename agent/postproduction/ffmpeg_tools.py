from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from agent.core.errors import ProcessingError
from agent.core.util import probe_video, redact


def find_ffmpeg() -> str:
    env = os.environ.get("FFMPEG_PATH")
    if env and Path(env).exists():
        return env
    try:
        import imageio_ffmpeg

        candidate = imageio_ffmpeg.get_ffmpeg_exe()
        if candidate and Path(candidate).exists():
            return candidate
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    return found or "ffmpeg"


def run_ffmpeg(command: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise ProcessingError(f"FFmpeg failed: {redact(result.stderr[-3000:])}")
    return result


def normalize_clip(
    source: Path,
    destination: Path,
    *,
    width: int,
    height: int,
    fps: float = 24.0,
    has_audio: bool | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    probe = probe_video(source)
    if has_audio is None:
        has_audio = bool(probe.get("has_audio"))
    duration = probe.get("duration") or 1.0
    scale = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )
    command = [find_ffmpeg(), "-y", "-i", str(source)]
    if has_audio:
        command += [
            "-filter_complex",
            f"[0:v]{scale}[v];[0:a]aresample=48000,aformat=channel_layouts=stereo[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
        ]
    else:
        command += [
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=48000",
            "-filter_complex",
            f"[0:v]{scale}[v]",
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-shortest",
        ]
    command += [
        "-t",
        f"{max(0.5, float(duration)):.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    run_ffmpeg(command)
    if not destination.exists() or destination.stat().st_size == 0:
        raise ProcessingError(f"Normalized clip is empty: {destination}")
    return destination


def concat_normalized(paths: list[Path], destination: Path) -> Path:
    if not paths:
        raise ProcessingError("No clips to concatenate")
    destination.parent.mkdir(parents=True, exist_ok=True)
    concat_list = destination.parent / f"{destination.stem}_concat.txt"
    lines = []
    for path in paths:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
    command = [
        find_ffmpeg(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not destination.exists() or destination.stat().st_size == 0:
        command = [
            find_ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        run_ffmpeg(command)
    return destination


def concat_with_crossfade(paths: list[Path], destination: Path, transition_seconds: float = 0.5) -> Path:
    if len(paths) < 2:
        return concat_normalized(paths, destination)
    probes = [probe_video(path) for path in paths]
    durations = [float(probe.get("duration") or 1.0) for probe in probes]
    transition_seconds = max(0.1, min(transition_seconds, min(durations) / 3))
    command = [find_ffmpeg(), "-y"]
    for path in paths:
        command += ["-i", str(path)]
    filter_parts = []
    previous_video = "0:v"
    previous_audio = "0:a"
    cumulative = durations[0]
    for index in range(1, len(paths)):
        offset = max(0.0, cumulative - transition_seconds)
        out_video = f"v{index}"
        out_audio = f"a{index}"
        filter_parts.append(
            f"[{previous_video}][{index}:v]xfade=transition=fade:duration={transition_seconds:.3f}:"
            f"offset={offset:.3f}[{out_video}]"
        )
        filter_parts.append(
            f"[{previous_audio}][{index}:a]acrossfade=d={transition_seconds:.3f}[{out_audio}]"
        )
        previous_video = out_video
        previous_audio = out_audio
        cumulative += durations[index] - transition_seconds
    command += [
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        f"[{previous_video}]",
        "-map",
        f"[{previous_audio}]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    run_ffmpeg(command)
    return destination


def mix_audio(
    video: Path,
    destination: Path,
    *,
    music_path: Path | None = None,
    voiceover_path: Path | None = None,
    music_volume: float = 0.25,
) -> Path:
    if music_path is None and voiceover_path is None:
        shutil.copyfile(video, destination)
        return destination
    command = [find_ffmpeg(), "-y", "-i", str(video)]
    filter_parts = []
    inputs = 1
    audio_map = "0:a"
    if voiceover_path and voiceover_path.exists():
        command += ["-i", str(voiceover_path)]
        filter_parts.append(f"[{inputs}:a]volume=1.0[vo]")
        inputs += 1
        audio_map = "[mixvo]"
        base = "0:a"
        filter_parts.append(f"[{base}][vo]amix=inputs=2:duration=first:dropout_transition=2[mixvo]")
    if music_path and music_path.exists():
        command += ["-stream_loop", "-1", "-i", str(music_path)]
        filter_parts.append(f"[{inputs}:a]volume={music_volume}[music]")
        inputs += 1
        if audio_map == "[mixvo]":
            filter_parts.append("[mixvo][music]amix=inputs=2:duration=first:dropout_transition=2[mixfinal]")
        else:
            filter_parts.append("[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[mixfinal]")
        audio_map = "[mixfinal]"
    command += ["-filter_complex", ";".join(filter_parts), "-map", "0:v", "-map", audio_map]
    command += [
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    run_ffmpeg(command)
    return destination
