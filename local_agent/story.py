from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from agent.planner.planner import PlanRequest, build_plan
from agent.postproduction import soundbox
from agent.postproduction.assemble import assemble_clips
from agent.postproduction.narration import synthesize_narration
from agent.providers.base import GenerationResult, VideoProvider
from agent.providers.simulated import SimulatedProvider
from agent.providers.taaft import TaaftProvider
from agent.scenes.spec import CharacterSpec
from agent.validation.validator import assert_valid, validate_clip

DEFAULT_SCRIPT = """The lighthouse had been dark for forty years when Mara climbed the cliff stairs.
Wind tore at her coat, but the tower door opened without a sound.
Inside, the spiral steps were warm, as if the lamp had just been lit.
At the top she found a mirror where the lens should have been.
In the mirror, the sea was perfectly calm and the sky was wrong.
Her own reflection pointed back toward the shore, where every window had gone dark.
Mara ran down before she decided to, her breath loud in the narrow stair.
When she reached the beach, the tide had walked far out, waiting.
She looked once at the mirror sea, then turned the great brass crank.
The beam swung wide across the water, and the light came home."""

SFX_PROMPT = (
    "dark eerie forest ambience at night, distant wind, low ominous drone, "
    "occasional rustling branches, horror atmosphere, seamless loop"
)

WAIT_RETRY_ATTEMPTS = 3
WAIT_RETRY_BACKOFF_SECONDS = 10.0
SESSION_RETRY_ATTEMPTS = 3
SESSION_RETRY_BACKOFF_SECONDS = 15.0
FATAL_PAGE_MARKERS = ("target closed", "browser has been closed", "page.goto", "err_connection", "net::")


@dataclass
class StoryConfig:
    work_dir: Path = field(default_factory=lambda: Path("local_work/story"))
    provider: str = "simulated"
    tier: str = "fast"
    orientation: str = "landscape"
    headless: bool = False
    profile_dir: Path = field(default_factory=lambda: Path(".taaft_chrome_profile"))
    title: str = "The Lighthouse Mirror"
    script: str = DEFAULT_SCRIPT
    style: str = "cinematic photorealistic short film, 35mm lens, moody coastal lighting"
    genre: str | None = "mystery"
    scene_count: int = 5
    scene_seconds: int = 8
    width: int = 1280
    height: int = 720
    clip_seconds: float = 8.0

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir)


def fmt_ts(seconds: float, comma: bool = True) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    ms = int(round((seconds - int(seconds)) * 1000)) % 1000
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{ms:03d}"


def _build_provider(config: StoryConfig) -> VideoProvider:
    if config.provider == "taaft":
        return TaaftProvider(
            enabled=os.environ.get("TAAFT_LOCAL_ENABLED", "0") == "1" or os.environ.get("TAAFT_ENABLED", "0") in {"1", "true"},
            profile_dir=config.profile_dir if config.profile_dir.exists() else None,
            headless=config.headless,
            poll_seconds=20,
            job_timeout_seconds=3600,
            tier=config.tier,
            orientation=config.orientation,
        )
    return SimulatedProvider(
        cache_dir=config.work_dir / "provider_cache",
        generation_seconds=1.0,
        clip_seconds=config.clip_seconds,
    )


def _jobs_path(config: StoryConfig) -> Path:
    return config.work_dir / "jobs.json"


def _load_jobs(config: StoryConfig) -> dict[str, str]:
    path = _jobs_path(config)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_job(config: StoryConfig, scene_number: int, job_id: str) -> None:
    jobs = _load_jobs(config)
    jobs[str(scene_number)] = job_id
    _jobs_path(config).write_text(json.dumps(jobs, indent=2), encoding="utf-8")


async def _wait_with_retry(provider: VideoProvider, generation_id: str) -> GenerationResult:
    last_error: Exception | None = None
    for attempt in range(1, WAIT_RETRY_ATTEMPTS + 1):
        try:
            return await _poll_until_terminal(provider, generation_id)
        except Exception as error:
            message = str(error).lower()
            if any(marker in message for marker in FATAL_PAGE_MARKERS):
                raise
            last_error = error
            print(f"    [wait] attempt {attempt}/{WAIT_RETRY_ATTEMPTS} failed: {error}", flush=True)
            await asyncio.sleep(WAIT_RETRY_BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"Generation {generation_id} did not finish: {last_error}")


