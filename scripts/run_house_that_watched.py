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

import numpy as np
import requests
import soundfile as sf

from agent.postproduction import soundbox
from agent.postproduction.assemble import assemble_clips
from agent.postproduction.narration import synthesize_narration
from agent.providers.taaft import GEN_URL, TaaftProvider
from agent.scenes.spec import ScenePlan
from agent.validation.validator import assert_valid, validate_clip

PLAN_PATH = Path("stories/house_that_watched/plan.json")
WORK = Path("local_work/house_that_watched")

AMBIENCE_PROMPT = (
    "abandoned Victorian house interior ambience, creaking wooden floorboards, "
    "cold wind through broken windows, distant thunder, low ominous drone, "
    "tape hiss, horror atmosphere, seamless loop"
)


def fmt_ts(seconds: float, comma: bool = True) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    ms = int(round((seconds - int(seconds)) * 1000)) % 1000
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{ms:03d}"


def load_jobs() -> dict[str, str]:
    path = WORK / "jobs.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_job(scene_number: int, job_id: str) -> None:
    jobs = load_jobs()
    jobs[str(scene_number)] = job_id
    (WORK / "jobs.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")


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


def make_narration(plan: ScenePlan) -> tuple[Path | None, list[dict]]:
    segments: list[dict] = []
    parts: list = []
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
        parts.append(np.zeros(int(rate * 0.6), dtype=audio.dtype))
        cursor += duration + 0.6
        print(f"[narration] scene {scene.scene_number}: {duration:.2f}s", flush=True)
    if not parts:
        return None, segments
    voiceover = WORK / "voiceover.wav"
    sf.write(voiceover, np.concatenate(parts), 24000)
    return voiceover, segments


def make_ambience(report: dict) -> Path | None:
    if not start_soundbox():
        report["soundbox"] = {"available": False}
        print("[soundbox] app not reachable, skipping ambience", flush=True)
        return None
    report["soundbox"] = {"available": True}
    try:
        out = soundbox.generate_clip(AMBIENCE_PROMPT, WORK / "ambience.wav", duration_s=10.0)
        report["soundbox"]["generated"] = str(out)
        print(f"[soundbox] ambience -> {out.name}", flush=True)
        return out
    except Exception as error:
        report["soundbox"]["error"] = str(error)[:300]
        print(f"[soundbox] generation skipped: {error}", flush=True)
        return None


def make_subtitles(segments: list[dict]) -> tuple[Path | None, Path | None]:
    if not segments:
        return None, None
    srt = WORK / "story.srt"
    lines: list[str] = []
    for index, seg in enumerate(segments, start=1):
        lines += [str(index), f"{fmt_ts(seg['start'])} --> {fmt_ts(seg['end'])}", seg["text"].strip(), ""]
    srt.write_text("\n".join(lines), encoding="utf-8")
    from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg

    vtt = WORK / "story.vtt"
    run_ffmpeg([find_ffmpeg(), "-y", "-i", str(srt), str(vtt)])
    print("[subtitles] srt + vtt written", flush=True)
    return srt, vtt


async def main() -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    plan = ScenePlan.model_validate_json(PLAN_PATH.read_text(encoding="utf-8"))
    (WORK / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    report: dict = {
        "plan": {"title": plan.title, "scenes": len(plan.scenes), "duration": plan.total_duration()},
        "orientation": plan.orientation,
        "scenes": [],
        "started": time.time(),
    }
    print(f"[planner] {plan.title}: {len(plan.scenes)} scenes ({plan.orientation})", flush=True)

    provider = TaaftProvider(
        enabled=True,
        profile_dir=Path(".taaft_chrome_profile"),
        headless=False,
        poll_seconds=20,
        job_timeout_seconds=3600,
        tier="quality",
        orientation=plan.orientation,
    )

    jobs = load_jobs()
    for scene in plan.scenes:
        clip = WORK / f"scene_{scene.scene_number:02d}.mp4"
        if clip.exists() and validate_clip(clip)["passed"]:
            print(f"[scene {scene.scene_number}/{len(plan.scenes)}] clip exists, skipping", flush=True)
            report["scenes"].append({"scene": scene.scene_number, "clip": str(clip), "resumed": True})
            continue
        job_id = jobs.get(str(scene.scene_number))
        final = None
        if job_id:
            print(f"[scene {scene.scene_number}/{len(plan.scenes)}] adopting saved job {job_id}", flush=True)
            try:
                final = await provider.wait_for_generation(job_id)
            except Exception as error:
                print(f"[scene {scene.scene_number}] saved job unusable ({error}); resubmitting", flush=True)
                job_id = None
        if final is None:
            print(f"[scene {scene.scene_number}/{len(plan.scenes)}] submitting to TAAFT ({plan.orientation})...", flush=True)
            result = await provider.submit_generation(
                prompt=scene.prompt,
                tier="quality",
                orientation=plan.orientation,
                duration=scene.duration,
                idempotency_key=f"house-{scene.scene_number}",
            )
            job_id = result.generation_id
            save_job(scene.scene_number, job_id)
            print(f"[scene {scene.scene_number}/{len(plan.scenes)}] job {job_id} ({result.status})", flush=True)
            final = await provider.wait_for_generation(job_id)
        if final.status not in {"succeeded", "success", "completed"} or not final.video_url:
            raise RuntimeError(f"Scene {scene.scene_number} did not finish: {final.status} {final.error}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
            "Referer": GEN_URL,
        }
        response = requests.get(final.video_url, headers=headers, timeout=180)
        response.raise_for_status()
        clip.write_bytes(response.content)
        if clip.stat().st_size == 0:
            raise RuntimeError(f"Scene {scene.scene_number} download was empty")
        validation = validate_clip(clip)
        report["scenes"].append(
            {
                "scene": scene.scene_number,
                "title": scene.title,
                "job_id": job_id,
                "clip": str(clip),
                "clip_valid": validation["passed"],
            }
        )
        print(f"[scene {scene.scene_number}/{len(plan.scenes)}] downloaded {clip.name} valid={validation['passed']}", flush=True)

    voiceover, segments = make_narration(plan)
    report["kokoro"] = {"voiceover": str(voiceover) if voiceover else None, "segments": len(segments)}

    ambience = make_ambience(report)

    assembly = assemble_clips(
        [WORK / f"scene_{s.scene_number:02d}.mp4" for s in plan.scenes],
        WORK,
        width=720,
        height=1280,
        fps=24.0,
        transition="fade",
        music_path=ambience,
        voiceover_path=voiceover,
    )
    print(f"[assemble] final -> {assembly.final_path.name} expected={assembly.expected_duration:.2f}s", flush=True)

    srt, vtt = make_subtitles(segments)
    report["subtitles"] = {"srt": str(srt) if srt else None, "vtt": str(vtt) if vtt else None}

    final_report = assert_valid(
        assembly.final_path,
        expected_scene_count=len(plan.scenes),
        expected_duration=assembly.expected_duration,
        expected_width=720,
        expected_height=1280,
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
    report["provider"] = "taaft (real, persistent chrome profile)"
    report["elapsed_seconds"] = round(time.time() - report["started"], 1)
    (WORK / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["validation", "final", "elapsed_seconds"]}, indent=2, default=str))
    return report


if __name__ == "__main__":
    asyncio.run(main())
