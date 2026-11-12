from __future__ import annotations

import asyncio
import os
import shutil
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from agent.core.errors import GenerationError, ProviderDisabledError, ValidationError, VisionModelError, ContinuityError
from agent.core.util import probe_video, sha256_file, extract_last_frame
from agent.scenes.spec import SceneSpec, CharacterSpec
from agent.postproduction.ffmpeg_tools import (
    concat_normalized,
    concat_with_crossfade,
    mix_audio,
    normalize_clip,
)
from agent.providers.base import GenerationResult
from agent.validation.validator import validate_clip, validate_final
from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models import (
    Character,
    GenerationAttempt,
    Job,
    Project,
    Scene,
    Video,
)
from backend.app.security import utcnow
from backend.app.services.continuity_service import ContinuityService
from backend.app.services.planning_service import execute_planning
from backend.app.services.project_service import (
    acquire_provider_lock,
    notify,
    publish_activity,
    recompute_progress,
    record_usage,
    refresh_provider_lock,
    release_provider_lock,
    resolve_provider,
    storage_keys,
)
from backend.app.services.queue import (
    claim_job,
    complete_job,
    enqueue_job,
    fail_job,
    heartbeat_job,
)
from backend.app.services.storage import storage

TERMINAL_OK = {"succeeded", "success", "completed"}
TERMINAL_FAIL = {"failed", "error", "canceled", "cancelled"}
SCENE_ATTEMPT_LIMIT = 3


