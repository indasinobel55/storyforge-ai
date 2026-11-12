from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import require_user
from ..models import Notification, Project, User
from ..realtime import manager
from ..schemas import MessageOut
from ..security import create_signed_token, verify_signed_token

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.post("/ticket", response_model=dict)
async def create_ticket(user: User = Depends(require_user)) -> dict:
    token = create_signed_token(user.id, settings.ws_ticket_ttl_seconds, "ws")
    return {"ticket": token, "expires_in": settings.ws_ticket_ttl_seconds}


async def _snapshot(db: AsyncSession, user_id: str) -> dict:
    projects = list(
        (
            await db.execute(
                select(Project)
                .where(Project.user_id == user_id)
                .order_by(Project.updated_at.desc())
                .limit(25)
            )
        ).scalars()
    )
    unread = (
        await db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
    ).scalar_one()
    return {
        "type": "snapshot",
        "execution_mode": settings.effective_execution_mode,
        "unread_notifications": unread,
        "projects": [
            {
                "id": project.id,
                "title": project.title,
                "status": project.status,
                "progress": project.progress,
                "final_video_id": project.final_video_id,
                "error": project.error,
                "updated_at": project.updated_at.isoformat(),
            }
            for project in projects
        ],
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")) -> None:
    user_id = verify_signed_token(token, "ws") if token else None
    if not user_id:
        await websocket.close(code=4401)
        return
    await manager.connect(user_id, websocket)
    try:
        while True:
            try:
                async with SessionLocal() as db:
                    snapshot = await _snapshot(db, user_id)
                await websocket.send_text(json.dumps(snapshot, default=str))
            except Exception:
                pass
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id, websocket)


@router.get("/health", response_model=MessageOut)
async def realtime_health() -> MessageOut:
    return MessageOut(message=f"{manager.connection_count()} active connections")
