from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import Project, Session, User, Video
from .security import token_hash

SESSION_COOKIE = "sf_session"
CSRF_COOKIE = "sf_csrf"


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def get_session_user(request: Request, db: AsyncSession) -> tuple[User, Session] | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            token = header.split(" ", 1)[1]
    if not token:
        return None
    result = await db.execute(select(Session).where(Session.token_hash == token_hash(token)))
    session = result.scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        return None
    expires = as_utc(session.expires_at)
    if expires is None or expires <= datetime.now(timezone.utc):
        return None
    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user, session


async def require_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    found = await get_session_user(request, db)
    if found is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return found[0]


async def optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    found = await get_session_user(request, db)
    return found[0] if found else None


async def require_session(request: Request, db: AsyncSession = Depends(get_db)) -> tuple[User, Session]:
    found = await get_session_user(request, db)
    if found is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return found


async def owned_project(
    project_id: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def owned_video(
    video_id: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> Video:
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == user.id, Video.deleted_at.is_(None))
    )
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