def utcnow_naive_safe(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class GenerationWorker:
    def __init__(self, worker_id: str | None = None) -> None:
        self.worker_id = worker_id or f"{settings.worker_id_prefix}-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self._active_account_id: str | None = None
        self._active_project_id: str | None = None
        self._stopping = asyncio.Event()

    async def run_forever(self) -> None:
        if not settings.cloud_execution_enabled:
            print(
                "[worker] cloud execution is disabled (EXECUTION_MODE=local). "
                "Start a local worker with: python -m local_agent --api-url <url> --token <token>",
                flush=True,
            )
            return
        print(f"[worker] {self.worker_id} started (db={settings.database_url.split('://')[0]})", flush=True)
        while not self._stopping.is_set():
            try:
                async with SessionLocal() as db:
                    job = await claim_job(
                        db, worker_id=self.worker_id, lease_seconds=settings.worker_lease_seconds
                    )
                if job is None:
                    await asyncio.sleep(settings.worker_poll_seconds)
                    continue
                await self._run_job(job)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - worker must never die
                print(f"[worker] loop error: {error}", flush=True)
                await asyncio.sleep(2)

    def stop(self) -> None:
        self._stopping.set()

    async def run_until_idle(self, max_iterations: int = 200) -> int:
        """Process jobs until the queue is empty. Used by tests and one-shot mode."""
        if not settings.cloud_execution_enabled:
            return 0
        processed = 0
        for _ in range(max_iterations):
            async with SessionLocal() as db:
                job = await claim_job(
                    db, worker_id=self.worker_id, lease_seconds=settings.worker_lease_seconds
                )
            if job is None:
                break
            await self._run_job(job)
            processed += 1
        return processed

    async def _run_job(self, job: Job) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        outcome = "succeeded"
        try:
            async with SessionLocal() as db:
                fresh = await db.get(Job, job.id)
                if fresh is None or fresh.status != "RUNNING":
                    return
                if fresh.kind == "PLAN":
                    result = await self._process_plan(db, fresh)
                elif fresh.kind == "GENERATE":
                    result = await self._process_generate(db, fresh)
                elif fresh.kind == "ASSEMBLE":
                    result = await self._process_assemble(db, fresh)
                else:
                    raise RuntimeError(f"Unknown job kind: {fresh.kind}")
                if result.get("deferred"):
                    outcome = "deferred"
                else:
                    await complete_job(db, fresh, result)
        except ProviderDisabledError as error:
            outcome = "failed"
            async with SessionLocal() as db:
                await self._mark_project_failed(db, job, str(error))
                await fail_job(db, job, str(error))
        except ValidationError as error:
            outcome = "failed"
            async with SessionLocal() as db:
                await fail_job(db, job, str(error))
                if job.attempts >= job.max_attempts:
                    await self._mark_project_failed(db, job, str(error))
        except Exception as error:  # noqa: BLE001
            outcome = "failed"
            async with SessionLocal() as db:
                action = await fail_job(db, job, str(error))
                if action == "failed":
                    await self._mark_project_failed(db, job, str(error))
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            if self._active_account_id:
                try:
                    async with SessionLocal() as db:
                        await release_provider_lock(
                            db, account_id=self._active_account_id, worker_id=self.worker_id
                        )
                except Exception:  # noqa: BLE001
                    pass
            self._active_account_id = None
            self._active_project_id = None
            print(f"[worker] job {job.id} ({job.kind}) {outcome}", flush=True)

    async def _heartbeat(self, job_id: str) -> None:
        interval = max(2.0, settings.worker_lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            try:
                async with SessionLocal() as db:
                    await heartbeat_job(db, job_id, self.worker_id, settings.worker_lease_seconds)
                    if self._active_account_id:
                        await refresh_provider_lock(
                            db,
                            account_id=self._active_account_id,
                            worker_id=self.worker_id,
                            lease_seconds=settings.worker_lease_seconds,
                        )
                    if self._active_project_id:
                        project = await db.get(Project, self._active_project_id)
                        if project is not None and project.status == "CANCELLED":
                            self._stopping_pipeline = True
            except Exception:  # noqa: BLE001
                pass

    async def _mark_project_failed(self, db, job: Job, error: str) -> None:
        if not job.project_id:
            return
        project = await db.get(Project, job.project_id)
        if project is None:
            return
        if project.status in {"CANCELLED", "COMPLETED"}:
            return
        project.status = "FAILED"
        project.error = error[:4000]
        await db.commit()
        await notify(
            db,
            user_id=project.user_id,
            project_id=project.id,
            kind="project_failed",
            title="Project failed",
            body=f"\"{project.title}\" could not complete: {error[:300]}",
        )

    async def _defer_job(self, db, job: Job, seconds: int = 10) -> dict:
        job.status = "QUEUED"
        job.attempts = max(0, job.attempts - 1)
        job.available_at = utcnow() + timedelta(seconds=seconds)
        job.locked_by = None
        job.locked_at = None
        job.lease_expires_at = None
        await db.commit()
        return {"deferred": True}

    # ------------------------------------------------------------------ PLAN

    async def _process_plan(self, db, job: Job) -> dict:
        project = await db.get(Project, job.project_id)
        if project is None:
            raise RuntimeError("Project not found")
        if project.status == "CANCELLED":
            return {"cancelled": True}
        project.status = "PLANNING"
        project.error = None
        await db.commit()
        summary = await execute_planning(db, project)
        return summary

    # -------------------------------------------------------------- GENERATE

    async def _process_generate(self, db, job: Job) -> dict:
        project = await db.get(Project, job.project_id)
        if project is None:
            raise RuntimeError("Project not found")
        if project.status == "CANCELLED":
            return {"cancelled": True}
        if project.status == "PAUSED":
            return {"paused": True}

        scenes = list(
            (
                await db.execute(
                    select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)
                )
            ).scalars()
        )
        if not scenes:
            raise GenerationError("No scenes approved for generation")

        provider, account, session_dir = await resolve_provider(db, project=project, worker_id=self.worker_id)
        acquired = await acquire_provider_lock(
            db,
            account_id=account.id,
            project_id=project.id,
            worker_id=self.worker_id,
            lease_seconds=settings.worker_lease_seconds,
        )
        if not acquired:
            return await self._defer_job(db, job, seconds=15)

        self._active_account_id = account.id
        self._active_project_id = project.id
        if project.status != "PAUSED":
            project.status = "GENERATING"
            project.started_at = project.started_at or utcnow()
        await db.commit()

        try:
            ordered = sorted(scenes, key=lambda item: item.scene_number)
            for index, scene in enumerate(ordered):
                await db.refresh(project)
                if project.status == "CANCELLED":
                    return {"cancelled": True, "completed_scenes": index}
                if project.status == "PAUSED":
                    return {"paused": True, "completed_scenes": index}

                previous = ordered[index - 1] if index > 0 else None
                await self._generate_scene(
                    db,
                    project=project,
                    scene=scene,
                    provider=provider,
                    previous=previous,
                    scenes_total=len(ordered),
                )

            await db.refresh(project)
            if project.status in {"CANCELLED", "PAUSED"}:
                return {"paused": project.status == "PAUSED", "cancelled": project.status == "CANCELLED"}

            project.status = "PROCESSING"
            project.error = None
            await db.commit()
            await recompute_progress(db, project)
            await enqueue_job(
                db,
                user_id=project.user_id,
                project_id=project.id,
                kind="ASSEMBLE",
                idempotency_key=f"assemble:{project.id}:{project.plan_revision}",
                payload={"plan_revision": project.plan_revision},
                max_attempts=settings.worker_max_attempts,
                revive=True,
            )
            await notify(
                db,
                user_id=project.user_id,
                project_id=project.id,
                kind="generation_complete",
                title="All scenes generated",
                body=f"Assembling and validating \"{project.title}\" now.",
            )
            return {"scenes": len(ordered), "stage": "assemble_queued"}
        finally:
            if session_dir:
                shutil.rmtree(session_dir, ignore_errors=True)

    async def _generate_scene(
        self,
        db,
        *,
        project: Project,
        scene: Scene,
        provider,
        previous: Scene | None,
        scenes_total: int,
    ) -> None:
        keys = storage_keys(project.user_id, project.id)
        scene_key = f"{keys['scene']}/scene_{scene.scene_number:03d}.mp4"
        frame_key = f"{keys['scene']}/scene_{scene.scene_number:03d}_last.png"

        if scene.status == "SUCCEEDED":
            if scene.local_path and await storage.exists(scene.local_path):
                return
            scene.status = "PENDING"
            scene.local_path = None
            scene.download_status = "PENDING"
            await db.commit()

        if scene.status == "FAILED" and scene.attempt_count >= SCENE_ATTEMPT_LIMIT:
            raise GenerationError(
                f"Scene {scene.scene_number} failed after {scene.attempt_count} attempts: {scene.error}"
            )
        if scene.status == "FAILED":
            scene.status = "PENDING"
            scene.error = None
            await db.commit()

        parent_generation_id = None
        reference_path: Path | None = None
        if previous is not None and previous.status == "SUCCEEDED":
            parent_generation_id = previous.generation_id
            if previous.last_frame_path:
                try:
                    candidate = storage.local_path(previous.last_frame_path)
                    if candidate.exists():
                        reference_path = candidate
                except Exception:
                    reference_path = None

        continuity: dict | None = None
        if previous is not None and previous.status == "SUCCEEDED":
            continuity = await self._run_continuity_stage(
                db,
                project=project,
                scene=scene,
                previous=previous,
                provider=provider,
                previous_clip_path=storage.local_path(previous.local_path),
                scenes_total=scenes_total,
            )
            if continuity.get("rewritten"):
                scene.prompt = continuity["final_prompt"]
                scene.continuity = continuity.get("continuity_summary") or scene.continuity
                scene.continuation_passage = continuity.get("continuation_passage") or scene.continuation_passage
                scene.frame_analysis = continuity.get("frame_analysis") or scene.frame_analysis
                scene.final_prompt = continuity.get("final_prompt") or scene.final_prompt
                scene.script_segment = scene.script_segment or scene.narration or scene.actions or ""
                await db.commit()

        last_error: Exception | None = None
        for round_index in range(SCENE_ATTEMPT_LIMIT):
            try:
                await self._run_scene_attempt(
                    db,
                    project=project,
                    scene=scene,
                    provider=provider,
                    scene_key=scene_key,
                    frame_key=frame_key,
                    parent_generation_id=parent_generation_id,
                    reference_path=reference_path,
                )
                await recompute_progress(db, project)
                succeeded = (
                    await db.execute(
                        select(Scene).where(Scene.project_id == project.id, Scene.status == "SUCCEEDED")
                    )
                ).scalars().all()
                await record_usage(
                    db,
                    user_id=project.user_id,
                    project_id=project.id,
                    kind="scene_generated",
                    quantity=1,
                    unit="scene",
                    meta={"scene_number": scene.scene_number, "provider": project.provider},
                )
                if len(succeeded) == 1:
                    await notify(
                        db,
                        user_id=project.user_id,
                        project_id=project.id,
                        kind="generation_progress",
                        title="First scene generated",
                        body=(
                            f"\"{project.title}\" is progressing locally ({len(succeeded)}/{scenes_total})."
                            if settings.effective_execution_mode == "local"
                            else f"\"{project.title}\" is progressing in the cloud ({len(succeeded)}/{scenes_total})."
                        ),
                    )
                elif len(succeeded) == max(1, scenes_total // 2):
                    await notify(
                        db,
                        user_id=project.user_id,
                        project_id=project.id,
                        kind="generation_progress",
                        title="Halfway there",
                        body=f"\"{project.title}\" is {len(succeeded)}/{scenes_total} scenes complete.",
                    )
                await publish_activity(
                    db,
                    user_id=project.user_id,
                    project_id=project.id,
                    event="scene_complete",
                    title=f"Scene {scene.scene_number} generated",
                    body=f"Scene {scene.scene_number} finished and passed clip validation.",
                    meta={"scene_number": scene.scene_number, "duration": scene.duration_actual},
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                last_error = error
                await self._mark_latest_attempt_failed(db, scene, error)
                scene.status = "FAILED"
                scene.error = str(error)[:4000]
                scene.attempt_count = max(scene.attempt_count, round_index + 1)
                scene.download_status = "FAILED"
                await db.commit()
                await publish_activity(
                    db,
                    user_id=project.user_id,
                    project_id=project.id,
                    event="scene_failed",
                    title=f"Scene {scene.scene_number} failed",
                    body=str(error)[:400],
                    meta={"scene_number": scene.scene_number},
                )
                if round_index + 1 < SCENE_ATTEMPT_LIMIT:
                    await asyncio.sleep(min(10, 2 * (round_index + 1)))
                    scene.status = "PENDING"
                    await db.commit()
                    continue
                break
        raise GenerationError(
            f"Scene {scene.scene_number} failed after {SCENE_ATTEMPT_LIMIT} attempts: {last_error}"
        )

    async def _run_continuity_stage(
        self,
        db,
        *,
        project: Project,
        scene: Scene,
        previous: Scene,
        provider,
        previous_clip_path: Path,
        scenes_total: int,
    ) -> dict:
        characters = list(
            (
                await db.execute(
                    select(Character).where(Character.project_id == project.id).order_by(Character.position)
                )
            ).scalars()
        )
        continuity_service = ContinuityService(
            vision_adapter=provider,
            fallback_when_unavailable=not settings.taaft_enabled,
        )
        previous_spec = SceneSpec(
            scene_number=previous.scene_number,
            title=previous.title,
            narrative_purpose=previous.narrative_purpose,
            duration=float(previous.duration),
            environment=previous.environment,
            character_presence=previous.character_presence,
            actions=previous.actions,
            camera=previous.camera,
            lighting=previous.lighting,
            visual_style=previous.visual_style,
            prompt=previous.prompt,
            negative_prompt=previous.negative_prompt,
            reference_assets=previous.reference_assets,
            continuity=previous.continuity,
            previous_scene_relationship=previous.previous_scene_relationship,
            next_scene_relationship=previous.next_scene_relationship,
            narration=previous.narration,
            dialogue=previous.dialogue,
        )
        try:
            frame_analysis = await continuity_service.analyze_previous_frame(
                previous_scene_spec=previous_spec,
                previous_clip_path=previous_clip_path,
                project_title=project.title,
                project_style=project.style,
                characters=[CharacterSpec(
                    name=c.name,
                    age_range=c.age_range,
                    description=c.description,
                    appearance=c.appearance or {},
                    voice_description=c.voice_description,
                    reference_notes=c.reference_notes,
                ) for c in characters],
            )
        except (VisionModelError, ContinuityError) as error:
            if not settings.taaft_enabled and not continuity_service._fallback_when_unavailable:
                raise
            frame_analysis = ContinuityService.FrameAnalysisResult(
                frame_path=previous_clip_path.parent / f"{previous_clip_path.stem}_last.png",
                raw_analysis="",
                summary="",
                blocked=True,
                error=str(error),
            )
        continuation_passage = None
        if frame_analysis.usable:
            try:
                continuation_passage = await continuity_service.write_continuation(
                    script_segment=scene.script_segment or scene.narration or scene.actions or "",
                    frame_analysis_summary=frame_analysis.summary,
                    scene_number=scene.scene_number,
                    total_scenes=scenes_total,
                    project_title=project.title,
                )
            except ContinuityError:
                continuation_passage = None
        if not continuation_passage and not frame_analysis.usable:
            continuation_passage = (
                f"Continue the established world from the previous scene without a live frame analysis. "
                f"Maintain the same characters, wardrobe, environment, lighting, and color grade."
            )
        try:
            final_prompt = await continuity_service.build_next_prompt(
                scene=SceneSpec(
                    scene_number=scene.scene_number,
                    title=scene.title,
                    narrative_purpose=scene.narrative_purpose,
                    duration=float(scene.duration),
                    environment=scene.environment,
                    character_presence=scene.character_presence,
                    actions=scene.actions,
                    camera=scene.camera,
                    lighting=scene.lighting,
                    visual_style=scene.visual_style,
                    prompt=scene.prompt,
                    negative_prompt=scene.negative_prompt,
                    reference_assets=scene.reference_assets,
                    continuity=scene.continuity,
                    previous_scene_relationship=scene.previous_scene_relationship,
                    next_scene_relationship=scene.next_scene_relationship,
                    narration=scene.narration,
                    dialogue=scene.dialogue,
                ),
                project_title=project.title,
                project_style=project.style,
                project_characters=[CharacterSpec(
                    name=c.name,
                    age_range=c.age_range,
                    description=c.description,
                    appearance=c.appearance or {},
                    voice_description=c.voice_description,
                    reference_notes=c.reference_notes,
                ) for c in characters],
                frame_analysis_summary=frame_analysis.summary if frame_analysis.usable else None,
                continuation_passage=continuation_passage,
                is_final_scene=scene.scene_number >= scenes_total,
            )
        except ContinuityError as error:
            raise PromptBuildError(str(error)) from error
        summary = frame_analysis.summary or "(frame analysis unavailable)"
        return {
            "rewritten": True,
            "final_prompt": final_prompt,
            "frame_analysis": frame_analysis.raw_analysis,
            "frame_analysis_summary": summary,
            "continuation_passage": continuation_passage,
            "continuity_summary": summary,
            "parent_generation_id": previous.generation_id,
        }

    async def _mark_latest_attempt_failed(self, db, scene: Scene, error: Exception) -> None:
        attempt = (
            await db.execute(
                select(GenerationAttempt)
                .where(GenerationAttempt.scene_id == scene.id)
                .order_by(GenerationAttempt.submitted_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if attempt is None or attempt.status in {"succeeded", "failed"}:
            return
        attempt.status = "failed"
        attempt.error = str(error)[:4000]
        attempt.completed_at = utcnow()

    async def _run_scene_attempt(
        self,
        db,
        *,
        project: Project,
        scene: Scene,
        provider,
        scene_key: str,
        frame_key: str,
        parent_generation_id: str | None,
        reference_path: Path | None,
    ) -> None:
        attempt_number = scene.attempt_count + 1
        idempotency_key = f"scene:{scene.id}:a{attempt_number}"
        attempt = (
            await db.execute(
                select(GenerationAttempt).where(GenerationAttempt.idempotency_key == idempotency_key)
            )
        ).scalar_one_or_none()

        generation: GenerationResult | None = None
        if attempt is not None and attempt.generation_id:
            generation = GenerationResult(
                generation_id=attempt.generation_id,
                status=attempt.status,
                video_url=attempt.video_url,
                parent_generation_id=attempt.parent_generation_id,
                mode=attempt.mode,
            )
            scene.status = "GENERATING"
            scene.generation_id = attempt.generation_id
            scene.provider_status = attempt.status
            await db.commit()
        elif attempt is not None and attempt.status == "submitting":
            generation = await provider.find_generation_by_idempotency(idempotency_key)
            if generation is not None:
                attempt.generation_id = generation.generation_id
                attempt.status = generation.status
                attempt.video_url = generation.video_url
                attempt.submitted_at = attempt.submitted_at or utcnow()
                scene.generation_id = generation.generation_id
                await db.commit()

        if generation is None:
            if attempt is None:
                attempt = GenerationAttempt(
                    project_id=project.id,
                    scene_id=scene.id,
                    user_id=project.user_id,
                    provider=project.provider,
                    idempotency_key=idempotency_key,
                    status="submitting",
                    mode="extend" if parent_generation_id and scene.scene_number > 1 else "initial",
                    submitted_at=utcnow(),
                )
                db.add(attempt)
                await db.commit()
                await db.refresh(attempt)
            scene.status = "SUBMITTING"
            scene.attempt_count = attempt_number
            scene.started_at = scene.started_at or utcnow()
            await db.commit()

            if parent_generation_id and scene.scene_number > 1:
                generation = await provider.extend_generation(
                    parent_generation_id=parent_generation_id,
                    prompt=scene.prompt,
                    tier=project.tier,
                    orientation=project.orientation,
                    duration=scene.duration,
                    reference_image_path=reference_path,
                )
            else:
                generation = await provider.submit_generation(
                    prompt=scene.prompt,
                    tier=project.tier,
                    orientation=project.orientation,
                    duration=scene.duration,
                    reference_image_path=reference_path,
                    idempotency_key=idempotency_key,
                )
            attempt.generation_id = generation.generation_id
            attempt.status = generation.status
            attempt.video_url = generation.video_url
            attempt.parent_generation_id = generation.parent_generation_id
            attempt.mode = generation.mode
            attempt.submitted_at = attempt.submitted_at or utcnow()
            scene.generation_id = generation.generation_id
            scene.parent_generation_id = generation.parent_generation_id
            scene.provider_status = generation.status
            scene.status = "GENERATING"
            await db.commit()
        else:
            scene.status = "GENERATING"
            scene.generation_id = generation.generation_id
            scene.provider_status = generation.status
            await db.commit()

        generation = await self._wait_for_generation(db, scene, provider, generation)
        if generation.status in TERMINAL_FAIL or generation.failed:
            attempt.status = "failed"
            attempt.error = generation.error or "Provider reported failure"
            attempt.completed_at = utcnow()
            await db.commit()
            raise GenerationError(attempt.error)

        if not generation.video_url:
            raise GenerationError(f"Generation {generation.generation_id} finished without a video URL")

        scene.status = "DOWNLOADING"
        scene.download_status = "DOWNLOADING"
        await db.commit()
        temp_dir = settings.storage_path / "_tmp" / project.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_video = temp_dir / f"scene_{scene.scene_number:03d}.mp4"
        temp_frame = temp_dir / f"scene_{scene.scene_number:03d}_last.png"

        if await storage.exists(scene_key):
            local_video = storage.local_path(scene_key)
        else:
            local_video = await provider.download_generation(generation, temp_video)
            clip_report = validate_clip(local_video)
            if not clip_report["passed"]:
                raise GenerationError(
                    f"Downloaded clip failed validation: {clip_report.get('checks')}"
                )
            await storage.save_file(scene_key, local_video)

        probe = probe_video(local_video)
        if not temp_frame.exists():
            extract_last_frame(local_video, temp_frame)
        await storage.save_file(frame_key, temp_frame)

        scene.local_path = scene_key
        scene.last_frame_path = frame_key
        scene.output_checksum = sha256_file(local_video)
        scene.duration_actual = float(probe.get("duration") or scene.duration)
        scene.width = int(probe.get("width") or 0)
        scene.height = int(probe.get("height") or 0)
        scene.fps = probe.get("fps")
        scene.mode = generation.mode or attempt.mode
        scene.parent_generation_id = generation.parent_generation_id or scene.parent_generation_id
        scene.status = "SUCCEEDED"
        scene.provider_status = "succeeded"
        scene.download_status = "DOWNLOADED"
        scene.error = None
        scene.generation_id = generation.generation_id
        scene.completed_at = utcnow()
        attempt.status = "succeeded"
        attempt.video_url = generation.video_url
        attempt.completed_at = utcnow()
        attempt.error = None
        await self._upsert_scene_video(db, project, scene, local_video, probe)
        await db.commit()

    async def _wait_for_generation(
        self, db, scene: Scene, provider, generation: GenerationResult
    ) -> GenerationResult:
        if generation.status in TERMINAL_OK and generation.video_url:
            return generation
        if generation.failed:
            return generation

        if provider.name == "taaft" and hasattr(provider, "wait_for_generation"):
            result = await provider.wait_for_generation(generation.generation_id)
            scene.provider_status = result.status
            await db.commit()
            return result

        deadline = time.monotonic() + (settings.taaft_job_timeout_seconds if provider.name == "taaft" else 300)
        interval = 0.4 if provider.name == "simulated" else max(5, settings.taaft_poll_seconds)
        last_status = None
        while time.monotonic() < deadline:
            result = await provider.get_generation_status(generation.generation_id)
            if result.status != last_status:
                last_status = result.status
                scene.provider_status = result.status
                await db.commit()
            if result.failed:
                return result
            if result.status in TERMINAL_OK and result.video_url:
                return result
            await asyncio.sleep(interval)
        raise GenerationError(f"Timed out waiting for generation {generation.generation_id}")

    async def _upsert_scene_video(self, db, project: Project, scene: Scene, local_video: Path, probe: dict) -> None:
        existing = (
            await db.execute(
                select(Video).where(Video.scene_id == scene.id, Video.kind == "scene")
            )
        ).scalar_one_or_none()
        video = existing or Video(
            user_id=project.user_id, project_id=project.id, scene_id=scene.id, kind="scene"
        )
        video.filename = f"scene_{scene.scene_number:03d}.mp4"
        video.storage_key = scene.local_path or ""
        video.thumbnail_key = scene.last_frame_path
        video.size_bytes = local_video.stat().st_size
        video.duration_seconds = float(probe.get("duration") or scene.duration)
        video.width = int(probe.get("width") or 0)
        video.height = int(probe.get("height") or 0)
        video.has_audio = bool(probe.get("has_audio"))
        video.checksum_sha256 = scene.output_checksum
        video.deleted_at = None
        if existing is None:
            db.add(video)
        await db.commit()

    # -------------------------------------------------------------- ASSEMBLE

    async def _process_assemble(self, db, job: Job) -> dict:
        project = await db.get(Project, job.project_id)
        if project is None:
            raise RuntimeError("Project not found")
        if project.status == "CANCELLED":
            return {"cancelled": True}
        if project.status == "PAUSED":
            return {"paused": True}

        scenes = list(
            (
                await db.execute(
                    select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)
                )
            ).scalars()
        )
        if not scenes:
            raise ValidationError("No scenes to assemble")
        missing = [scene.scene_number for scene in scenes if scene.status != "SUCCEEDED" or not scene.local_path]
        if missing:
            raise ValidationError(f"Scenes not ready for assembly: {missing}")

        project.status = "PROCESSING"
        await db.commit()

        width, height = self._target_resolution(project)
        render_dir = settings.storage_path / "_render" / project.id
        if render_dir.exists():
            shutil.rmtree(render_dir, ignore_errors=True)
        render_dir.mkdir(parents=True, exist_ok=True)

        normalized: list[Path] = []
        probes: list[dict] = []
        for scene in scenes:
            source = storage.local_path(scene.local_path)
            clip_report = validate_clip(source)
            if not clip_report["passed"]:
                raise ValidationError(f"Scene {scene.scene_number} clip is invalid: {clip_report['checks']}")
            target = render_dir / f"norm_{scene.scene_number:03d}.mp4"
            normalize_clip(source, target, width=width, height=height, fps=24)
            normalized.append(target)
            probes.append(probe_video(target))

        transitions = (project.generation_config or {}).get("transition", "none")
        concat_target = render_dir / "concat.mp4"
        if transitions in {"fade", "crossfade"} and len(normalized) > 1:
            try:
                concat_with_crossfade(normalized, concat_target, transition_seconds=0.4)
            except Exception:
                concat_normalized(normalized, concat_target)
        else:
            concat_normalized(normalized, concat_target)

        final_local = concat_target
        config = project.generation_config or {}
        music_key = config.get("music_key")
        voiceover_key = config.get("voiceover_key")
        if music_key or voiceover_key:
            music_path = storage.local_path(music_key) if music_key else None
            voice_path = storage.local_path(voiceover_key) if voiceover_key else None
            if (music_path and music_path.exists()) or (voice_path and voice_path.exists()):
                mixed = render_dir / "mixed.mp4"
                final_local = mix_audio(concat_target, mixed, music_path=music_path, voiceover_path=voice_path)

        thumbnail_local = render_dir / "thumbnail.jpg"
        try:
            from agent.core.util import extract_thumbnail

            extract_thumbnail(final_local, thumbnail_local, at_seconds=1.0)
        except Exception:
            thumbnail_local = None  # type: ignore[assignment]

        expected_duration = sum(float(probe.get("duration") or 0) for probe in probes)
        report = validate_final(
            final_local,
            expected_scene_count=len(scenes),
            expected_duration=expected_duration,
            expected_width=width,
            expected_height=height,
            thumbnail_path=thumbnail_local,
        )
        if not report["passed"]:
            project.status = "FAILED"
            project.error = "Final validation failed: " + "; ".join(report.get("errors") or [])
            project.report = report
            await db.commit()
            await notify(
                db,
                user_id=project.user_id,
                project_id=project.id,
                kind="project_failed",
                title="Final validation failed",
                body=project.error[:400],
            )
            raise ValidationError(project.error)

        project.status = "VALIDATING"
        await db.commit()
        keys = storage_keys(project.user_id, project.id)
        await storage.save_file(keys["final"], final_local)
        if thumbnail_local and thumbnail_local.exists():
            await storage.save_file(keys["thumbnail"], thumbnail_local)

        probe = report["metadata"]
        existing = (
            await db.execute(
                select(Video).where(Video.project_id == project.id, Video.kind == "final")
            )
        ).scalar_one_or_none()
        has_audio = bool(probe.get("has_audio"))
        video = existing or Video(user_id=project.user_id, project_id=project.id, kind="final")
        video.filename = f"{project.title[:80].strip() or 'video'}.mp4"
        video.storage_key = keys["final"]
        video.thumbnail_key = keys["thumbnail"]
        video.size_bytes = int(report.get("size_bytes") or final_local.stat().st_size)
        video.duration_seconds = float(probe.get("duration") or expected_duration)
        video.width = int(probe.get("width") or width)
        video.height = int(probe.get("height") or height)
        video.has_audio = has_audio
        video.checksum_sha256 = report.get("checksum_sha256")
        video.deleted_at = None
        if existing is None:
            db.add(video)
            await db.commit()
            await db.refresh(video)

        project.final_video_id = video.id
        project.status = "COMPLETED"
        project.progress = 100
        project.completed_at = utcnow()
        project.error = None
        project.report = {
            "validation": report,
            "scenes": [
                {
                    "scene_number": scene.scene_number,
                    "duration": scene.duration_actual,
                    "resolution": f"{scene.width}x{scene.height}",
                    "attempts": scene.attempt_count,
                    "generation_id": scene.generation_id,
                    "checksum": scene.output_checksum,
                }
                for scene in scenes
            ],
        }
        await db.commit()
        await record_usage(
            db,
            user_id=project.user_id,
            project_id=project.id,
            kind="video_completed",
            quantity=1,
            unit="video",
            meta={"duration": video.duration_seconds},
        )
        await notify(
            db,
            user_id=project.user_id,
            project_id=project.id,
            kind="project_completed",
            title="Your video is ready",
            body=f"\"{project.title}\" finished and passed validation. Open your library to watch or download it.",
        )
        shutil.rmtree(render_dir, ignore_errors=True)
        return {
            "video_id": video.id,
            "duration": video.duration_seconds,
            "scenes": len(scenes),
            "provider": project.provider,
        }

    @staticmethod
    def _target_resolution(project: Project) -> tuple[int, int]:
        try:
            width_text, height_text = project.resolution.lower().split("x")
            width, height = int(width_text), int(height_text)
            if 320 <= width <= 3840 and 240 <= height <= 2160:
                return width, height
        except Exception:
            pass
        return {
            "portrait": (720, 1280),
            "square": (720, 720),
        }.get(project.orientation, (1280, 720))
