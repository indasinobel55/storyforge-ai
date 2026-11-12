from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent.core.errors import ProviderDisabledError
from agent.core.util import extract_last_frame, probe_video, sha256_file
from agent.planner.planner import PlanRequest, build_plan
from agent.postproduction.assemble import assemble_clips
from agent.providers.base import GenerationResult, VideoProvider
from agent.providers.simulated import SimulatedProvider
from agent.providers.taaft import TaaftProvider
from agent.scenes.spec import CharacterSpec
from agent.validation.validator import validate_clip, validate_final

from .client import LocalApiClient, LocalApiError

TERMINAL_OK = {"succeeded", "success", "completed"}
TERMINAL_FAIL = {"failed", "error", "canceled", "cancelled"}
MAX_SCENE_ATTEMPTS = 3


@dataclass
class LocalConfig:
    work_dir: Path = field(default_factory=lambda: Path.cwd() / "local_work")
    simulated_generation_seconds: float = 1.0
    simulated_clip_seconds: float = 2.0
    planner_llm: bool = field(default_factory=lambda: os.environ.get("LOCAL_PLANNER_LLM", "0") == "1")
    planner_llm_url: str = field(
        default_factory=lambda: os.environ.get("PLANNER_LLM_URL", "https://text.pollinations.ai/openai")
    )
    taaft_local_enabled: bool = field(default_factory=lambda: os.environ.get("TAAFT_LOCAL_ENABLED", "0") == "1")
    taaft_storage_state: Path | None = field(
        default_factory=lambda: Path(os.environ["TAAFT_STORAGE_STATE"])
        if os.environ.get("TAAFT_STORAGE_STATE")
        else None
    )
    taaft_poll_seconds: int = 20
    taaft_job_timeout_seconds: int = 3600

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)


