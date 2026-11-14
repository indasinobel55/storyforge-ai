from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("KOKORO_ENABLED", "1")
os.environ.setdefault("SOUNDBOX_ENABLED", "1")

from agent.planner.planner import PlanRequest, build_plan
from agent.postproduction import soundbox
from agent.postproduction.assemble import assemble_clips
from agent.postproduction.narration import synthesize_narration
from agent.providers.simulated import SimulatedProvider
from agent.scenes.spec import CharacterSpec
from agent.validation.validator import assert_valid, validate_clip

WORK = Path("local_work/story5_test")
SFX_PROMPT = (
    "dark eerie forest ambience at night, distant wind, low ominous drone, "
    "occasional rustling branches, horror atmosphere, seamless loop"
)

SCRIPT_TEXT = """The lighthouse had been dark for forty years when Mara climbed the cliff stairs.
Wind tore at her coat, but the tower door opened without a sound.
Inside, the spiral steps were warm, as if the lamp had just been lit.
At the top she found a mirror where the lens should have been.
In the mirror, the sea was perfectly calm and the sky was wrong.
Her own reflection pointed back toward the shore, where every window had gone dark.
Mara ran down before she decided to, her breath loud in the narrow stair.
When she reached the beach, the tide had walked far out, waiting.
She looked once at the mirror sea, then turned the great brass crank.
The beam swung wide across the water, and the light came home."""


def fmt_ts(seconds: float, comma: bool = True) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    ms = int(round((seconds - int(seconds)) * 1000)) % 1000
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{ms:03d}"


def start_soundbox() -> bool:
    try:
        soundbox.health()
        return True
    except Exception:
        pass
    exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Soundbox" / "soundbox-desktop.exe"
    if not exe.exists():
        return False
    subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(6):
        time.sleep(3)
        try:
            soundbox.health()
            return True
        except Exception:
            continue
    return False


async def generate_scenes(plan, provider, report) -> list[Path]:
    clips: list[Path] = []
    for scene in plan.scenes:
        result = await provider.submit_generation(
            prompt=scene.prompt,
            tier="standard",
            orientation=plan.orientation,
            duration=scene.duration,
            idempotency_key=f"story5-{scene.scene_number}",
        )
        for _ in range(120):
            status = await provider.get_generation_status(result.generation_id)
            if status.status in {"succeeded", "success", "completed"}:
                break
            if status.status == "failed":
                raise RuntimeError(f"Scene {scene.scene_number} generation failed: {status.error}")
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError(f"Scene {scene.scene_number} timed out")
        destination = WORK / f"scene_{scene.scene_number:02d}.mp4"
        await provider.download_generation(status, destination)
        validation = validate_clip(destination)
        clips.append(destination)
        report["scenes"].append(
            {
                "scene": scene.scene_number,
                "title": scene.title,
                "clip": str(destination),
                "clip_valid": validation["passed"],
                "prompt": scene.prompt[:80] + "...",
            }
        )
        print(f"[scene {scene.scene_number}/5] rendered -> {destination.name} valid={validation['passed']}")
    return clips


def make_narration(plan) -> tuple[Path | None, list[dict]]:
    segments: list[dict] = []
    voiceover = WORK / "voiceover.wav"
    import numpy as np
    import soundfile as sf

    parts: list[np.ndarray] = []
    cursor = 0.0
    for scene in plan.scenes:
        if not scene.narration.strip():
            continue
        wav = WORK / f"narr_{scene.scene_number:02d}.wav"
        synthesize_narration(scene.narration, wav, speed=1.0)
        audio, rate = sf.read(wav)
        duration = len(audio) / rate
        segments.append({"start": cursor, "end": cursor + duration, "text": scene.narration})
        parts.append(audio)
        gap = np.zeros(int(rate * 0.6), dtype=audio.dtype)
        parts.append(gap)
        cursor += duration + 0.6
        print(f"[narration] scene {scene.scene_number}: {duration:.2f}s")
    if not parts:
        return None, segments
    sf.write(voiceover, np.concatenate(parts), 24000)
    return voiceover, segments


def make_ambience(report) -> Path | None:
    if not start_soundbox():
        report["soundbox"] = {"available": False, "note": "Soundbox app not reachable on port 17494"}
        return None
    report["soundbox"] = {"available": True, "health": soundbox.health()}
    try:
        out = soundbox.generate_clip(SFX_PROMPT, WORK / "ambience.wav", duration_s=10.0)
        report["soundbox"]["generated"] = str(out)
        print(f"[soundbox] ambience generated -> {out.name}")
        return out
    except Exception as exc:
        report["soundbox"]["generated"] = False
        report["soundbox"]["error"] = str(exc)[:300]
        print(f"[soundbox] generation skipped: {exc}")
        return None


