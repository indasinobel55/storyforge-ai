from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import require_user
from ..models import Job, Project, Scene, UsageEvent, User, Video
from ..schemas import PublicConfigOut, UsageOut

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    queued = (await db.execute(select(func.count(Job.id)).where(Job.status == "QUEUED"))).scalar_one()
    running = (await db.execute(select(func.count(Job.id)).where(Job.status == "RUNNING"))).scalar_one()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "execution_mode": settings.effective_execution_mode,
        "cloud_workers_enabled": settings.cloud_execution_enabled,
        "local_workers_enabled": settings.local_execution_enabled,
        "jobs": {"queued": queued, "running": running},
        "simulated_provider_enabled": settings.simulated_provider_enabled,
        "taaft_enabled": settings.taaft_enabled,
    }


@router.get("/config", response_model=PublicConfigOut)
async def public_config() -> PublicConfigOut:
    return PublicConfigOut(
        app_name=settings.app_name,
        environment=settings.environment,
        execution_mode=settings.effective_execution_mode,
        simulated_provider_enabled=settings.simulated_provider_enabled,
        taaft_enabled=settings.taaft_enabled,
        max_scenes_per_project=settings.max_scenes_per_project,
        max_scene_seconds=settings.max_scene_seconds,
        max_reference_upload_mb=settings.max_reference_upload_mb,
        push_configured=False,
    )


@router.get("/usage", response_model=UsageOut)
async def usage(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> UsageOut:
    project_ids = select(Project.id).where(Project.user_id == user.id).subquery()
    projects_total = (
        await db.execute(select(func.count(Project.id)).where(Project.user_id == user.id))
    ).scalar_one()
    active = (
        await db.execute(
            select(func.count(Project.id)).where(
                Project.user_id == user.id,
                Project.status.in_(["PLANNING", "QUEUED", "GENERATING", "PROCESSING", "VALIDATING"]),
            )
        )
    ).scalar_one()
    videos_total = (
        await db.execute(
            select(func.count(Video.id)).where(Video.user_id == user.id, Video.deleted_at.is_(None))
        )
    ).scalar_one()
    scenes_generated = (
        await db.execute(
            select(func.count(Scene.id)).where(
                Scene.project_id.in_(select(project_ids.c.id)), Scene.status == "SUCCEEDED"
            )
        )
    ).scalar_one()
    storage_used = (
        await db.execute(
            select(func.coalesce(func.sum(Video.size_bytes), 0)).where(
                Video.user_id == user.id, Video.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    generations = (
        await db.execute(
            select(func.count(UsageEvent.id)).where(
                UsageEvent.user_id == user.id,
                UsageEvent.kind == "scene_generated",
                UsageEvent.created_at >= month_start,
            )
        )
    ).scalar_one()
    return UsageOut(
        projects_total=projects_total,
        projects_active=active,
        videos_total=videos_total,
        scenes_generated=scenes_generated,
        storage_used_bytes=int(storage_used),
        storage_quota_bytes=settings.usage_storage_quota_mb * 1024 * 1024,
        generations_this_month=generations,
    )
