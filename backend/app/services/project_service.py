from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.errors import ProviderDisabledError
from agent.providers.base import VideoProvider
from agent.providers.registry import build_provider

from ..config import settings
from ..models import Activity, Notification, Project, ProviderAccount, Scene, UsageEvent
from ..security import decrypt_secret


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def notify(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None,
    kind: str,
    title: str,
    body: str,
) -> Notification:
    item = Notification(user_id=user_id, project_id=project_id, kind=kind, title=title, body=body)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def record_activity(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None,
    kind: str,
    title: str,
    body: str,
    meta: dict | None = None,
) -> Activity:
    # ``created_at`` is the only ordering key for activity feeds, so keep it
    # strictly monotonic per project. Without this, events recorded in the same
    # clock tick share a timestamp and newest-first listings plus replay
    # ordering become nondeterministic (the previous event can flip position).
    created_at = utcnow()
    latest_query = select(func.max(Activity.created_at))
    if project_id is None:
        latest_query = latest_query.where(
            Activity.user_id == user_id, Activity.project_id.is_(None)
        )
    else:
        latest_query = latest_query.where(Activity.project_id == project_id)
    latest_created_at = (await db.execute(latest_query)).scalar()
    if latest_created_at is not None:
        if latest_created_at.tzinfo is None:
            latest_created_at = latest_created_at.replace(tzinfo=timezone.utc)
        if created_at <= latest_created_at:
            created_at = latest_created_at + timedelta(microseconds=1)

    item = Activity(
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        title=title,
        body=body,
        meta=meta or {},
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def activity_for_user(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Activity]:
    """Return the owning user's activity events, optionally filtered to one project.

    The caller is responsible for confirming that ``user_id`` owns the requested
    project when ``project_id`` is supplied.
    """
    query = select(Activity).where(Activity.user_id == user_id)
    if project_id is not None:
        query = query.where(Activity.project_id == project_id)
    query = query.order_by(Activity.created_at.desc()).offset(offset).limit(limit)
    rows = await db.execute(query)
    return list(rows.scalars())


async def activity_count_for_user(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> int:
    query = select(func.count(Activity.id)).where(Activity.user_id == user_id)
    if project_id is not None:
        query = query.where(Activity.project_id == project_id)
    row = await db.execute(query)
    return int(row.scalar() or 0)


async def record_usage(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None,
    kind: str,
    quantity: float = 1,
    unit: str = "count",
    meta: dict | None = None,
) -> None:
    db.add(
        UsageEvent(
            user_id=user_id,
            project_id=project_id,
            kind=kind,
            quantity=quantity,
            unit=unit,
            meta=meta or {},
        )
    )
    await db.commit()


async def recompute_progress(db: AsyncSession, project: Project) -> int:
    rows = (
        await db.execute(
            select(Scene.status, func.count(Scene.id)).where(Scene.project_id == project.id).group_by(Scene.status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    total = sum(counts.values())
    succeeded = counts.get("SUCCEEDED", 0)
    if project.status == "COMPLETED":
        progress = 100
    elif project.status in {"PLANNING", "PLANNING_QUEUED"}:
        progress = 5
    elif project.status in {"AWAITING_APPROVAL", "QUEUED"}:
        progress = 10
    elif total == 0:
        progress = 0
    else:
        progress = min(94, 10 + int(84 * succeeded / total))
        if project.status in {"PROCESSING", "VALIDATING", "DOWNLOADING"}:
            progress = max(progress, 90)
    project.progress = progress
    await db.commit()
    return progress


async def ensure_simulated_account(db: AsyncSession, user_id: str) -> ProviderAccount:
    result = await db.execute(
        select(ProviderAccount).where(
            ProviderAccount.user_id == user_id, ProviderAccount.provider == "simulated"
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = ProviderAccount(
            user_id=user_id,
            provider="simulated",
            status="connected",
            account_ref=f"simulated:{user_id[:8]}",
            usage={"plan": "simulated", "detail": {"simulated": True}},
            last_verified_at=utcnow(),
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
    return account


async def acquire_provider_lock(
    db: AsyncSession,
    *,
    account_id: str,
    project_id: str,
    worker_id: str,
    lease_seconds: int,
) -> bool:
    now = utcnow()
    result = await db.execute(
        update(ProviderAccount)
        .where(
            ProviderAccount.id == account_id,
            (
                (ProviderAccount.active_project_id.is_(None))
                | (ProviderAccount.active_project_id == project_id)
                | (ProviderAccount.lock_expires_at.is_(None))
                | (ProviderAccount.lock_expires_at < now)
            ),
        )
        .values(
            active_project_id=project_id,
            lock_owner=worker_id,
            lock_expires_at=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
    )
    await db.commit()
    return bool(result.rowcount)


async def refresh_provider_lock(
    db: AsyncSession, *, account_id: str, worker_id: str, lease_seconds: int
) -> None:
    await db.execute(
        update(ProviderAccount)
        .where(ProviderAccount.id == account_id, ProviderAccount.lock_owner == worker_id)
        .values(lock_expires_at=utcnow() + timedelta(seconds=lease_seconds))
    )
    await db.commit()


async def release_provider_lock(db: AsyncSession, *, account_id: str, worker_id: str) -> None:
    await db.execute(
        update(ProviderAccount)
        .where(ProviderAccount.id == account_id, ProviderAccount.lock_owner == worker_id)
        .values(active_project_id=None, lock_owner=None, lock_expires_at=None)
    )
    await db.commit()


async def resolve_provider(
    db: AsyncSession, *, project: Project, worker_id: str
) -> tuple[VideoProvider, ProviderAccount, str | None]:
    """Build the provider adapter for a project's owner.

    Returns ``(provider, account, temp_session_dir)``. The caller must remove the
    temporary session directory when done; decrypted session material never
    leaves the worker process and is never logged.
    """
    result = await db.execute(
        select(ProviderAccount).where(
            ProviderAccount.user_id == project.user_id,
            ProviderAccount.provider == project.provider,
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        if project.provider == "simulated":
            account = await ensure_simulated_account(db, project.user_id)
        else:
            raise ProviderDisabledError(
                f"No connected {project.provider} account for this user; connect it in Account Settings"
            )
    if account.status != "connected":
        raise ProviderDisabledError(f"{project.provider} account is not connected")

    session_dir: str | None = None
    storage_state = None
    if project.provider == "taaft":
        if not account.encrypted_session:
            raise ProviderDisabledError("No stored TAAFT session; reconnect the account")
        path = settings.storage_path / "_sessions" / worker_id
        path.mkdir(parents=True, exist_ok=True)
        state_file = path / f"{account.id}.json"
        state_file.write_text(decrypt_secret(account.encrypted_session), encoding="utf-8")
        storage_state = state_file
        session_dir = str(path)

    provider = build_provider(
        project.provider,
        cache_dir=settings.storage_path / "_simulated" / project.user_id,
        simulated_generation_seconds=settings.simulated_generation_seconds,
        simulated_clip_seconds=settings.simulated_clip_seconds,
        taaft_enabled=settings.taaft_enabled,
        taaft_storage_state=storage_state,
        taaft_chrome_path=settings.taaft_chrome_path or None,
        taaft_headless=settings.taaft_headless,
        taaft_poll_seconds=settings.taaft_poll_seconds,
        taaft_job_timeout=settings.taaft_job_timeout_seconds,
        test_vision_adapter=settings.simulated_provider_enabled,
    )
    return provider, account, session_dir


async def publish_activity(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str,
    event: str,
    title: str,
    body: str,
    meta: dict | None = None,
) -> Activity:
    """Write a user-scoped activity event and return it.

    Activity events are visible only to the owning user; they are never
    fabricated ahead of backend confirmation.
    """
    return await record_activity(
        db,
        user_id=user_id,
        project_id=project_id,
        kind=event,
        title=title,
        body=body,
        meta=meta or {},
    )


def storage_keys(user_id: str, project_id: str) -> dict[str, str]:
    base = f"users/{user_id}/projects/{project_id}"
    return {
        "base": base,
        "scene": f"{base}/scenes",
        "render": f"{base}/render",
        "final": f"{base}/final.mp4",
        "thumbnail": f"{base}/thumbnail.jpg",
    }
