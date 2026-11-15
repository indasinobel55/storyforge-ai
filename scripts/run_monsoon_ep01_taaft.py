"""Real TAAFT generation for THE CHILD OF THE MONSOON - Episode 01.

Pipeline:
  1. Park the simulated clips (they are NOT real footage).
  2. Adopt the already-done scene 1 from TAAFT history if it exists, else submit it.
  3. Generate scenes 2-8 with native extend chaining (last-frame reference fallback).
  4. Normalize every TAAFT clip (864x480) to 1280x720 @ 24fps, exactly 8s.
  5. Hand off to run_monsoon_ep01_full.py --skip-generate for 4x enhancement + assembly.

Run from anywhere:
    python scripts/run_monsoon_ep01_taaft.py

Options:
    --skip-enhance-assemble   only generate + normalize the scenes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SOUNDBOX_ENABLED", "1")

from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg
from agent.providers.taaft import TaaftProvider
from agent.validation.validator import validate_clip

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORK = PROJECT_ROOT / "local_work" / "child_of_the_monsoon" / "ep01"
PLAN_PATH = PROJECT_ROOT / "stories" / "child_of_the_monsoon" / "ep01" / "plan.json"
FULL_PIPELINE = PROJECT_ROOT / "scripts" / "run_monsoon_ep01_full.py"

# Scene-1 prompt markers used to recognize the already-submitted generation
# in the TAAFT history (prompts are submitted verbatim from plan.json).
SCENE_1_MARKERS = ("SCENE 1 of 8 - MONSOON EXPEDITION FILM", "unexplored Amazon rainforest")

TERMINAL_OK = {"succeeded", "success", "completed"}


def log(msg: str) -> None:
    print(msg, flush=True)


def park_simulated_outputs() -> None:
    """Move simulated artifacts aside so only real TAAFT footage remains."""
    backup = WORK / "_simulated_backup"
    backup.mkdir(exist_ok=True)
    moved = []
    for pattern in ("scene_*.mp4", "norm_*.mp4", "concat.mp4", "mixed.mp4",
                    "frame_*.png", "thumbnail.jpg", "jobs.json", "report.json"):
        for f in WORK.glob(pattern):
            shutil.move(str(f), backup / f.name)
            moved.append(f.name)
    enhanced = WORK / "enhanced"
    if enhanced.exists():
        shutil.rmtree(enhanced)
    cache = WORK / "provider_cache"
    if cache.exists():
        shutil.rmtree(cache)
    if moved:
        log(f"[park] moved simulated artifacts -> _simulated_backup: {', '.join(moved)}")
    else:
        log("[park] no simulated artifacts found")


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


def extract_last_frame(clip: Path, image: Path) -> Path:
    image.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [find_ffmpeg(), "-y", "-sseof", "-0.5", "-i", str(clip),
         "-frames:v", "1", "-update", "1", str(image)]
    )
    if not image.exists() or image.stat().st_size == 0:
        raise RuntimeError(f"Last frame extraction failed: {clip}")
    return image


def normalize_clip(src: Path, dst: Path) -> Path:
    """TAAFT quality tier renders ~864x480; upscale to 720p, exact 8s, no audio."""
    run_ffmpeg(
        [
            find_ffmpeg(), "-y", "-i", str(src),
            "-vf",
            "scale=1280:720:flags=lanczos,setsar=1,fps=24,"
            "tpad=stop_mode=clone:stop_duration=8",
            "-t", "8", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", str(dst),
        ]
    )
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"Normalization failed: {src}")
    return dst


def scrape_history(provider: TaaftProvider) -> list[dict]:
    """Return [{id, text}] for every generation listed in the TAAFT history."""
    with provider.session() as page:
        items = page.eval_on_selector_all(
            "[data-videogen-generation-id]",
            "els => els.map(e => ({id: e.getAttribute('data-videogen-generation-id'),"
            " text: (e.innerText || '')}));",
        )
    return [i for i in items if i.get("id")]


async def adopt_scene_1(provider: TaaftProvider) -> tuple[str | None, str | None]:
    """Find the already-done scene 1 generation in TAAFT history.

    Returns (job_id, video_url) when a completed matching generation exists.
    """
    try:
        history = await asyncio.to_thread(scrape_history, provider)
    except Exception as error:
        log(f"[adopt] history scrape failed ({str(error)[:150]}); will submit fresh")
        return None, None
    log(f"[adopt] {len(history)} generations in TAAFT history")
    for item in history:
        text = item.get("text") or ""
        if not any(marker in text for marker in SCENE_1_MARKERS):
            continue
        job_id = item["id"]
        log(f"[adopt] candidate {job_id} matches scene 1 markers")
        try:
            status = await provider.get_generation_status(job_id)
        except Exception as error:
            log(f"[adopt] status check failed for {job_id}: {str(error)[:150]}")
            continue
        if status.status in TERMINAL_OK and status.video_url:
            log(f"[adopt] job {job_id} is completed -> adopting")
            return job_id, status.video_url
        log(f"[adopt] job {job_id} status={status.status} (not completed); skipping")
    return None, None


async def wait_download_normalize(
    provider: TaaftProvider, job_id: str, index: int, report: dict
) -> Path:
    raw_clip = WORK / f"scene_{index:02d}_raw.mp4"
    clip = WORK / f"scene_{index:02d}.mp4"
    t0 = time.time()
    final = await provider.wait_for_generation(job_id)
    if final.status not in TERMINAL_OK or not final.video_url:
        raise RuntimeError(f"Scene {index} did not finish: {final.status} {final.error}")
    await provider.download_generation(final, raw_clip)
    normalize_clip(raw_clip, clip)
    raw_clip.unlink(missing_ok=True)
    validation = validate_clip(clip)
    log(
        f"[scene {index}/8] TAAFT clip ready: {clip.name} "
        f"({clip.stat().st_size/1e6:.1f} MB, valid={validation['passed']}, {time.time()-t0:.0f}s)"
    )
    report["scenes"].append(
        {
            "scene": index,
            "title": report["titles"][index - 1],
            "job_id": job_id,
            "clip": str(clip),
            "clip_valid": validation["passed"],
            "mode": final.mode,
        }
    )
    return clip


async def generate_all() -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    report: dict = {
        "plan": {"title": plan["title"], "scenes": len(plan["scenes"])},
        "titles": [s["title"] for s in plan["scenes"]],
        "scenes": [],
        "started": time.time(),
    }
    log(f"[plan] {plan['title']}: {len(plan['scenes'])} scenes (TAAFT real, quality, landscape)")

    provider = TaaftProvider(
        enabled=True,
        profile_dir=Path(".taaft_chrome_profile"),
        headless=False,  # Cloudflare trust needs the visible profile
        poll_seconds=20,
        job_timeout_seconds=3600,
        tier="quality",
        orientation="landscape",
    )

    jobs = load_jobs()
    prev_job: str | None = None
    prev_clip: Path | None = None

    # ---- scene 1: adopt the already-done generation, else submit fresh ----
    index = 1
    clip1 = WORK / "scene_01.mp4"
    job_id = jobs.get("1")
    if clip1.exists() and validate_clip(clip1)["passed"] and job_id:
        log(f"[scene 1/8] real clip already present (job {job_id}) -> skipping")
        prev_job = job_id
        prev_clip = clip1
        report["scenes"].append(
            {
                "scene": 1,
                "title": report["titles"][0],
                "job_id": job_id,
                "clip": str(clip1),
                "resumed": True,
            }
        )
    else:
        if not job_id:
            job_id, _url = await adopt_scene_1(provider)
            if job_id:
                save_job(1, job_id)
        if not job_id:
            log("[scene 1/8] submitting fresh to TAAFT (quality, landscape)...")
            result = await provider.submit_generation(
                prompt=plan["scenes"][0]["prompt"],
                tier="quality",
                orientation="landscape",
                duration=8.0,
                idempotency_key="monsoon-ep01-taaft-1",
            )
            job_id = result.generation_id
            save_job(1, job_id)
            log(f"[scene 1/8] job {job_id} ({result.status})")
        prev_job = job_id
        prev_clip = await wait_download_normalize(provider, job_id, index, report)

    # ---- scenes 2-8: native extend chaining, reference fallback ----
    for scene in plan["scenes"][1:]:
        index = scene["scene_number"]
        existing = WORK / f"scene_{index:02d}.mp4"
        if existing.exists() and validate_clip(existing)["passed"] and jobs.get(str(index)):
            log(f"[scene {index}/8] real clip already present (job {jobs[str(index)]}) -> skipping")
            prev_job = jobs[str(index)]
            prev_clip = existing
            report["scenes"].append(
                {
                    "scene": index,
                    "title": report["titles"][index - 1],
                    "job_id": prev_job,
                    "clip": str(existing),
                    "resumed": True,
                }
            )
            continue
        reference = extract_last_frame(prev_clip, WORK / f"frame_{index - 1:02d}.png")
        job_id = None
        if prev_job:
            log(f"[scene {index}/8] extending {prev_job} (native continuity)...")
            try:
                result = await provider.extend_generation(
                    parent_generation_id=prev_job,
                    prompt=scene["prompt"],
                    tier="quality",
                    orientation="landscape",
                    duration=8.0,
                    reference_image_path=reference,
                )
                job_id = result.generation_id
                save_job(index, job_id)
                log(f"[scene {index}/8] extend job {job_id} ({result.status}, mode={result.mode})")
            except Exception as error:
                log(f"[scene {index}/8] extend failed ({str(error)[:200]}); reference fallback")
                job_id = None
        if not job_id:
            log(f"[scene {index}/8] submitting with last-frame reference...")
            result = await provider.submit_generation(
                prompt=scene["prompt"],
                tier="quality",
                orientation="landscape",
                duration=8.0,
                reference_image_path=reference,
                idempotency_key=f"monsoon-ep01-taaft-{index}",
            )
            job_id = result.generation_id
            save_job(index, job_id)
            log(f"[scene {index}/8] job {job_id} ({result.status})")
        prev_job = job_id
        prev_clip = await wait_download_normalize(provider, job_id, index, report)

    report["provider"] = "taaft (real, persistent chrome profile)"
    report["elapsed_seconds"] = round(time.time() - report["started"], 1)
    (WORK / "report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    return report


def enhance_and_assemble() -> None:
    log("\n=== handing off to 4x enhancement + assembly ===")
    run = subprocess.run(
        [sys.executable, str(FULL_PIPELINE), "--skip-generate", "--keep-originals"],
        cwd=str(PROJECT_ROOT),
    )
    if run.returncode != 0:
        raise SystemExit(f"Enhancement/assembly pipeline failed (exit {run.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Child of the Monsoon EP01 - real TAAFT")
    parser.add_argument("--skip-enhance-assemble", action="store_true")
    args = parser.parse_args()

    t0 = time.time()
    park_simulated_outputs()
    asyncio.run(generate_all())
    if not args.skip_enhance_assemble:
        enhance_and_assemble()
    log(f"\nTotal elapsed: {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