class LocalRunner:
    """Executes backend jobs on the user's machine using the shared agent core.

    Uses the same planner, provider adapters, downloader, FFmpeg pipeline and
    validation modules as the cloud worker. The machine must stay powered on and
    connected while a job is running.
    """

    def __init__(self, client: LocalApiClient, config: LocalConfig | None = None) -> None:
        self.client = client
        self.config = config or LocalConfig()
        self._simulated = SimulatedProvider(
            cache_dir=self.config.work_dir / "_simulated",
            generation_seconds=self.config.simulated_generation_seconds,
            clip_seconds=self.config.simulated_clip_seconds,
        )

    async def run_once(self) -> bool:
        claim = await asyncio.to_thread(self.client.claim)
        if not claim:
            return False
        job = claim["job"]
        job_id = job["id"]
        try:
            kind = job["kind"]
            if kind == "PLAN":
                result = await self._run_plan(job, claim)
            elif kind == "GENERATE":
                result = await self._run_generate(job, claim)
            elif kind == "ASSEMBLE":
                result = await self._run_assemble(job, claim)
            else:
                raise RuntimeError(f"Unsupported local job kind: {kind}")
            await asyncio.to_thread(self.client.complete, job_id, result or {"mode": "local"})
        except ProviderDisabledError as error:
            await asyncio.to_thread(self.client.fail, job_id, str(error))
        except Exception as error:  # noqa: BLE001
            await asyncio.to_thread(self.client.fail, job_id, str(error)[:4000])
        return True

    async def run_until_idle(self, max_jobs: int = 50) -> int:
        processed = 0
        for _ in range(max_jobs):
            if not await self.run_once():
                break
            processed += 1
        return processed

    # ------------------------------------------------------------------ PLAN

    async def _run_plan(self, job: dict, claim: dict) -> dict:
        project = claim["project"]
        characters = [
            CharacterSpec(
                name=item["name"],
                age_range=item.get("age_range"),
                description=item.get("description") or "",
                appearance=item.get("appearance") or {},
                voice_description=item.get("voice_description"),
                reference_notes=item.get("reference_notes"),
            )
            for item in claim.get("characters") or []
        ]
        request = PlanRequest(
            title=project["title"],
            script=project["script"],
            style=project["style"],
            scene_count=project["target_scene_count"],
            scene_seconds=project["scene_seconds"],
            target_duration_seconds=project["target_duration_seconds"],
            orientation=project["orientation"],
            aspect_ratio=project["aspect_ratio"],
            genre=project.get("genre"),
            characters=characters,
            reference_notes=project.get("reference_notes"),
            provider="auto" if self.config.planner_llm else "deterministic",
            llm_url=self.config.planner_llm_url,
        )
        plan = await asyncio.to_thread(build_plan, request)
        payload = {
            "logline": plan.logline,
            "plan_scenes": [scene.model_dump() for scene in plan.scenes],
            "characters": [character.model_dump() for character in plan.characters],
            "message": "Plan generated by local worker",
        }
        await asyncio.to_thread(self.client.checkpoint, job["id"], payload)
        return {"mode": "local", "scene_count": len(plan.scenes)}

    # -------------------------------------------------------------- GENERATE

    def _provider(self, project: dict) -> VideoProvider:
        provider = project["provider"]
        if provider == "simulated":
            return self._simulated
        if provider == "taaft":
            return TaaftProvider(
                enabled=self.config.taaft_local_enabled,
                storage_state_path=self.config.taaft_storage_state,
                headless=False,
                poll_seconds=self.config.taaft_poll_seconds,
                job_timeout_seconds=self.config.taaft_job_timeout_seconds,
            )
        raise ProviderDisabledError(f"Unknown provider {provider}")

    async def _run_generate(self, job: dict, claim: dict) -> dict:
        project = claim["project"]
        job_id = job["id"]
        provider = self._provider(project)
        scenes = sorted(claim.get("scenes") or [], key=lambda item: item["scene_number"])
        job_dir = self.config.work_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        previous: dict | None = None
        previous_local_frame: Path | None = None

        for scene in scenes:
            heartbeat = await asyncio.to_thread(self.client.heartbeat, job_id)
            if heartbeat.get("project_status") in {"PAUSED", "CANCELLED"}:
                await asyncio.to_thread(
                    self.client.checkpoint,
                    job_id,
                    {"project_status": heartbeat["project_status"]},
                )
                return {"mode": "local", "paused": True, "project_status": heartbeat["project_status"]}
            if scene.get("status") == "SUCCEEDED":
                previous = scene
                continue

            parent_generation_id = previous.get("generation_id") if previous else None
            reference = previous_local_frame
            if reference is None and previous and previous.get("thumbnail_url"):
                try:
                    reference = await asyncio.to_thread(
                        self.client.download,
                        previous["thumbnail_url"],
                        job_dir / f"ref_{previous['scene_number']:03d}.png",
                    )
                except Exception:
                    reference = None

            result, clip_path, last_frame = await self._generate_scene(
                project=project,
                scene=scene,
                provider=provider,
                job_id=job_id,
                job_dir=job_dir,
                parent_generation_id=parent_generation_id,
                reference=reference,
            )
            await asyncio.to_thread(
                self.client.upload_scene, job_id, scene["id"], clip_path, "video"
            )
            await asyncio.to_thread(
                self.client.upload_scene, job_id, scene["id"], last_frame, "last_frame"
            )
            probe = probe_video(clip_path)
            await asyncio.to_thread(
                self.client.checkpoint,
                job_id,
                {
                    "scene_updates": [
                        {
                            "scene_id": scene["id"],
                            "status": "SUCCEEDED",
                            "generation_id": result.generation_id,
                            "provider_status": "succeeded",
                            "download_status": "DOWNLOADED",
                            "attempt_count": int(scene.get("attempt_count") or 0) + 1,
                            "duration_actual": float(probe.get("duration") or scene["duration"]),
                            "width": int(probe.get("width") or 0),
                            "height": int(probe.get("height") or 0),
                            "fps": probe.get("fps"),
                            "output_checksum": sha256_file(clip_path),
                            "mode": result.mode,
                            "parent_generation_id": result.parent_generation_id,
                            "error": None,
                        }
                    ],
                    "project_status": "GENERATING",
                },
            )
            scene = dict(scene)
            scene.update(
                {
                    "status": "SUCCEEDED",
                    "generation_id": result.generation_id,
                    "duration_actual": float(probe.get("duration") or scene["duration"]),
                    "attempt_count": int(scene.get("attempt_count") or 0) + 1,
                }
            )
            previous = scene
            previous_local_frame = last_frame

        await asyncio.to_thread(
            self.client.checkpoint,
            job_id,
            {"project_status": "PROCESSING", "enqueue_assemble": True},
        )
        return {"mode": "local", "all_scenes_succeeded": True}

    async def _generate_scene(
        self,
        *,
        project: dict,
        scene: dict,
        provider: VideoProvider,
        job_id: str,
        job_dir: Path,
        parent_generation_id: str | None,
        reference: Path | None,
    ) -> tuple[GenerationResult, Path, Path]:
        attempt_number = int(scene.get("attempt_count") or 0) + 1
        last_error: Exception | None = None
        generation: GenerationResult | None = None
        existing_generation_id = (
            scene["generation_id"]
            if scene.get("generation_id")
            and scene.get("status") in {"GENERATING", "DOWNLOADING", "SUBMITTING"}
            else None
        )

        for round_index in range(MAX_SCENE_ATTEMPTS):
            try:
                if generation is None and existing_generation_id:
                    generation = await provider.get_generation_status(existing_generation_id)
                    existing_generation_id = None

                if generation is None:
                    if parent_generation_id and scene["scene_number"] > 1:
                        generation = await provider.extend_generation(
                            parent_generation_id=parent_generation_id,
                            prompt=scene["prompt"],
                            tier=project["tier"],
                            orientation=project["orientation"],
                            duration=float(scene["duration"]),
                            reference_image_path=reference,
                        )
                    else:
                        generation = await provider.submit_generation(
                            prompt=scene["prompt"],
                            tier=project["tier"],
                            orientation=project["orientation"],
                            duration=float(scene["duration"]),
                            reference_image_path=reference,
                            idempotency_key=f"local:{scene['id']}:a{attempt_number + round_index}",
                        )
                    await asyncio.to_thread(
                        self.client.checkpoint,
                        job_id,
                        {
                            "scene_updates": [
                                {
                                    "scene_id": scene["id"],
                                    "status": "GENERATING",
                                    "generation_id": generation.generation_id,
                                    "provider_status": generation.status,
                                    "attempt_count": attempt_number + round_index,
                                    "mode": generation.mode,
                                    "parent_generation_id": generation.parent_generation_id,
                                }
                            ],
                            "project_status": "GENERATING",
                        },
                    )

                deadline = time.monotonic() + (
                    self.config.taaft_job_timeout_seconds
                    if provider.name == "taaft"
                    else 300
                )
                interval = 0.4 if provider.name == "simulated" else self.config.taaft_poll_seconds
                while True:
                    if generation.status in TERMINAL_OK and generation.video_url:
                        break
                    if generation.failed:
                        raise RuntimeError(generation.error or "Provider reported failure")
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"Generation {generation.generation_id} timed out")
                    await asyncio.sleep(interval)
                    generation = await provider.get_generation_status(generation.generation_id)

                clip = job_dir / f"scene_{scene['scene_number']:03d}.mp4"
                await provider.download_generation(generation, clip)
                report = validate_clip(clip)
                if not report["passed"]:
                    raise RuntimeError(f"Downloaded clip invalid: {report['checks']}")
                last_frame = job_dir / f"scene_{scene['scene_number']:03d}_last.png"
                extract_last_frame(clip, last_frame)
                return generation, clip, last_frame
            except Exception as error:  # noqa: BLE001
                last_error = error
                await asyncio.to_thread(
                    self.client.checkpoint,
                    job_id,
                    {
                        "scene_updates": [
                            {
                                "scene_id": scene["id"],
                                "status": "FAILED",
                                "error": str(error)[:2000],
                                "attempt_count": attempt_number + round_index,
                                "download_status": "FAILED",
                            }
                        ]
                    },
                )
                generation = None
                existing_generation_id = None
                if round_index + 1 < MAX_SCENE_ATTEMPTS:
                    await asyncio.sleep(min(8, 2 * (round_index + 1)))
        raise RuntimeError(
            f"Scene {scene['scene_number']} failed after {MAX_SCENE_ATTEMPTS} attempts: {last_error}"
        )

    # -------------------------------------------------------------- ASSEMBLE

    async def _run_assemble(self, job: dict, claim: dict) -> dict:
        project = claim["project"]
        scenes = sorted(claim.get("scenes") or [], key=lambda item: item["scene_number"])
        if not scenes:
            raise RuntimeError("No scenes to assemble")
        job_dir = self.config.work_dir / job["id"] / "assembly"
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        job_dir.mkdir(parents=True, exist_ok=True)

        clip_paths: list[Path] = []
        for scene in scenes:
            if not scene.get("video_url"):
                raise RuntimeError(f"Scene {scene['scene_number']} has no downloadable clip")
            clip = job_dir / f"source_{scene['scene_number']:03d}.mp4"
            await asyncio.to_thread(self.client.download, scene["video_url"], clip)
            clip_paths.append(clip)

        music_path = None
        voiceover_path = None
        assets = claim.get("assets") or {}
        if assets.get("music_key"):
            music_path = job_dir / "music_asset"
            await asyncio.to_thread(self.client.download, assets["music_key"], music_path)
        if assets.get("voiceover_key"):
            voiceover_path = job_dir / "voiceover_asset"
            await asyncio.to_thread(self.client.download, assets["voiceover_key"], voiceover_path)

        try:
            width_text, height_text = project["resolution"].lower().split("x")
            width, height = int(width_text), int(height_text)
        except Exception:
            width, height = (720, 1280) if project["orientation"] == "portrait" else (1280, 720)

        config = project.get("generation_config") or {}
        result = await asyncio.to_thread(
            assemble_clips,
            clip_paths,
            job_dir,
            width=width,
            height=height,
            fps=24.0,
            transition=config.get("transition", "none"),
            music_path=music_path,
            voiceover_path=voiceover_path,
        )
        report = validate_final(
            result.final_path,
            expected_scene_count=len(scenes),
            expected_duration=result.expected_duration,
            expected_width=width,
            expected_height=height,
            thumbnail_path=result.thumbnail_path,
        )
        if not report["passed"]:
            raise RuntimeError("Local final validation failed: " + "; ".join(report.get("errors") or []))
        await asyncio.to_thread(
            self.client.upload_final, job["id"], result.final_path, result.thumbnail_path
        )
        shutil.rmtree(job_dir, ignore_errors=True)
        return {
            "mode": "local",
            "duration": report["metadata"].get("duration"),
            "validation": report["passed"],
        }