def make_subtitles(segments: list[dict]) -> tuple[Path, Path | None]:
    srt = WORK / "story.srt"
    lines: list[str] = []
    for index, seg in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{fmt_ts(seg['start'])} --> {fmt_ts(seg['end'])}")
        lines.append(seg["text"].strip())
        lines.append("")
    srt.write_text("\n".join(lines), encoding="utf-8")
    vtt = WORK / "story.vtt"
    from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg

    run_ffmpeg([find_ffmpeg(), "-y", "-i", str(srt), str(vtt)])
    ok = vtt.exists() and vtt.stat().st_size > 0
    print(f"[subtitles] srt written; vtt conversion via ffmpeg: {'ok' if ok else 'failed'}")
    return srt, vtt if ok else None


async def main() -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    report: dict = {"scenes": [], "started": time.time()}

    plan = build_plan(
        PlanRequest(
            title="The Lighthouse Mirror",
            script=SCRIPT_TEXT,
            style="cinematic photorealistic short film, 35mm lens, moody coastal lighting",
            scene_count=5,
            scene_seconds=8,
            target_duration_seconds=40,
            genre="mystery",
            characters=[
                CharacterSpec(
                    name="Mara",
                    description="a weathered lighthouse keeper's daughter in her thirties, short dark hair, grey wool coat",
                )
            ],
            provider="deterministic",
        )
    )
    report["plan"] = {
        "title": plan.title,
        "scenes": len(plan.scenes),
        "duration": plan.total_duration(),
        "provider": plan.provider,
    }
    print(f"[planner] {plan.title}: {len(plan.scenes)} scenes, {plan.total_duration():.0f}s")

    provider = SimulatedProvider(cache_dir=WORK / "provider_cache", generation_seconds=1.0, clip_seconds=8.0)
    clips = await generate_scenes(plan, provider, report)

    report["ffmpeg"] = {"source": "winget Gyan.FFmpeg 9.0.2 (on PATH)"}

    voiceover, segments = make_narration(plan)
    report["kokoro"] = {"voiceover": str(voiceover) if voiceover else None, "segments": len(segments)}
    print(f"[kokoro] voiceover ready ({len(segments)} segments)")

    ambience = make_ambience(report)

    assembly = assemble_clips(
        clips,
        WORK,
        width=1280,
        height=720,
        fps=24.0,
        transition="fade",
        music_path=ambience,
        voiceover_path=voiceover,
    )
    print(f"[assemble] final -> {assembly.final_path.name} expected={assembly.expected_duration:.2f}s")

    srt, vtt = make_subtitles(segments)
    report["subtitles"] = {"srt": str(srt), "vtt": str(vtt) if vtt else None, "note": "Subtitle Edit 5.4 is GUI-only (no headless CLI); automated conversion done with FFmpeg"}
    report["subtitle_edit"] = {
        "installed": Path(os.environ.get("SUBTITLE_EDIT_PATH", r"C:\Program Files\Subtitle Edit\SubtitleEdit.exe")).exists(),
        "headless_cli": False,
        "role": "manual GUI tool for sync/styling/speech-to-text",
    }

    final_report = assert_valid(
        assembly.final_path,
        expected_scene_count=len(plan.scenes),
        expected_duration=assembly.expected_duration,
        expected_width=1280,
        expected_height=720,
        thumbnail_path=assembly.thumbnail_path,
    )
    report["validation"] = {"passed": final_report["passed"], "checks": len(final_report["checks"]), "errors": final_report["errors"]}
    report["final"] = {
        "video": str(assembly.final_path),
        "size_bytes": final_report["size_bytes"],
        "checksum": final_report["checksum_sha256"][:16],
        "metadata": final_report["metadata"],
        "thumbnail": str(assembly.thumbnail_path) if assembly.thumbnail_path else None,
    }
    report["tool_status"] = {
        "1_kokoro": bool(voiceover),
        "2_soundbox": bool(report.get("soundbox", {}).get("generated")),
        "3_ffmpeg": True,
        "4_youtube_mcp": "publish-capable (setup pending OAuth, not part of video render)",
        "5_subtitle_edit": bool(report.get("subtitle_edit", {}).get("installed")),
    }
    report["elapsed_seconds"] = round(time.time() - report["started"], 1)
    (WORK / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["tool_status", "validation", "elapsed_seconds"]}, indent=2))
    return report


if __name__ == "__main__":
    asyncio.run(main())
