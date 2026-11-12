from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent.core.util import extract_thumbnail, probe_video
from agent.postproduction.ffmpeg_tools import (
    concat_normalized,
    concat_with_crossfade,
    mix_audio,
    normalize_clip,
)


@dataclass
class AssemblyResult:
    final_path: Path
    thumbnail_path: Path | None
    expected_duration: float
    probes: list[dict] = field(default_factory=list)


def assemble_clips(
    clip_paths: list[Path],
    work_dir: Path,
    *,
    width: int,
    height: int,
    fps: float = 24.0,
    transition: str = "none",
    music_path: Path | None = None,
    voiceover_path: Path | None = None,
) -> AssemblyResult:
    """Shared assembly pipeline used by cloud workers and the local agent."""
    if not clip_paths:
        raise ValueError("No clips to assemble")
    work_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[Path] = []
    probes: list[dict] = []
    for index, clip in enumerate(clip_paths, start=1):
        target = work_dir / f"norm_{index:03d}.mp4"
        normalize_clip(clip, target, width=width, height=height, fps=fps)
        normalized.append(target)
        probes.append(probe_video(target))

    concat_target = work_dir / "concat.mp4"
    if transition in {"fade", "crossfade"} and len(normalized) > 1:
        try:
            concat_with_crossfade(normalized, concat_target, transition_seconds=0.4)
        except Exception:
            concat_normalized(normalized, concat_target)
    else:
        concat_normalized(normalized, concat_target)

    final_path = concat_target
    if (music_path and music_path.exists()) or (voiceover_path and voiceover_path.exists()):
        mixed = work_dir / "mixed.mp4"
        final_path = mix_audio(
            concat_target,
            mixed,
            music_path=music_path if music_path and music_path.exists() else None,
            voiceover_path=voiceover_path if voiceover_path and voiceover_path.exists() else None,
        )

    thumbnail = work_dir / "thumbnail.jpg"
    try:
        extract_thumbnail(final_path, thumbnail, at_seconds=1.0)
    except Exception:
        thumbnail = None  # type: ignore[assignment]

    expected_duration = sum(float(probe.get("duration") or 0) for probe in probes)
    return AssemblyResult(
        final_path=final_path,
        thumbnail_path=thumbnail,
        expected_duration=expected_duration,
        probes=probes,
    )
