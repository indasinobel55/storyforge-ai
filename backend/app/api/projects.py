from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import owned_project, require_user
from ..models import Activity, Character, GenerationAttempt, Job, Project, Scene, User, Video
from ..schemas import (
    ActivityOut,
    ActivityListOut,
    CharacterOut,
    JobOut,
    MediaAssetOut,
    MessageOut,
    ProjectCreateIn,
    ProjectDetailOut,
    ProjectListOut,
    ProjectOut,
    ProjectUpdateIn,
    SceneOut,
    SceneReorderIn,
    SceneUpdateIn,
)
from ..security import generation_limiter, utcnow
from ..services.planning_service import approve_plan, regenerate_scene_prompt
from ..services.project_service import (
    ensure_simulated_account,
    activity_for_user,
    activity_count_for_user,
    notify,
    recompute_progress,
)
from ..services.queue import cancel_project_jobs, enqueue_job, project_active_job
from ..services.storage import storage

router = APIRouter(prefix="/projects", tags=["projects"])

EDITABLE_STATUSES = {"DRAFT", "AWAITING_APPROVAL", "FAILED", "PAUSED"}
ACTIVE_STATUSES = {"PLANNING", "QUEUED", "GENERATING", "DOWNLOADING", "PROCESSING", "VALIDATING"}


def _limit(user: User) -> None:
    allowed, retry_after = generation_limiter.check(user.id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Generation rate limit reached. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


async def _project_detail(db: AsyncSession, project: Project) -> ProjectDetailOut:
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
                select(Character).where(Character.project_id == project.id).order_by(Character.position)
            )
        ).scalars()
    )
    job = await project_active_job(db, project.id)
    return ProjectDetailOut(
        **ProjectOut.model_validate(project).model_dump(),
        scenes=[SceneOut.model_validate(scene) for scene in scenes],
        characters=[CharacterOut.model_validate(character) for character in characters],
        active_job=JobOut.model_validate(job) if job else None,
    )


