from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import require_user
from ..models import Notification, PushSubscription, User
from ..schemas import MessageOut, NotificationOut, PushSubscribeIn
from ..security import utcnow

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = False,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationOut]:
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    items = list(
        (await db.execute(query.order_by(Notification.created_at.desc()).limit(limit))).scalars()
    )
    return [NotificationOut.model_validate(item) for item in items]


@router.post("/read", response_model=MessageOut)
async def mark_read(
    notification_id: str | None = None,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    query = select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if notification_id:
        query = query.where(Notification.id == notification_id)
    items = list((await db.execute(query)).scalars())
    for item in items:
        item.read_at = utcnow()
    await db.commit()
    return MessageOut(message=f"Marked {len(items)} notification(s) read")


@router.delete("/{notification_id}", response_model=MessageOut)
async def delete_notification(
    notification_id: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> MessageOut:
    result = await db.execute(
        delete(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    await db.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Notification not found")
    return MessageOut(message="Notification deleted")


@router.post("/subscribe", response_model=MessageOut)
async def subscribe_push(
    payload: PushSubscribeIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    existing = (
        await db.execute(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            PushSubscription(
                user_id=user.id,
                endpoint=payload.endpoint,
                p256dh=payload.p256dh,
                auth=payload.auth,
            )
        )
    else:
        existing.user_id = user.id
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
    await db.commit()
    return MessageOut(
        message="Subscription stored. Server push requires VAPID keys; local in-app notifications are enabled."
    )


@router.delete("/subscribe", response_model=MessageOut)
async def unsubscribe_push(
    endpoint: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == endpoint, PushSubscription.user_id == user.id
        )
    )
    await db.commit()
    return MessageOut(message="Subscription removed")
