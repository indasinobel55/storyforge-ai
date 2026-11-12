from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Job


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def enqueue_job(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None,
    kind: str,
    idempotency_key: str,
    payload: dict | None = None,
    priority: int = 100,
    max_attempts: int = 3,
    available_at: datetime | None = None,
    revive: bool = False,
) -> Job:
    """Insert a job idempotently.

    If the idempotency key already exists the existing job is returned. With
    ``revive=True`` a terminal job is reset to QUEUED so an explicit retry can
    reuse the same logical work item without creating duplicates.
    """
    result = await db.execute(select(Job).where(Job.idempotency_key == idempotency_key))
    existing = result.scalar_one_or_none()
    if existing is not None:
        if revive and existing.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            existing.status = "QUEUED"
            existing.attempts = 0
            existing.last_error = None
            existing.result = None
            existing.available_at = available_at or utcnow()
            existing.locked_by = None
            existing.locked_at = None
            existing.lease_expires_at = None
            existing.finished_at = None
            if payload is not None:
                existing.payload = payload
            await db.commit()
            await db.refresh(existing)
        return existing

    job = Job(
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        idempotency_key=idempotency_key,
        payload=payload or {},
        priority=priority,
        max_attempts=max_attempts,
        available_at=available_at or utcnow(),
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(Job).where(Job.idempotency_key == idempotency_key))
        job = result.scalar_one()
    await db.refresh(job)
    return job


async def claim_job(db: AsyncSession, *, worker_id: str, lease_seconds: int) -> Job | None:
    now = utcnow()
    lease_until = now + timedelta(seconds=lease_seconds)
    for _ in range(5):
        result = await db.execute(
            select(Job)
            .where(
                or_(
                    and_(Job.status == "QUEUED", Job.available_at <= now),
                    and_(Job.status == "RUNNING", Job.lease_expires_at.is_not(None), Job.lease_expires_at < now),
                )
            )
            .order_by(Job.priority.asc(), Job.available_at.asc(), Job.created_at.asc())
            .limit(1)
        )
        candidate = result.scalar_one_or_none()
        if candidate is None:
            return None

        claim = (
            update(Job)
            .where(
                Job.id == candidate.id,
                or_(
                    and_(Job.status == "QUEUED", Job.available_at <= now),
                    and_(
                        Job.status == "RUNNING",
                        Job.lease_expires_at.is_not(None),
                        Job.lease_expires_at < now,
                    ),
                ),
            )
            .values(
                status="RUNNING",
                locked_by=worker_id,
                locked_at=now,
                lease_expires_at=lease_until,
                attempts=Job.attempts + 1,
                started_at=func.coalesce(Job.started_at, now),
                updated_at=now,
            )
        )
        outcome = await db.execute(claim)
        await db.commit()
        if outcome.rowcount:
            await db.refresh(candidate)
            return candidate
    return None


async def heartbeat_job(db: AsyncSession, job_id: str, worker_id: str, lease_seconds: int) -> None:
    now = utcnow()
    await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "RUNNING", Job.locked_by == worker_id)
        .values(lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now)
    )
    await db.commit()


async def complete_job(db: AsyncSession, job: Job, result: dict | None = None) -> None:
    now = utcnow()
    job.status = "SUCCEEDED"
    job.result = result or {}
    job.locked_by = None
    job.locked_at = None
    job.lease_expires_at = None
    job.finished_at = now
    job.last_error = None
    await db.commit()


async def fail_job(db: AsyncSession, job: Job, error: str) -> str:
    now = utcnow()
    job.last_error = error[:8000]
    job.locked_by = None
    job.locked_at = None
    job.lease_expires_at = None
    if job.attempts < job.max_attempts:
        job.status = "QUEUED"
        delay = min(300, 10 * (2 ** max(0, job.attempts - 1)))
        job.available_at = now + timedelta(seconds=delay)
        await db.commit()
        return "retry"
    job.status = "FAILED"
    job.finished_at = now
    await db.commit()
    return "failed"


async def cancel_project_jobs(db: AsyncSession, project_id: str) -> int:
    jobs = (
        await db.execute(
            select(Job).where(Job.project_id == project_id, Job.status.in_(["QUEUED", "RUNNING"]))
        )
    ).scalars()
    count = 0
    for job in jobs:
        job.status = "CANCELLED"
        job.finished_at = utcnow()
        count += 1
    await db.commit()
    return count


async def project_active_job(db: AsyncSession, project_id: str) -> Job | None:
    result = await db.execute(
        select(Job)
        .where(Job.project_id == project_id, Job.status.in_(["QUEUED", "RUNNING"]))
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