@router.post("", response_model=ProjectDetailOut, status_code=201)
async def create_project(
    payload: ProjectCreateIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    _limit(user)
    if payload.provider == "taaft" and not settings.taaft_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "TAAFT automation is disabled pending written provider authorization. "
                "Use the simulated provider or see TAAFT_INTEGRATION_FEASIBILITY.md."
            ),
        )
    if payload.provider == "simulated":
        await ensure_simulated_account(db, user.id)

    active_count = (
        await db.execute(
            select(func.count(Project.id)).where(
                Project.user_id == user.id, Project.status.in_(list(ACTIVE_STATUSES))
            )
        )
    ).scalar_one()
    if active_count >= settings.max_active_projects_per_user and not payload.start_planning:
        raise HTTPException(
            status_code=429,
            detail="You already have an active project. Wait for it to finish or pause it.",
        )

    scene_seconds = min(payload.scene_seconds, settings.max_scene_seconds)
    project = Project(
        user_id=user.id,
        title=payload.title.strip(),
        script=payload.script,
        genre=payload.genre,
        style=payload.style,
        orientation=payload.orientation,
        aspect_ratio=payload.aspect_ratio,
        target_duration_seconds=payload.target_duration_seconds,
        target_scene_count=min(payload.target_scene_count, settings.max_scenes_per_project),
        scene_seconds=scene_seconds,
        tier=payload.tier,
        resolution=payload.resolution,
        quality=payload.quality,
        provider=payload.provider,
        execution_mode=settings.effective_execution_mode,
        auto_start=payload.auto_start,
        voiceover_instructions=payload.voiceover_instructions,
        music_instructions=payload.music_instructions,
        reference_notes=payload.reference_notes,
        generation_config={"transition": "fade" if payload.auto_start else "none"},
        status="DRAFT",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    for position, character in enumerate(payload.characters):
        db.add(
            Character(
                project_id=project.id,
                name=character.name,
                description=character.description,
                age_range=character.age_range,
                appearance=character.appearance or {},
                voice_description=character.voice_description,
                reference_notes=character.reference_notes,
                position=position,
            )
        )
    await db.commit()

    if payload.start_planning:
        project.status = "PLANNING"
        await db.commit()
        await enqueue_job(
            db,
            user_id=user.id,
            project_id=project.id,
            kind="PLAN",
            idempotency_key=f"plan:{project.id}:{project.plan_revision + 1}",
            payload={"plan_revision": project.plan_revision + 1},
            max_attempts=settings.worker_max_attempts,
            revive=True,
        )
    await db.refresh(project)
    return await _project_detail(db, project)


@router.get("", response_model=ProjectListOut)
async def list_projects(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectListOut:
    query = select(Project).where(Project.user_id == user.id)
    count_query = select(func.count(Project.id)).where(Project.user_id == user.id)
    if status_filter:
        query = query.where(Project.status == status_filter)
        count_query = count_query.where(Project.status == status_filter)
    total = (await db.execute(count_query)).scalar_one()
    projects = list(
        (
            await db.execute(
                query.order_by(Project.updated_at.desc()).limit(limit).offset(offset)
            )
        ).scalars()
    )
    return ProjectListOut(items=[ProjectOut.model_validate(project) for project in projects], total=total)


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project: Project = Depends(owned_project), db: AsyncSession = Depends(get_db)
) -> ProjectDetailOut:
    return await _project_detail(db, project)


@router.patch("/{project_id}", response_model=ProjectDetailOut)
async def update_project(
    payload: ProjectUpdateIn,
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    if project.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Project cannot be edited while generation is active")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return await _project_detail(db, project)


@router.delete("/{project_id}", response_model=MessageOut)
async def delete_project(
    project: Project = Depends(owned_project),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await cancel_project_jobs(db, project.id)
    project_dir = settings.storage_path / "users" / user.id / "projects" / project.id
    await db.execute(delete(Project).where(Project.id == project.id))
    await db.commit()
    shutil.rmtree(project_dir, ignore_errors=True)
    return MessageOut(message="Project deleted")


@router.post("/{project_id}/plan", response_model=ProjectDetailOut)
async def start_planning(
    project: Project = Depends(owned_project),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    _limit(user)
    if project.status in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Project is already active")
    if project.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="Project is already completed")
    scenes = list((await db.execute(select(Scene).where(Scene.project_id == project.id))).scalars())
    if any(scene.status == "SUCCEEDED" for scene in scenes):
        raise HTTPException(status_code=409, detail="Cannot replan after clips were generated")
    project.status = "PLANNING"
    project.error = None
    await db.commit()
    await enqueue_job(
        db,
        user_id=user.id,
        project_id=project.id,
        kind="PLAN",
        idempotency_key=f"plan:{project.id}:{project.plan_revision + 1}",
        payload={"plan_revision": project.plan_revision + 1},
        max_attempts=settings.worker_max_attempts,
        revive=True,
    )
    await db.refresh(project)
    return await _project_detail(db, project)


@router.post("/{project_id}/approve", response_model=ProjectDetailOut)
async def approve_project(
    project: Project = Depends(owned_project),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    _limit(user)
    if project.status not in {"AWAITING_APPROVAL", "DRAFT", "FAILED", "PAUSED"}:
        raise HTTPException(status_code=409, detail=f"Project cannot be approved from status {project.status}")
    await approve_plan(db, project)
    await db.refresh(project)
    return await _project_detail(db, project)


@router.post("/{project_id}/generate", response_model=ProjectDetailOut)
async def start_generation(
    project: Project = Depends(owned_project),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    return await approve_project(project=project, user=user, db=db)


@router.post("/{project_id}/pause", response_model=ProjectDetailOut)
async def pause_project(
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    if project.status not in {"QUEUED", "GENERATING", "PROCESSING", "PLANNING"}:
        raise HTTPException(status_code=409, detail="Project is not running")
    project.status = "PAUSED"
    await db.commit()
    await notify(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="project_paused",
        title="Generation paused",
        body=f"\"{project.title}\" will stop after the current scene checkpoint.",
    )
    await db.refresh(project)
    return await _project_detail(db, project)


@router.post("/{project_id}/resume", response_model=ProjectDetailOut)
async def resume_project(
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    if project.status != "PAUSED":
        raise HTTPException(status_code=409, detail="Project is not paused")
    project.status = "QUEUED"
    await db.commit()
    await enqueue_job(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="GENERATE",
        idempotency_key=f"generate:{project.id}:{project.plan_revision}",
        payload={"plan_revision": project.plan_revision},
        max_attempts=settings.worker_max_attempts,
        revive=True,
    )
    await notify(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="project_resumed",
        title="Generation resumed",
        body=f"\"{project.title}\" resumed from its last checkpoint.",
    )
    await db.refresh(project)
    return await _project_detail(db, project)


@router.post("/{project_id}/cancel", response_model=ProjectDetailOut)
async def cancel_project(
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    if project.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="Completed projects cannot be cancelled")
    project.status = "CANCELLED"
    project.cancelled_at = utcnow()
    await db.commit()
    await cancel_project_jobs(db, project.id)
    await notify(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="project_cancelled",
        title="Generation cancelled",
        body=f"\"{project.title}\" was cancelled. Completed clips were preserved.",
    )
    await db.refresh(project)
    return await _project_detail(db, project)


@router.post("/{project_id}/retry", response_model=ProjectDetailOut)
async def retry_project(
    project: Project = Depends(owned_project),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    _limit(user)
    scenes = list(
        (
            await db.execute(
                select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)
            )
        ).scalars()
    )
    if not scenes:
        raise HTTPException(status_code=409, detail="No scenes to retry")
    failed_or_missing = [
        scene for scene in scenes if scene.status != "SUCCEEDED" or not scene.local_path
    ]
    if failed_or_missing:
        for scene in failed_or_missing:
            scene.status = "PENDING"
            scene.error = None
            scene.attempt_count = 0
            scene.generation_id = None
            scene.provider_status = None
            scene.download_status = "PENDING"
            scene.started_at = None
            scene.completed_at = None
        project.status = "QUEUED"
        project.error = None
        await db.commit()
        await enqueue_job(
            db,
            user_id=project.user_id,
            project_id=project.id,
            kind="GENERATE",
            idempotency_key=f"generate:{project.id}:{project.plan_revision}",
            payload={"plan_revision": project.plan_revision},
            max_attempts=settings.worker_max_attempts,
            revive=True,
        )
    else:
        project.status = "PROCESSING"
        project.error = None
        await db.commit()
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
    await db.refresh(project)
    return await _project_detail(db, project)


@router.get("/{project_id}/report", response_model=dict)
async def get_report(project: Project = Depends(owned_project)) -> dict:
    return {
        "project_id": project.id,
        "status": project.status,
        "progress": project.progress,
        "report": project.report,
        "error": project.error,
    }


@router.get("/{project_id}/activity", response_model=ActivityListOut)
async def list_activity(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    project: Project = Depends(owned_project),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityListOut:
    """Return the owning user's activity events for this project.

    Only the project owner can read these events, and no events are
    fabricated before the backend has recorded them.
    """
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your project")
    total = await activity_count_for_user(db, user_id=user.id, project_id=project.id)
    items = [
        ActivityOut.model_validate(item)
        for item in await activity_for_user(
            db, user_id=user.id, project_id=project.id, limit=limit, offset=offset
        )
    ]
    return ActivityListOut(items=items, total=total)


@router.get("/{project_id}/activity/replay", response_model=ActivityListOut)
async def replay_activity(
    since: datetime | None = Query(default=None, alias="since"),
    project: Project = Depends(owned_project),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityListOut:
    """Return all activity events for this project ordered oldest-first,
    optionally limited to events created at or after ``since``.
    """
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your project")
    query = select(Activity).where(Activity.project_id == project.id)
    if since is not None:
        query = query.where(Activity.created_at >= since)
    rows = list((await db.execute(query.order_by(Activity.created_at.asc()))).scalars())
    return ActivityListOut(
        items=[ActivityOut.model_validate(item) for item in rows],
        total=len(rows),
    )


@router.patch("/{project_id}/scenes/{scene_id}", response_model=SceneOut)
async def update_scene(
    scene_id: str,
    payload: SceneUpdateIn,
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> SceneOut:
    if project.status in ACTIVE_STATUSES or project.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="Scenes cannot be edited while generation is active")
    scene = await db.get(Scene, scene_id)
    if scene is None or scene.project_id != project.id:
        raise HTTPException(status_code=404, detail="Scene not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(scene, field, value)
    await db.commit()
    await db.refresh(scene)
    return SceneOut.model_validate(scene)


@router.post("/{project_id}/scenes/{scene_id}/regenerate-prompt", response_model=SceneOut)
async def regenerate_prompt(
    scene_id: str,
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> SceneOut:
    scene = await db.get(Scene, scene_id)
    if scene is None or scene.project_id != project.id:
        raise HTTPException(status_code=404, detail="Scene not found")
    if project.status in ACTIVE_STATUSES or project.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="Scenes cannot be regenerated while generation is active")
    scene = await regenerate_scene_prompt(db, project, scene)
    return SceneOut.model_validate(scene)


@router.post("/{project_id}/scenes/{scene_id}/retry", response_model=ProjectDetailOut)
async def retry_scene(
    scene_id: str,
    project: Project = Depends(owned_project),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    _limit(user)
    if project.status in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Project is already running")
    scene = await db.get(Scene, scene_id)
    if scene is None or scene.project_id != project.id:
        raise HTTPException(status_code=404, detail="Scene not found")
    if scene.status == "SUCCEEDED" and scene.local_path and project.status != "FAILED":
        raise HTTPException(status_code=409, detail="This scene already succeeded")
    scene.status = "PENDING"
    scene.error = None
    scene.attempt_count = 0
    scene.generation_id = None
    scene.provider_status = None
    scene.download_status = "PENDING"
    scene.local_path = None
    scene.started_at = None
    scene.completed_at = None
    await db.execute(delete(Video).where(Video.scene_id == scene.id, Video.kind == "scene"))
    project.status = "QUEUED"
    project.error = None
    await db.commit()
    await enqueue_job(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="GENERATE",
        idempotency_key=f"generate:{project.id}:{project.plan_revision}",
        payload={"plan_revision": project.plan_revision, "scene_id": scene.id},
        max_attempts=settings.worker_max_attempts,
        revive=True,
    )
    await db.refresh(project)
    return await _project_detail(db, project)


@router.delete("/{project_id}/scenes/{scene_id}", response_model=MessageOut)
async def delete_scene(
    scene_id: str,
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    if project.status in ACTIVE_STATUSES or project.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="Scenes cannot be edited while generation is active")
    scene = await db.get(Scene, scene_id)
    if scene is None or scene.project_id != project.id:
        raise HTTPException(status_code=404, detail="Scene not found")
    await db.execute(delete(GenerationAttempt).where(GenerationAttempt.scene_id == scene.id))
    await db.delete(scene)
    await db.commit()
    remaining = list(
        (
            await db.execute(
                select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)
            )
        ).scalars()
    )
    for index, item in enumerate(remaining, start=1):
        item.scene_number = index
    await db.commit()
    return MessageOut(message="Scene removed")


@router.post("/{project_id}/scenes/reorder", response_model=ProjectDetailOut)
async def reorder_scenes(
    payload: SceneReorderIn,
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailOut:
    if project.status in ACTIVE_STATUSES or project.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="Scenes cannot be reordered while generation is active")
    scenes = list((await db.execute(select(Scene).where(Scene.project_id == project.id))).scalars())
    by_id = {scene.id: scene for scene in scenes}
    if set(payload.scene_ids) != set(by_id):
        raise HTTPException(status_code=400, detail="scene_ids must contain every scene exactly once")
    for index, scene_id in enumerate(payload.scene_ids, start=1):
        by_id[scene_id].scene_number = index
    await db.commit()
    await db.refresh(project)
    return await _project_detail(db, project)


@router.post("/{project_id}/assets", response_model=MediaAssetOut, status_code=201)
async def upload_asset(
    kind: str = Query(pattern="^(reference|music|voiceover)$"),
    file: UploadFile = File(...),
    project: Project = Depends(owned_project),
    db: AsyncSession = Depends(get_db),
) -> MediaAssetOut:
    allowed = {
        "reference": {"image/jpeg", "image/png", "image/webp"},
        "music": {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/ogg"},
        "voiceover": {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/ogg"},
    }[kind]
    content_type = (file.content_type or "").lower()
    if content_type not in allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported content type for {kind}: {content_type}")
    limit = settings.max_reference_upload_mb * 1024 * 1024 if kind == "reference" else 64 * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="File too large")
    suffix = Path(file.filename or "asset").suffix.lower()[:8]
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".mp3", ".wav", ".m4a", ".mp4", ".ogg"}:
        suffix = ".bin"
    key = f"users/{project.user_id}/projects/{project.id}/assets/{kind}_{uuid.uuid4().hex[:10]}{suffix}"
    await storage.save_bytes(key, data)
    config = dict(project.generation_config or {})
    if kind == "reference":
        config.setdefault("reference_keys", []).append(key)
    else:
        config[f"{kind}_key"] = key
    project.generation_config = config
    await db.commit()
    return MediaAssetOut(
        kind=kind,
        key=key,
        filename=file.filename or "asset",
        size_bytes=len(data),
        content_type=content_type,
    )


@router.get("/{project_id}/jobs", response_model=list[JobOut])
async def list_project_jobs(
    project: Project = Depends(owned_project), db: AsyncSession = Depends(get_db)
) -> list[JobOut]:
    jobs = list(
        (
            await db.execute(
                select(Job).where(Job.project_id == project.id).order_by(Job.created_at.desc()).limit(50)
            )
        ).scalars()
    )
    return [JobOut.model_validate(job) for job in jobs]
