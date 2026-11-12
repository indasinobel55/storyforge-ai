"""The autonomous video pipeline.

One class, one entry point: parse a master prompt, generate every scene with
the configured provider, narrate it, compose the ambient sound design, apply
cinematic transitions, assemble, validate and write the final MP4 plus a full
run report. No API server, no UI, no manual approval gates.

Resumable: any scene whose clip already exists and validates is reused, so a
crashed run re-launches with ``resume=True`` and continues where it stopped.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent.core.errors import PlanningError
from agent.core.util import extract_last_frame, probe_video, sha256_file, slugify, write_json
from agent.postproduction.assemble import assemble_clips
from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg
from agent.providers.base import GenerationResult, VideoProvider
from agent.providers.registry import build_provider
from agent.providers.simulated import SimulatedProvider
from agent.providers.taaft import TaaftProvider
from agent.scenes.spec import ScenePlan
from agent.validation.validator import validate_clip, validate_final

from .masterprompt import parse_master_prompt_file
from .soundstage import build_scene_audio, mux_audio_onto_clip, narration_duration, synthesize_speech

TERMINAL_OK = {"succeeded", "success", "completed"}
MAX_SCENE_ATTEMPTS = 3
RESUME_SUFFIX = "_av.mp4"

RESOLUTION = {
    "landscape": (1280, 720),
    "portrait": (720, 1280),
    "square": (720, 720),
}


@dataclass
class AutonomousConfig:
    prompt_path: Path
    output_dir: Path | None = None
    provider: str = "simulated"
    tier: str = "quality"  # quality = TAAFT slow mode
    transition: str = "fade"  # fade | crossfade | none
    with_narration: bool = True
    narration_voice: str | None = None
    narration_rate: int = 1
    with_ambience: bool = True
    keep_clip_audio: bool = False
    resume: bool = True
    fps: float = 24.0
    orientation: str = "landscape"
    scene_seconds_override: float | None = None
    work_root: Path = field(default_factory=lambda: Path.cwd() / "outputs")
    simulated_generation_seconds: float = 1.0
    taaft_enabled: bool = field(default_factory=lambda: os.environ.get("TAAFT_LOCAL_ENABLED", "0") == "1")
    taaft_profile_dir: Path | None = field(
        default_factory=lambda: Path(os.environ["TAAFT_PROFILE"]) if os.environ.get("TAAFT_PROFILE") else Path.cwd() / ".taaft_chrome_profile"
    )
    taaft_headless: bool = field(default_factory=lambda: os.environ.get("TAAFT_HEADLESS", "0") == "1")
    taaft_poll_seconds: int = 20
    taaft_job_timeout_seconds: int = 3600
    taaft_enhance: bool = field(default_factory=lambda: os.environ.get("TAAFT_ENHANCE", "0") == "1")
    chrome_path: str | None = field(default_factory=lambda: os.environ.get("CHROME_PATH") or None)

    def __post_init__(self) -> None:
        self.prompt_path = Path(self.prompt_path)
        if self.output_dir is None:
            slug = slugify(self.prompt_path.stem, "film")
            if self.provider == "taaft":
                slug += "-taaft"
            self.output_dir = Path(self.work_root) / slug
        else:
            self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.tier not in {"fast", "quality"}:
            self.tier = "quality"
        if self.taaft_profile_dir is None:
            self.taaft_profile_dir = Path(
                os.environ.get("TAAFT_PROFILE") or (Path.cwd() / ".taaft_chrome_profile")
            )


@dataclass
class AutonomousResult:
    output_dir: Path
    plan: ScenePlan
    final_path: Path | None
    thumbnail_path: Path | None
    report_path: Path
    validation: dict
    duration: float | None
    matches_target: bool
    clip_paths: list[Path] = field(default_factory=list)


class AutonomousPipeline:
    def __init__(self, config: AutonomousConfig, log=None) -> None:
        self.config = config
        self.log = log or (lambda message: print(message, flush=True))
        self.output_dir = config.output_dir
        self.scenes_dir = self.output_dir / "scenes"
        self.audio_dir = self.output_dir / "audio"
        self.work_dir = self.output_dir / "_work"
        self._provider: VideoProvider | None = None

    # ------------------------------------------------------------------ setup

    def _provider_for(self) -> VideoProvider:
        if self.config.provider == "taaft":
            return TaaftProvider(
                enabled=self.config.taaft_enabled,
                profile_dir=self.config.taaft_profile_dir,
                chrome_path=self.config.chrome_path,
                headless=self.config.taaft_headless,
                poll_seconds=self.config.taaft_poll_seconds,
                job_timeout_seconds=self.config.taaft_job_timeout_seconds,
                enhance=self.config.taaft_enhance,
                tier=self.config.tier,
                orientation=self.config.orientation,
            )
        return build_provider(
            self.config.provider,
            cache_dir=self.output_dir / "_provider_cache",
            simulated_generation_seconds=self.config.simulated_generation_seconds,
            simulated_clip_seconds=self.config.scene_seconds_override or 8.0,
            taaft_enabled=False,
        )

    # ------------------------------------------------------------- main entry

    async def run(self) -> AutonomousResult:
        started = time.monotonic()
        self.log(f"[plan] parsing master prompt: {self.config.prompt_path}")
        document, plan = await asyncio.to_thread(parse_master_prompt_file, self.config.prompt_path)
        if self.config.scene_seconds_override:
            seconds = max(1.0, min(10.0, float(self.config.scene_seconds_override)))
            for scene in plan.scenes:
                scene.duration = seconds
        plan.target_duration_seconds = int(sum(scene.duration for scene in plan.scenes))
        self.log(
            f"[plan] '{plan.title}': {len(plan.scenes)} scenes x "
            f"{plan.scenes[0].duration:.0f}s, target {plan.target_duration_seconds}s"
        )
        plan_json = self.output_dir / "plan.json"
        write_json(plan_json, plan.model_dump())

        if self.config.provider == "taaft" and not self.config.taaft_enabled:
            raise PlanningError(
                "Real TAAFT automation needs explicit consent: set TAAFT_LOCAL_ENABLED=1 "
                "or pass --enable-taaft. Your own repo gate remains in place otherwise."
            )

        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        narration_on = self.config.with_narration
        ambience_on = self.config.with_ambience

        provider = await asyncio.to_thread(self._provider_for)
        self._provider = provider
        width, height = RESOLUTION.get(self.config.orientation, (1280, 720))

        scene_entries: list[dict] = []
        final_clips: list[Path] = []
        parent_generation_id: str | None = None
        reference_frame: Path | None = None

        for scene in sorted(plan.scenes, key=lambda item: item.scene_number):
            self.log(f"[scene {scene.scene_number:{len(str(len(plan.scenes)))}d}/{len(plan.scenes)}] '{scene.title}'")
            clip_path = self.scenes_dir / f"scene_{scene.scene_number:03d}.mp4"
            try:
                clip_path, generation_id = await self._ensure_scene_clip(
                    scene,
                    provider,
                    tier=self.config.tier,
                    parent_generation_id=parent_generation_id,
                    reference_image_path=reference_frame,
                )
            except Exception as error:  # noqa: BLE001
                self.log(f"[scene {scene.scene_number}] FAILED: {error}")
                raise
            self.log(f"[scene {scene.scene_number}] clip ready ({clip_path.name})")

            try:
                if narration_on or ambience_on:
                    clip_path = await self._apply_scene_sound(scene, clip_path)
            except Exception as error:  # noqa: BLE001
                if narration_on:
                    raise
                self.log(f"[scene {scene.scene_number}] ambience skipped: {error}")

            scene_entries.append(
                {
                    "scene_number": scene.scene_number,
                    "title": scene.title,
                    "clip": str(clip_path),
                    "generation_id": generation_id,
                    "probe": probe_video(clip_path),
                    "checksum_sha256": sha256_file(clip_path),
                }
            )
            final_clips.append(clip_path)

            if generation_id and not str(generation_id).startswith("resumed"):
                parent_generation_id = generation_id
            try:
                reference_frame = await asyncio.to_thread(
                    extract_last_frame,
                    clip_path,
                    self.work_dir / f"ref_{scene.scene_number:03d}.png",
                )
            except Exception as error:  # noqa: BLE001
                self.log(f"[scene {scene.scene_number}] reference frame unavailable: {error}")
                reference_frame = None

        transition = self.config.transition
        assembly_dir = self.work_dir / "assembly"
        if transition == "fade":
            final_clips = await asyncio.to_thread(self._apply_dip_to_black_fades, final_clips)
            assembly_transition = "none"
        else:
            assembly_transition = transition

        self.log("[assemble] assembling final cut...")
        result = await asyncio.to_thread(
            assemble_clips,
            final_clips,
            assembly_dir,
            width=width,
            height=height,
            fps=self.config.fps,
            transition=assembly_transition,
        )

        slug = slugify(plan.title, "film")
        final_path = self.output_dir / f"{slug}_final.mp4"
        thumbnail_path = self.output_dir / f"{slug}_thumbnail.jpg"
        if result.final_path != final_path:
            shutil.copyfile(result.final_path, final_path)
        if result.thumbnail_path and result.thumbnail_path.exists():
            shutil.copyfile(result.thumbnail_path, thumbnail_path)

        expected_duration = float(plan.target_duration_seconds)
        report = await asyncio.to_thread(
            validate_final,
            final_path,
            expected_scene_count=len(plan.scenes),
            expected_duration=result.expected_duration,
            expected_width=width,
            expected_height=height,
            thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
        )
        final_probe = probe_video(final_path)
        final_duration = float(final_probe.get("duration") or 0)
        tolerance = 3.0
        matches_target = (
            abs(final_duration - expected_duration) <= tolerance
            if transition in {"fade", "none"}
            else report["passed"]
        )

        narration_script = self.output_dir / "narration_script.txt"
        narration_script.write_text(self._narration_script_text(document, plan), encoding="utf-8")

        run_report = {
            "title": plan.title,
            "source_prompt": str(self.config.prompt_path),
            "provider": provider.name,
            "scene_count": len(plan.scenes),
            "scene_seconds": float(plan.scenes[0].duration),
            "target_duration_seconds": expected_duration,
            "final_duration_seconds": round(final_duration, 3),
            "matches_target": matches_target,
            "resolution": f"{width}x{height}",
            "fps": self.config.fps,
            "transition": self.config.transition,
            "narration_enabled": narration_on,
            "ambience_enabled": ambience_on,
            "final_path": str(final_path),
            "thumbnail_path": str(thumbnail_path) if thumbnail_path.exists() else None,
            "narration_script": str(narration_script),
            "checksum_sha256": report.get("checksum_sha256"),
            "size_bytes": report.get("size_bytes"),
            "validation_passed": report["passed"],
            "validation_errors": report.get("errors") or [],
            "scenes": scene_entries,
            "wall_seconds": round(time.monotonic() - started, 1),
        }
        report_path = self.output_dir / "report.json"
        write_json(report_path, run_report)

        shutil.rmtree(self.work_dir, ignore_errors=True)

        self.log(
            f"[done] {final_path}  "
            f"{final_duration:.1f}s (target {expected_duration:.0f}s)  "
            f"validation={'OK' if report['passed'] else 'FAILED'}"
        )
        if not report["passed"]:
            raise PlanningError("Final validation failed: " + "; ".join(report.get("errors") or []))

        return AutonomousResult(
            output_dir=self.output_dir,
            plan=plan,
            final_path=final_path,
            thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
            report_path=report_path,
            validation=report,
            duration=final_duration,
            matches_target=matches_target,
            clip_paths=final_clips,
        )

    # ------------------------------------------------------------ generation

    def _reusable_clip(self, clip_path: Path) -> bool:
        return self.config.resume and clip_path.exists() and validate_clip(clip_path)["passed"]

    async def _ensure_scene_clip(
        self,
        scene,
        provider: VideoProvider,
        *,
        tier: str,
        parent_generation_id: str | None = None,
        reference_image_path: Path | None = None,
    ) -> tuple[Path, str]:
        clip_path = self.scenes_dir / f"scene_{scene.scene_number:03d}.mp4"
        idempotency_key = f"autonomous:{self.output_dir.name}:scene_{scene.scene_number:03d}"
        if self._reusable_clip(clip_path):
            existing = await provider.find_generation_by_idempotency(idempotency_key)
            if existing is not None:
                self.log(f"[scene {scene.scene_number}] resumed from existing clip")
                return clip_path, existing.generation_id
            return clip_path, "resumed"

        last_error: Exception | None = None
        for attempt in range(MAX_SCENE_ATTEMPTS):
            try:
                if scene.scene_number > 1 and parent_generation_id:
                    generation = await provider.extend_generation(
                        parent_generation_id=parent_generation_id,
                        prompt=scene.prompt,
                        tier=tier,
                        orientation=self.config.orientation,
                        duration=float(scene.duration),
                        reference_image_path=reference_image_path,
                    )
                else:
                    generation = await provider.submit_generation(
                        prompt=scene.prompt,
                        tier=tier,
                        orientation=self.config.orientation,
                        duration=float(scene.duration),
                        reference_image_path=reference_image_path,
                        idempotency_key=f"{idempotency_key}:a{attempt}",
                    )

                if provider.name == "taaft" and hasattr(provider, "wait_for_generation"):
                    # Single-browser poll: TAAFT clips can take many minutes.
                    self.log(f"[scene {scene.scene_number}] generation {generation.generation_id} submitted; waiting (this can take minutes in {tier} mode)...")
                    generation = await provider.wait_for_generation(generation.generation_id)
                    if generation.failed:
                        raise RuntimeError(generation.error or "TAAFT generation failed")
                    if not generation.video_url:
                        raise RuntimeError("TAAFT generation finished without a video URL")
                else:
                    deadline = time.monotonic() + (300 if provider.name in {"simulated", "test-vision"} else 3600)
                    interval = 0.4 if provider.name == "simulated" else 20
                    while True:
                        if generation.status in TERMINAL_OK and generation.video_url:
                            break
                        if generation.failed:
                            raise RuntimeError(generation.error or "Provider failure")
                        if time.monotonic() > deadline:
                            raise TimeoutError(f"Generation timed out for scene {scene.scene_number}")
                        await asyncio.sleep(interval)
                        generation = await provider.get_generation_status(generation.generation_id)

                generation_id = generation.generation_id
                await provider.download_generation(generation, clip_path)
                report = validate_clip(clip_path)
                if not report["passed"]:
                    raise RuntimeError(f"Clip failed validation: {report['checks']}")
                return clip_path, generation_id
            except Exception as error:  # noqa: BLE001
                last_error = error
                self.log(
                    f"[scene {scene.scene_number}] attempt {attempt + 1}/{MAX_SCENE_ATTEMPTS} failed: "
                    f"{str(error)[:220]}"
                )
                if attempt + 1 < MAX_SCENE_ATTEMPTS:
                    await asyncio.sleep(min(8.0, 2.0 * (attempt + 1)))
        raise RuntimeError(f"Scene {scene.scene_number} failed: {last_error}")

    # ------------------------------------------------------------ narration

    async def _apply_scene_sound(self, scene, clip_path: Path) -> Path:
        narration_path: Path | None = None
        narration_seconds = 0.0
        if self.config.with_narration:
            narration_path = self.audio_dir / f"narration_{scene.scene_number:03d}.wav"
            if not narration_path.exists():
                self.log(f"[scene {scene.scene_number}] narrating...")
                await asyncio.to_thread(
                    synthesize_speech,
                    scene.narration,
                    narration_path,
                    rate=self.config.narration_rate,
                    voice=self.config.narration_voice,
                )
            narration_seconds = await asyncio.to_thread(narration_duration, narration_path)

        if not self.config.with_ambience and narration_path is None:
            return clip_path

        scene_audio = self.audio_dir / f"track_{scene.scene_number:03d}.wav"
        await asyncio.to_thread(
            build_scene_audio,
            scene_audio,
            scene_seconds=float(scene.duration),
            script_line=(getattr(scene, "sound_design", "") or scene.lighting or scene.actions),
            narration_path=narration_path,
            narration_seconds=narration_seconds,
            with_narration=narration_path is not None,
            with_ambience=self.config.with_ambience,
        )
        mixed = self.scenes_dir / f"scene_{scene.scene_number:03d}{RESUME_SUFFIX}"
        await asyncio.to_thread(
            mux_audio_onto_clip,
            clip_path,
            scene_audio,
            mixed,
            keep_clip_audio=self.config.keep_clip_audio,
        )
        return mixed

    # ------------------------------------------------------------ transitions

    def _apply_dip_to_black_fades(self, clips: list[Path]) -> list[Path]:
        """Fades keep every clip's exact duration, so total runtime stays exact."""
        ffmpeg = find_ffmpeg()
        faded_dir = self.work_dir / "faded"
        faded_dir.mkdir(parents=True, exist_ok=True)
        output: list[Path] = []
        for index, clip in enumerate(clips, start=1):
            evidence = validate_clip(clip)
            if not evidence["passed"]:
                raise RuntimeError(f"Clip {clip.name} invalid before fades: {evidence['checks']}")
            duration = float(probe_video(clip).get("duration") or 8.0)
            fade_in = 1.0 if index == 1 else 0.3
            fade_out = 1.6 if index == len(clips) else 0.3
            destination = faded_dir / f"faded_{index:03d}.mp4"
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(clip),
                "-vf",
                f"fade=t=in:st=0:d={fade_in:.2f},fade=t=out:st={max(0.0, duration - fade_out):.2f}:d={fade_out:.2f}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "19",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                str(destination),
            ]
            run_ffmpeg(command, timeout=600)
            output.append(destination)
        return output

    # ------------------------------------------------------------ narration doc

    def _narration_script_text(self, document, plan: ScenePlan) -> str:
        title = plan.title or "Untitled Film"
        lines = [title, "=" * min(80, max(12, len(title))), ""]
        for scene in sorted(plan.scenes, key=lambda item: item.scene_number):
            block = next(
                (item for item in document.scenes if item.number == scene.scene_number),
                None,
            )
            timecode = f" ({block.timecode_from}-{block.timecode_to})" if block else ""
            lines.append(f"SCENE {scene.scene_number:02d} - {scene.title}{timecode}")
            lines.append("")
            lines.append(scene.narration)
            lines.append("")
        return "\n".join(lines)
