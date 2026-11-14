from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("KOKORO_ENABLED", "1")
os.environ.setdefault("SOUNDBOX_ENABLED", "1")

import test_story_5_scenes as base

from agent.planner.planner import PlanRequest, build_plan
from agent.providers.taaft import TaaftProvider
from agent.scenes.spec import CharacterSpec
from agent.validation.validator import assert_valid, validate_clip

WORK = Path("local_work/story5_taaft")
base.WORK = WORK


async def main() -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    report: dict = {"scenes": [], "started": time.time()}

    plan = build_plan(
        PlanRequest(
            title="The Lighthouse Mirror",
            script=base.SCRIPT_TEXT,
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
    report["plan"] = {"title": plan.title, "scenes": len(plan.scenes), "duration": plan.total_duration()}
    print(f"[planner] {plan.title}: {len(plan.scenes)} scenes", flush=True)

    provider = TaaftProvider(
        enabled=True,
        profile_dir=Path(".taaft_chrome_profile"),
        headless=False,
        poll_seconds=20,
        job_timeout_seconds=3600,
        tier="fast",
    )
    for scene in plan.scenes:
        clip = WORK / f"scene_{scene.scene_number:02d}.mp4"
        if clip.exists() and validate_clip(clip)["passed"]:
            print(f"[scene {scene.scene_number}/5] already generated, skipping", flush=True)
            report["scenes"].append({"scene": scene.scene_number, "clip": str(clip), "resumed": True})
            continue
        print(f"[scene {scene.scene_number}/5] submitting to TAAFT...", flush=True)
        result = await provider.submit_generation(
            prompt=scene.prompt,
            tier="fast",
            orientation="landscape",
            duration=scene.duration,
            idempotency_key=f"story5taaft-{scene.scene_number}",
        )
        print(f"[scene {scene.scene_number}/5] job {result.generation_id} ({result.status})", flush=True)
        final = await provider.wait_for_generation(result.generation_id)
        if final.status not in {"succeeded", "success", "completed"} or not final.video_url:
            raise RuntimeError(f"Scene {scene.scene_number} did not finish: {final.status}")
        await provider.download_generation(final, clip)
        validation = validate_clip(clip)
        report["scenes"].append(
            {
                "scene": scene.scene_number,
                "job_id": final.generation_id,
                "clip": str(clip),
                "clip_valid": validation["passed"],
                "mode": final.mode,
            }
        )
        print(f"[scene {scene.scene_number}/5] downloaded {clip.name} valid={validation['passed']}", flush=True)

    voiceover, segments = base.make_narration(plan)
    report["kokoro"] = {"voiceover": str(voiceover) if voiceover else None, "segments": len(segments)}
    print(f"[kokoro] voiceover ready ({len(segments)} segments)", flush=True)

    ambience = base.make_ambience(report)

    assembly = base.assemble_clips(
        [WORK / f"scene_{s.scene_number:02d}.mp4" for s in plan.scenes],
        WORK,
        width=1280,
        height=720,
        fps=24.0,
        transition="fade",
        music_path=ambience,
        voiceover_path=voiceover,
    )
    print(f"[assemble] final -> {assembly.final_path.name} expected={assembly.expected_duration:.2f}s", flush=True)

    srt, vtt = base.make_subtitles(segments)
    report["subtitles"] = {"srt": str(srt), "vtt": str(vtt) if vtt else None}

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
    report["provider"] = "taaft (real, persistent chrome profile)"
    report["tool_status"] = {
        "1_kokoro": bool(voiceover),
        "2_soundbox": bool(report.get("soundbox", {}).get("generated")),
        "3_ffmpeg": True,
        "4_youtube_mcp": "publish-capable (setup pending OAuth, not part of video render)",
        "5_subtitle_edit": bool(report.get("subtitle_edit", {}).get("installed")),
    }
    report["elapsed_seconds"] = round(time.time() - report["started"], 1)
    (WORK / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["tool_status", "validation", "elapsed_seconds", "final"]}, indent=2, default=str))
    return report


if __name__ == "__main__":
    asyncio.run(main())