async def _poll_until_terminal(provider: VideoProvider, generation_id: str) -> GenerationResult:
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline:
        result = await provider.get_generation_status(generation_id)
        if result.terminal:
            return result
        await asyncio.sleep(10)
    raise RuntimeError(f"Timed out waiting for generation {generation_id}")


class StoryRunner:
    def __init__(self, config: StoryConfig) -> None:
        self.config = config
        self.work = config.work_dir
        self.report: dict = {"scenes": [], "started": time.time()}

    def build_plan(self):
        characters = [
            CharacterSpec(
                name="Mara",
                description="a weathered lighthouse keeper's daughter in her thirties, short dark hair, grey wool coat",
            )
        ]
        plan = build_plan(
            PlanRequest(
                title=self.config.title,
                script=self.config.script,
                style=self.config.style,
                scene_count=self.config.scene_count,
                scene_seconds=self.config.scene_seconds,
                target_duration_seconds=self.config.scene_count * self.config.scene_seconds,
                orientation=self.config.orientation,
                genre=self.config.genre,
                characters=characters,
                provider="deterministic",
            )
        )
        plan_path = self.work / "plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        self.report["plan"] = {
            "title": plan.title,
            "scenes": len(plan.scenes),
            "duration": plan.total_duration(),
        }
        return plan

    async def generate_stage(self, plan) -> None:
        provider = _build_provider(self.config)
        if self.config.provider != "taaft":
            await self._generate_scenes(plan, provider)
            return
        for attempt in range(1, SESSION_RETRY_ATTEMPTS + 1):
            try:
                await asyncio.to_thread(self._generate_scenes_taaft_sync, plan, provider)
                return
            except Exception as error:
                print(f"[taaft] session attempt {attempt}/{SESSION_RETRY_ATTEMPTS} failed: {error}", flush=True)
                if attempt >= SESSION_RETRY_ATTEMPTS:
                    raise
                await asyncio.sleep(SESSION_RETRY_BACKOFF_SECONDS * attempt)

    def _generate_scenes_taaft_sync(self, plan, provider: TaaftProvider) -> None:
        from agent.providers.taaft import GEN_URL

        with provider.session():
            account = provider._sync_verify()
            print(f"[taaft] account: {account.get('account_id')} ({account.get('status')})", flush=True)
            jobs = _load_jobs(self.config)
            for scene in plan.scenes:
                clip = self.work / f"scene_{scene.scene_number:02d}.mp4"
                if clip.exists() and validate_clip(clip)["passed"]:
                    print(f"[scene {scene.scene_number}/{len(plan.scenes)}] clip exists, skipping", flush=True)
                    self.report["scenes"].append({"scene": scene.scene_number, "clip": str(clip), "resumed": True})
                    continue
                job_id = jobs.get(str(scene.scene_number))
                if job_id:
                    print(f"[scene {scene.scene_number}/{len(plan.scenes)}] adopting saved job {job_id}", flush=True)
                else:
                    print(f"[scene {scene.scene_number}/{len(plan.scenes)}] submitting to TAAFT...", flush=True)
                    raw = provider._sync_submit(scene.prompt, self.config.tier, self.config.orientation, None)
                    job_id = str(raw.get("id"))
                    _save_job(self.config, scene.scene_number, job_id)
                    print(f"[scene {scene.scene_number}/{len(plan.scenes)}] job {job_id} ({raw.get('status')})", flush=True)
                generation = provider._sync_status(job_id, True)
                video_url = generation.get("video_url")
                if not video_url:
                    raise RuntimeError(f"Scene {scene.scene_number} finished without a video URL")
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                    "Referer": GEN_URL,
                }
                response = requests.get(video_url, headers=headers, timeout=180)
                response.raise_for_status()
                clip.write_bytes(response.content)
                if clip.stat().st_size == 0:
                    raise RuntimeError(f"Scene {scene.scene_number} download was empty")
                validation = validate_clip(clip)
                self.report["scenes"].append(
                    {
                        "scene": scene.scene_number,
                        "job_id": job_id,
                        "clip": str(clip),
                        "clip_valid": validation["passed"],
                    }
                )
                print(f"[scene {scene.scene_number}/{len(plan.scenes)}] downloaded {clip.name} valid={validation['passed']}", flush=True)

    async def _generate_scenes(self, plan, provider: VideoProvider) -> None:
        jobs = _load_jobs(self.config)
        for scene in plan.scenes:
            clip = self.work / f"scene_{scene.scene_number:02d}.mp4"
            if clip.exists() and validate_clip(clip)["passed"]:
                print(f"[scene {scene.scene_number}/{len(plan.scenes)}] clip exists, skipping", flush=True)
                self.report["scenes"].append({"scene": scene.scene_number, "clip": str(clip), "resumed": True})
                continue
            job_id = jobs.get(str(scene.scene_number))
            if job_id:
                print(f"[scene {scene.scene_number}/{len(plan.scenes)}] adopting saved job {job_id}", flush=True)
                result = await _wait_with_retry(provider, job_id)
            else:
                print(f"[scene {scene.scene_number}/{len(plan.scenes)}] submitting ({self.config.provider})...", flush=True)
                submitted = await provider.submit_generation(
                    prompt=scene.prompt,
                    tier=self.config.tier,
                    orientation=self.config.orientation,
                    duration=scene.duration,
                    idempotency_key=f"story-{self.config.title.replace(' ', '-').lower()}-{scene.scene_number}",
                )
                job_id = submitted.generation_id
                _save_job(self.config, scene.scene_number, job_id)
                print(f"[scene {scene.scene_number}/{len(plan.scenes)}] job {job_id} ({submitted.status})", flush=True)
                if submitted.terminal and not submitted.failed and submitted.video_url:
                    result = submitted
                elif submitted.failed:
                    raise RuntimeError(f"Scene {scene.scene_number} submission failed: {submitted.error}")
                else:
                    result = await _wait_with_retry(provider, job_id)
            if result.failed or not result.video_url:
                raise RuntimeError(f"Scene {scene.scene_number} did not finish: {result.status} {result.error}")
            await provider.download_generation(result, clip)
            validation = validate_clip(clip)
            self.report["scenes"].append(
                {
                    "scene": scene.scene_number,
                    "job_id": job_id,
                    "clip": str(clip),
                    "clip_valid": validation["passed"],
                    "mode": result.mode,
                }
            )
            print(f"[scene {scene.scene_number}/{len(plan.scenes)}] downloaded {clip.name} valid={validation['passed']}", flush=True)

    def make_narration(self, plan) -> tuple[Path | None, list[dict]]:
        import numpy as np
        import soundfile as sf

        segments: list[dict] = []
        parts: list = []
        cursor = 0.0
        for scene in plan.scenes:
            if not scene.narration.strip():
                continue
            wav = self.work / f"narr_{scene.scene_number:02d}.wav"
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
        voiceover = self.work / "voiceover.wav"
        sf.write(voiceover, np.concatenate(parts), 24000)
        return voiceover, segments

    def make_ambience(self) -> Path | None:
        try:
            soundbox.health()
        except Exception:
            self.report["soundbox"] = {"available": False}
            print("[soundbox] app not reachable, skipping ambience", flush=True)
            return None
        self.report["soundbox"] = {"available": True}
        try:
            out = soundbox.generate_clip(SFX_PROMPT, self.work / "ambience.wav", duration_s=10.0)
            self.report["soundbox"]["generated"] = str(out)
            print(f"[soundbox] ambience -> {out.name}", flush=True)
            return out
        except Exception as error:
            self.report["soundbox"]["error"] = str(error)[:300]
            print(f"[soundbox] generation skipped: {error}", flush=True)
            return None

    def make_subtitles(self, segments: list[dict]) -> tuple[Path | None, Path | None]:
        if not segments:
            return None, None
        srt = self.work / "story.srt"
        lines: list[str] = []
        for index, seg in enumerate(segments, start=1):
            lines += [str(index), f"{fmt_ts(seg['start'])} --> {fmt_ts(seg['end'])}", seg["text"].strip(), ""]
        srt.write_text("\n".join(lines), encoding="utf-8")
        from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg

        vtt = self.work / "story.vtt"
        run_ffmpeg([find_ffmpeg(), "-y", "-i", str(srt), str(vtt)])
        print(f"[subtitles] srt + vtt written", flush=True)
        return srt, vtt

    def post_stage(self, plan) -> None:
        voiceover, segments = self.make_narration(plan)
        self.report["kokoro"] = {"voiceover": str(voiceover) if voiceover else None, "segments": len(segments)}
        ambience = self.make_ambience()
        clips = [self.work / f"scene_{scene.scene_number:02d}.mp4" for scene in plan.scenes]
        missing = [clip for clip in clips if not clip.exists()]
        if missing:
            raise RuntimeError(f"Missing clips for post stage: {missing}")
        assembly = assemble_clips(
            clips,
            self.work,
            width=self.config.width,
            height=self.config.height,
            fps=24.0,
            transition="fade",
            music_path=ambience,
            voiceover_path=voiceover,
        )
        print(f"[assemble] final -> {assembly.final_path.name} expected={assembly.expected_duration:.2f}s", flush=True)
        srt, vtt = self.make_subtitles(segments)
        self.report["subtitles"] = {"srt": str(srt) if srt else None, "vtt": str(vtt) if vtt else None}
        final_report = assert_valid(
            assembly.final_path,
            expected_scene_count=len(plan.scenes),
            expected_duration=assembly.expected_duration,
            expected_width=self.config.width,
            expected_height=self.config.height,
            thumbnail_path=assembly.thumbnail_path,
        )
        self.report["validation"] = {
            "passed": final_report["passed"],
            "checks": len(final_report["checks"]),
            "errors": final_report["errors"],
        }
        self.report["final"] = {
            "video": str(assembly.final_path),
            "size_bytes": final_report["size_bytes"],
            "checksum": final_report["checksum_sha256"][:16],
            "metadata": final_report["metadata"],
            "thumbnail": str(assembly.thumbnail_path) if assembly.thumbnail_path else None,
        }

    async def run(self, stage: str) -> dict:
        self.work.mkdir(parents=True, exist_ok=True)
        plan = self.build_plan()
        print(f"[planner] {plan.title}: {len(plan.scenes)} scenes", flush=True)
        if stage in {"generate", "all"}:
            await self.generate_stage(plan)
        if stage in {"post", "all"}:
            self.post_stage(plan)
        self.report["provider"] = self.config.provider
        self.report["elapsed_seconds"] = round(time.time() - self.report["started"], 1)
        (self.work / "report.json").write_text(json.dumps(self.report, indent=2, default=str), encoding="utf-8")
        print(json.dumps({k: self.report[k] for k in ("validation", "final", "elapsed_seconds") if k in self.report}, indent=2, default=str))
        return self.report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m local_agent.story",
        description="Generate a short story video end to end: plan -> provider clips -> narration -> ambience -> assembly -> subtitles -> validation.",
    )
    parser.add_argument("--provider", choices=["taaft", "simulated"], default=os.environ.get("STORY_PROVIDER", "simulated"))
    parser.add_argument("--stage", choices=["generate", "post", "all"], default="all")
    parser.add_argument("--work-dir", default=os.environ.get("STORY_WORK_DIR", "local_work/story"))
    parser.add_argument("--scenes", type=int, default=5)
    parser.add_argument("--scene-seconds", type=int, default=8)
    parser.add_argument("--title", default="The Lighthouse Mirror")
    parser.add_argument("--script-file", default=None, help="Path to a text file with the story script")
    parser.add_argument("--tier", choices=["fast", "quality"], default="fast")
    parser.add_argument("--headless", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> int:
    script = DEFAULT_SCRIPT
    if args.script_file:
        script = Path(args.script_file).read_text(encoding="utf-8")
    config = StoryConfig(
        work_dir=Path(args.work_dir),
        provider=args.provider,
        tier=args.tier,
        headless=args.headless,
        title=args.title,
        script=script,
        scene_count=args.scenes,
        scene_seconds=args.scene_seconds,
    )
    runner = StoryRunner(config)
    await runner.run(args.stage)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Story run interrupted; re-run the same command to resume.", flush=True)
        return 1
    except Exception as error:
        print(f"Story run failed: {error}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
