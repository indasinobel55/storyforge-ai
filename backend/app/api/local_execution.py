from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, Response
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.util import probe_video, sha256_file
from agent.scenes.spec import SceneSpec
from agent.validation.validator import validate_clip, validate_final

from ..config import settings
from ..database import get_db
from ..deps import require_user
from ..models import (
    Character,
    GenerationAttempt,
    Job,
    LocalExecutionToken,
    Project,
    ProviderAccount,
    Scene,
    User,
    Video,
)
from ..schemas import (
    LocalCheckpointIn,
    LocalTokenCreateIn,
    LocalTokenCreatedOut,
    LocalTokenOut,
    MessageOut,
)
from ..security import create_signed_token, new_token, token_hash, utcnow
from ..services.project_service import notify, recompute_progress, record_usage
from ..services.queue import enqueue_job, project_active_job
from ..services.storage import storage

router = APIRouter(prefix="/execution", tags=["local-execution"])

ACTIVE_PROJECT_STATUSES = {"PLANNING", "QUEUED", "GENERATING", "PROCESSING", "VALIDATING"}
UPLOAD_MAX_BYTES = 1024 * 1024 * 1024
SCENE_UPDATE_FIELDS = {
    "status",
    "generation_id",
    "provider_status",
    "attempt_count",
    "download_status",
    "output_checksum",
    "error",
    "duration_actual",
    "width",
    "height",
    "fps",
    "mode",
    "parent_generation_id",
    "provider_duration",
}


# ---------------------------------------------------------------- auth helpers


async def local_user(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)
) -> tuple[User, LocalExecutionToken]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Local execution token required")
    raw = authorization.split(" ", 1)[1].strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Local execution token required")
    result = await db.execute(
        select(LocalExecutionToken).where(
            LocalExecutionToken.token_hash == token_hash(raw),
            LocalExecutionToken.revoked_at.is_(None),
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid local execution token")
    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid local execution token")
    token.last_used_at = utcnow()
    await db.commit()
    return user, token


async def _require_local_mode() -> None:
    if not settings.local_execution_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Server execution mode is 'cloud'. Set EXECUTION_MODE=local and restart the backend "
                "to allow local workers to claim jobs."
            ),
        )


# ------------------------------------------------------------ token management


@router.post("/token", response_model=LocalTokenCreatedOut, status_code=201)
async def create_local_token(
    payload: LocalTokenCreateIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> LocalTokenCreatedOut:
    raw = new_token(32)
    token = LocalExecutionToken(
        user_id=user.id, label=payload.label.strip() or "Local worker", token_hash=token_hash(raw)
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return LocalTokenCreatedOut(
        id=token.id,
        label=token.label,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
        token=raw,
    )


@router.get("/tokens", response_model=list[LocalTokenOut])
async def list_local_tokens(
    user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> list[LocalTokenOut]:
    tokens = list(
        (
            await db.execute(
                select(LocalExecutionToken)
                .where(LocalExecutionToken.user_id == user.id, LocalExecutionToken.revoked_at.is_(None))
                .order_by(LocalExecutionToken.created_at.desc())
            )
        ).scalars()
    )
    return [LocalTokenOut.model_validate(token) for token in tokens]


@router.delete("/tokens/{token_id}", response_model=MessageOut)
async def revoke_local_token(
    token_id: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> MessageOut:
    token = await db.get(LocalExecutionToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(status_code=404, detail="Token not found")
    token.revoked_at = utcnow()
    await db.commit()
    return MessageOut(message="Local execution token revoked")


@router.get("/status", response_model=dict)
async def execution_status(
    user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    tokens = (
        await db.execute(
            select(LocalExecutionToken).where(
                LocalExecutionToken.user_id == user.id, LocalExecutionToken.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    return {
        "execution_mode": settings.effective_execution_mode,
        "cloud_workers_enabled": settings.cloud_execution_enabled,
        "local_workers_enabled": settings.local_execution_enabled,
        "active_tokens": len(tokens),
        "instructions": (
            "Run: python -m local_agent --api-url <backend-url> --token <token>"
            if settings.local_execution_enabled
            else "Set EXECUTION_MODE=local on the backend to use a local worker."
        ),
    }


# ---------------------------------------------------------------- job protocol


@router.get("/health", response_model=dict)
async def local_health() -> dict:
    return {"execution_mode": settings.effective_execution_mode}


@router.post("/claim", response_model=None)
async def _claim(user_and_token=Depends(local_user), db: AsyncSession = Depends(get_db)):
    await _require_local_mode()
    user, token = user_and_token
    now = utcnow()
    lease_seconds = max(60, settings.worker_lease_seconds)
    for _ in range(5):
        result = await db.execute(
            select(Job)
            .where(
                Job.user_id == user.id,
                or_(
                    (Job.status == "QUEUED") & (Job.available_at <= now),
                    (Job.status == "RUNNING")
                    & Job.lease_expires_at.is_not(None)
                    & (Job.lease_expires_at < now),
                ),
            )
            .order_by(Job.priority.asc(), Job.available_at.asc(), Job.created_at.asc())
            .limit(1)
        )
        candidate = result.scalar_one_or_none()
        if candidate is None:
            return Response(status_code=204)
        update_result = await db.execute(
            update(Job)
            .where(
                Job.id == candidate.id,
                or_(
                    (Job.status == "QUEUED") & (Job.available_at <= now),
                    (Job.status == "RUNNING")
                    & Job.lease_expires_at.is_not(None)
                    & (Job.lease_expires_at < now),
                ),
            )
            .values(
                status="RUNNING",
                locked_by=f"local:{token.id}",
                locked_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempts=Job.attempts + 1,
                started_at=func.coalesce(Job.started_at, now),
                updated_at=now,
            )
        )
        await db.commit()
        if not update_result.rowcount:
            continue
        await db.refresh(candidate)
        project = await db.get(Project, candidate.project_id) if candidate.project_id else None
        if project is None:
            candidate.status = "FAILED"
            candidate.last_error = "Project not found"
            await db.commit()
            return Response(status_code=204)
        project.execution_mode = "local"
        project.executor = f"local:{token.label}"[:120]
        await db.commit()

        scenes = list(
            (
                await db.execute(
                    select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)
                )
            ).scalars()
        )
        characters = list(
            (
                await db.execute(
                    select(Character)
                    .where(Character.project_id == project.id)
                    .order_by(Character.position)
                )
            ).scalars()
        )
        account = (
            await db.execute(
                select(ProviderAccount).where(
                    ProviderAccount.user_id == user.id, ProviderAccount.provider == project.provider
                )
            )
        ).scalar_one_or_none()

        scene_payload = []
        for scene in scenes:
            video = (
                await db.execute(
                    select(Video).where(Video.scene_id == scene.id, Video.kind == "scene")
                )
            ).scalar_one_or_none()
            scene_payload.append(
                {
                    **jsonable_encoder(scene),
                    "video_url": (
                        f"/api/videos/{video.id}/stream?token="
                        + create_signed_token(
                            f"{video.id}|{video.user_id}", settings.signed_url_ttl_seconds, "file"
                        )
                        if video is not None
                        else None
                    ),
                    "thumbnail_url": (
                        f"/api/videos/{video.id}/thumbnail?token="
                        + create_signed_token(
                            f"{video.id}|{video.user_id}", settings.signed_url_ttl_seconds, "file"
                        )
                        if video is not None and video.thumbnail_key
                        else None
                    ),
                }
            )

        config = dict(project.generation_config or {})
        asset_urls = {}
        for key_name in ("music_key", "voiceover_key"):
            key = config.get(key_name)
            if key:
                asset_urls[key_name] = (
                    f"/api/execution/assets?key={key}&token="
                    + create_signed_token(f"{user.id}|{key}", settings.signed_url_ttl_seconds, "asset")
                )

        payload = {
            "job": jsonable_encoder(candidate),
            "project": jsonable_encoder(project),
            "scenes": scene_payload,
            "characters": [jsonable_encoder(character) for character in characters],
            "provider": {
                "provider": project.provider,
                "status": account.status if account else "disconnected",
                "account_ref": account.account_ref if account else None,
                "usage": account.usage if account else None,
            },
            "assets": asset_urls,
            "execution_mode": settings.effective_execution_mode,
        }
        return payload
    return Response(status_code=204)


async def _job_for_token(db: AsyncSession, job_id: str, user_id: str, token_id: str) -> Job:
    job = await db.get(Job, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "RUNNING" or job.locked_by != f"local:{token_id}":
        raise HTTPException(status_code=409, detail="Job is not claimed by this local worker")
    return job


@router.post("/jobs/{job_id}/heartbeat", response_model=dict)
async def heartbeat(
    job_id: str,
    user_and_token=Depends(local_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, token = user_and_token
    job = await _job_for_token(db, job_id, user.id, token.id)
    job.lease_expires_at = utcnow() + timedelta(seconds=max(60, settings.worker_lease_seconds))
    project = await db.get(Project, job.project_id) if job.project_id else None
    await db.commit()
    return {
        "job_status": job.status,
        "project_status": project.status if project else None,
        "progress": project.progress if project else None,
    }


@router.get("/jobs/{job_id}/state", response_model=dict)
async def job_state(
    job_id: str,
    user_and_token=Depends(local_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, token = user_and_token
    job = await db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    project = await db.get(Project, job.project_id) if job.project_id else None
    scenes = (
        list(
            (
                await db.execute(
                    select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)
                )
            ).scalars()
        )
        if project
        else []
    )
    return {
        "job": jsonable_encoder(job),
        "project": jsonable_encoder(project) if project else None,
        "scenes": [jsonable_encoder(scene) for scene in scenes],
    }


@router.post("/jobs/{job_id}/checkpoint", response_model=dict)
async def checkpoint(
    job_id: str,
    payload: LocalCheckpointIn,
    user_and_token=Depends(local_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, token = user_and_token
    job = await _job_for_token(db, job_id, user.id, token.id)
    project = await db.get(Project, job.project_id) if job.project_id else None
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.plan_scenes is not None:
        scenes = list((await db.execute(select(Scene).where(Scene.project_id == project.id))).scalars())
        if any(scene.status == "SUCCEEDED" for scene in scenes):
            raise HTTPException(status_code=409, detail="Cannot replace scenes after generation started")
        for scene in scenes:
            await db.execute(delete(GenerationAttempt).where(GenerationAttempt.scene_id == scene.id))
            await db.delete(scene)
        validated: list[SceneSpec] = []
        for index, raw in enumerate(payload.plan_scenes):
            if not isinstance(raw, dict):
                raise HTTPException(status_code=422, detail="Invalid scene payload")
            data = dict(raw)
            data.setdefault("scene_number", index + 1)
            validated.append(SceneSpec.model_validate(data))
        for spec in validated:
            db.add(
                Scene(
                    project_id=project.id,
                    scene_number=spec.scene_number,
                    title=spec.title,
                    narrative_purpose=spec.narrative_purpose,
                    duration=spec.duration,
                    environment=spec.environment,
                    character_presence=spec.character_presence,
                    actions=spec.actions,
                    camera=spec.camera,
                    lighting=spec.lighting,
                    visual_style=spec.visual_style,
                    prompt=spec.prompt,
                    negative_prompt=spec.negative_prompt,
                    reference_assets=spec.reference_assets,
                    continuity=spec.continuity,
                    previous_scene_relationship=spec.previous_scene_relationship,
                    next_scene_relationship=spec.next_scene_relationship,
                    narration=spec.narration,
                    dialogue=spec.dialogue,
                    status="PENDING",
                )
            )
        if payload.characters is not None:
            await db.execute(delete(Character).where(Character.project_id == project.id))
            for position, raw in enumerate(payload.characters):
                db.add(
                    Character(
                        project_id=project.id,
                        name=str(raw.get("name") or "Character")[:120],
                        description=str(raw.get("description") or ""),
                        age_range=raw.get("age_range"),
                        appearance=raw.get("appearance") or {},
                        voice_description=raw.get("voice_description"),
                        reference_notes=raw.get("reference_notes"),
                        position=position,
                    )
                )
        project.plan_revision += 1
        if payload.logline:
            project.logline = payload.logline[:500]
        project.status = "QUEUED" if project.auto_start else "AWAITING_APPROVAL"
        project.error = None
        await db.commit()
        await notify(
            db,
            user_id=project.user_id,
            project_id=project.id,
            kind="planning_completed",
            title="Scene plan ready (local worker)",
            body=f"{len(validated)} scenes planned for \"{project.title}\".",
        )
        if project.auto_start:
            await enqueue_job(
                db,
                user_id=project.user_id,
                project_id=project.id,
                kind="GENERATE",
                idempotency_key=f"generate:{project.id}:{project.plan_revision}",
                payload={"plan_revision": project.plan_revision},
                max_attempts=settings.worker_max_attempts,
            )

    if payload.scene_updates:
        scenes = list(
            (
                await db.execute(
                    select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)
                )
            ).scalars()
        )
        by_id = {scene.id: scene for scene in scenes}
        by_number = {scene.scene_number: scene for scene in scenes}
        for update_payload in payload.scene_updates:
            if not isinstance(update_payload, dict):
                continue
            scene = by_id.get(update_payload.get("scene_id")) or by_number.get(
                update_payload.get("scene_number")
            )
            if scene is None:
                continue
            if update_payload.get("status") == "SUCCEEDED":
                if not scene.local_path:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Scene {scene.scene_number} cannot be SUCCEEDED before its clip is uploaded",
                    )
            for field in SCENE_UPDATE_FIELDS:
                if field in update_payload:
                    value = update_payload[field]
                    if field == "status":
                        allowed = {
                            "PENDING",
                            "SUBMITTING",
                            "GENERATING",
                            "DOWNLOADING",
                            "SUCCEEDED",
                            "FAILED",
                        }
                        if value not in allowed:
                            raise HTTPException(status_code=422, detail=f"Invalid scene status {value}")
                    setattr(scene, field, value)
            if update_payload.get("status") == "SUCCEEDED":
                scene.completed_at = scene.completed_at or utcnow()
        await db.commit()

    if payload.project_status:
        allowed = {"PLANNING", "GENERATING", "PROCESSING", "VALIDATING", "QUEUED", "FAILED", "PAUSED"}
        if payload.project_status not in allowed:
            raise HTTPException(status_code=422, detail="Invalid project status from worker")
        project.status = payload.project_status
    if payload.progress is not None:
        project.progress = max(0, min(100, payload.progress))
    if payload.message:
        project.error = payload.message[:4000] if payload.project_status == "FAILED" else project.error
    await db.commit()

    if payload.enqueue_assemble:
        project.status = "PROCESSING"
        await db.commit()
        await enqueue_job(
            db,
            user_id=project.user_id,
            project_id=project.id,
            kind="ASSEMBLE",
            idempotency_key=f"assemble:{project.id}:{project.plan_revision}:local",
            payload={"plan_revision": project.plan_revision},
            max_attempts=settings.worker_max_attempts,
            revive=True,
        )
    await recompute_progress(db, project)
    await db.refresh(project)
    return {
        "project_status": project.status,
        "progress": project.progress,
        "job_status": job.status,
        "server_now": utcnow().isoformat(),
    }


@router.post("/jobs/{job_id}/complete", response_model=dict)
async def complete_local_job(
    job_id: str,
    result: dict | None = None,
    user_and_token=Depends(local_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, token = user_and_token
    job = await _job_for_token(db, job_id, user.id, token.id)
    job.status = "SUCCEEDED"
    job.result = result or {}
    job.finished_at = utcnow()
    job.locked_by = None
    job.locked_at = None
    job.lease_expires_at = None
    project = await db.get(Project, job.project_id) if job.project_id else None
    if project and job.kind == "GENERATE" and (result or {}).get("all_scenes_succeeded"):
        project.status = "PROCESSING"
        await enqueue_job(
            db,
            user_id=user.id,
            project_id=project.id,
            kind="ASSEMBLE",
            idempotency_key=f"assemble:{project.id}:{project.plan_revision}:local",
            payload={"plan_revision": project.plan_revision},
            max_attempts=settings.worker_max_attempts,
            revive=True,
        )
    await db.commit()
    return {"status": "ok"}


@router.post("/jobs/{job_id}/fail", response_model=dict)
async def fail_local_job(
    job_id: str,
    payload: dict,
    user_and_token=Depends(local_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, token = user_and_token
    job = await _job_for_token(db, job_id, user.id, token.id)
    error = str(payload.get("error") or "Local worker failed")[:8000]
    job.last_error = error
    job.locked_by = None
    job.locked_at = None
    job.lease_expires_at = None
    terminal = job.attempts >= job.max_attempts
    if terminal:
        job.status = "FAILED"
        job.finished_at = utcnow()
    else:
        job.status = "QUEUED"
        job.available_at = utcnow() + timedelta(seconds=15)
    project = await db.get(Project, job.project_id) if job.project_id else None
    if project and terminal:
        project.status = "FAILED"
        project.error = error[:4000]
        await notify(
            db,
            user_id=user.id,
            project_id=project.id,
            kind="project_failed",
            title="Project failed (local worker)",
            body=error[:300],
        )
    await db.commit()
    return {"status": "failed" if terminal else "retry"}


# --------------------------------------------------------------- media upload


async def _save_upload(upload: UploadFile, destination: Path, max_bytes: int = UPLOAD_MAX_BYTES) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    size = 0
    with temp.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                handle.close()
                temp.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file is too large")
            handle.write(chunk)
    temp.replace(destination)
    return size


@router.post("/jobs/{job_id}/upload/scene", response_model=dict)
async def upload_scene(
    job_id: str,
    scene_id: str = Query(...),
    kind: str = Query(default="video", pattern="^(video|last_frame)$"),
    file: UploadFile = File(...),
    user_and_token=Depends(local_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, token = user_and_token
    job = await _job_for_token(db, job_id, user.id, token.id)
    project = await db.get(Project, job.project_id) if job.project_id else None
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    scene = await db.get(Scene, scene_id)
    if scene is None or scene.project_id != project.id:
        raise HTTPException(status_code=404, detail="Scene not found")

    if kind == "video":
        key = f"users/{project.user_id}/projects/{project.id}/scenes/scene_{scene.scene_number:03d}.mp4"
    else:
        key = f"users/{project.user_id}/projects/{project.id}/scenes/scene_{scene.scene_number:03d}_last.png"
    destination = settings.storage_path / "_uploads" / job.id / Path(key).name
    size = await _save_upload(file, destination)

    if kind == "video":
        report = validate_clip(destination)
        if not report["passed"]:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=f"Uploaded scene clip is invalid: {report['checks']}")
        await storage.save_file(key, destination)
        probe = probe_video(destination)
        scene.local_path = key
        scene.output_checksum = sha256_file(destination)
        scene.duration_actual = float(probe.get("duration") or scene.duration)
        scene.width = int(probe.get("width") or 0)
        scene.height = int(probe.get("height") or 0)
        scene.fps = probe.get("fps")
        scene.download_status = "DOWNLOADED"
        await db.commit()
        existing = (
            await db.execute(select(Video).where(Video.scene_id == scene.id, Video.kind == "scene"))
        ).scalar_one_or_none()
        video = existing or Video(
            user_id=project.user_id, project_id=project.id, scene_id=scene.id, kind="scene"
        )
        video.filename = f"scene_{scene.scene_number:03d}.mp4"
        video.storage_key = key
        video.thumbnail_key = scene.last_frame_path
        video.size_bytes = destination.stat().st_size
        video.duration_seconds = scene.duration_actual
        video.width = scene.width
        video.height = scene.height
        video.has_audio = bool(probe.get("has_audio"))
        video.checksum_sha256 = scene.output_checksum
        video.deleted_at = None
        if existing is None:
            db.add(video)
        await db.commit()
    else:
        if size <= 0:
            raise HTTPException(status_code=422, detail="Empty last-frame image")
        await storage.save_file(key, destination)
        scene.last_frame_path = key
        await db.commit()

    destination.unlink(missing_ok=True)
    return {"ok": True, "key": key, "size_bytes": size}


@router.post("/jobs/{job_id}/upload/final", response_model=dict)
async def upload_final(
    job_id: str,
    file: UploadFile = File(...),
    thumbnail: UploadFile | None = File(default=None),
    user_and_token=Depends(local_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, token = user_and_token
    job = await _job_for_token(db, job_id, user.id, token.id)
    project = await db.get(Project, job.project_id) if job.project_id else None
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = list(
        (
            await db.execute(
                select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)
            )
        ).scalars()
    )

    upload_dir = settings.storage_path / "_uploads" / job.id
    final_path = upload_dir / "final.mp4"
    await _save_upload(file, final_path)
    thumb_path = None
    if thumbnail is not None:
        thumb_path = upload_dir / "thumbnail.jpg"
        await _save_upload(thumbnail, thumb_path, max_bytes=20 * 1024 * 1024)

    expected_duration = sum(float(scene.duration_actual or scene.duration) for scene in scenes)
    try:
        width_text, height_text = project.resolution.lower().split("x")
        width, height = int(width_text), int(height_text)
    except Exception:
        width, height = 1280, 720
    report = validate_final(
        final_path,
        expected_scene_count=len(scenes),
        expected_duration=expected_duration,
        expected_width=width,
        expected_height=height,
        thumbnail_path=thumb_path if thumb_path and thumb_path.exists() else None,
    )
    if not report["passed"]:
        final_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail={"message": "Final video validation failed", "report": report})

    base = f"users/{project.user_id}/projects/{project.id}"
    await storage.save_file(f"{base}/final.mp4", final_path)
    thumb_key = None
    if thumb_path and thumb_path.exists():
        thumb_key = f"{base}/thumbnail.jpg"
        await storage.save_file(thumb_key, thumb_path)

    probe = report["metadata"]
    existing = (
        await db.execute(select(Video).where(Video.project_id == project.id, Video.kind == "final"))
    ).scalar_one_or_none()
    video = existing or Video(user_id=project.user_id, project_id=project.id, kind="final")
    video.filename = f"{project.title[:80].strip() or 'video'}.mp4"
    video.storage_key = f"{base}/final.mp4"
    video.thumbnail_key = thumb_key
    video.size_bytes = int(report.get("size_bytes") or final_path.stat().st_size)
    video.duration_seconds = float(probe.get("duration") or expected_duration)
    video.width = int(probe.get("width") or width)
    video.height = int(probe.get("height") or height)
    video.has_audio = bool(probe.get("has_audio"))
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
                "generation_id": scene.generation_id,
                "checksum": scene.output_checksum,
            }
            for scene in scenes
        ],
        "executed_on": "local",
    }
    await db.commit()
    await record_usage(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="video_completed",
        quantity=1,
        unit="video",
        meta={"duration": video.duration_seconds, "mode": "local"},
    )
    await notify(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="project_completed",
        title="Your video is ready",
        body=f"\"{project.title}\" finished locally and passed server validation.",
    )
    shutil.rmtree(upload_dir, ignore_errors=True)
    return {"ok": True, "video_id": video.id, "validation": report}


@router.get("/assets")
async def download_asset(
    key: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    from ..security import verify_signed_token

    subject = verify_signed_token(token, "asset")
    if not subject:
        raise HTTPException(status_code=403, detail="Invalid or expired asset token")
    user_id, _, asset_key = subject.partition("|")
    if asset_key != key or not key.startswith(f"users/{user_id}/"):
        raise HTTPException(status_code=403, detail="Invalid asset token")
    try:
        path = storage.local_path(key)
    except Exception:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path, filename=Path(key).name)
