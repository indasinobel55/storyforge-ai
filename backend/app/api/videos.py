from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_session_user, owned_video, require_user
from ..models import User, Video
from ..schemas import MessageOut, VideoListOut, VideoOut
from ..security import create_signed_token, verify_signed_token
from ..services.storage import storage


def _token_for(video: Video) -> str:
    return create_signed_token(f"{video.id}|{video.user_id}", settings.signed_url_ttl_seconds, "file")


def _video_out(video: Video) -> VideoOut:
    token = _token_for(video)
    return VideoOut(
        **{key: getattr(video, key) for key in (
            "id",
            "project_id",
            "scene_id",
            "kind",
            "filename",
            "size_bytes",
            "mime_type",
            "duration_seconds",
            "width",
            "height",
            "has_audio",
            "checksum_sha256",
            "created_at",
        )},
        stream_url=f"/api/videos/{video.id}/stream?token={token}",
        download_url=f"/api/videos/{video.id}/stream?token={token}&download=1",
        thumbnail_url=f"/api/videos/{video.id}/thumbnail?token={token}" if video.thumbnail_key else None,
    )


router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=VideoListOut)
async def list_videos(
    project_id: str | None = None,
    kind: str | None = Query(default=None, pattern="^(final|scene)$"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> VideoListOut:
    query = select(Video).where(Video.user_id == user.id, Video.deleted_at.is_(None))
    count_query = select(func.count(Video.id)).where(Video.user_id == user.id, Video.deleted_at.is_(None))
    if project_id:
        query = query.where(Video.project_id == project_id)
        count_query = count_query.where(Video.project_id == project_id)
    if kind:
        query = query.where(Video.kind == kind)
        count_query = count_query.where(Video.kind == kind)
    total = (await db.execute(count_query)).scalar_one()
    videos = list(
        (await db.execute(query.order_by(Video.created_at.desc()).limit(limit).offset(offset))).scalars()
    )
    return VideoListOut(items=[_video_out(video) for video in videos], total=total)


@router.get("/{video_id}", response_model=VideoOut)
async def get_video(video: Video = Depends(owned_video)) -> VideoOut:
    return _video_out(video)


async def _authorize_stream(video_id: str, request: Request, db: AsyncSession) -> Video:
    token = request.query_params.get("token")
    video = await db.get(Video, video_id)
    if video is None or video.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Video not found")
    if token:
        subject = verify_signed_token(token, "file")
        if subject != f"{video.id}|{video.user_id}":
            raise HTTPException(status_code=403, detail="Invalid or expired media token")
        return video
    found = await get_session_user(request, db)
    if found is None or found[0].id != video.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return video


def _iter_file(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: str,
    request: Request,
    download: bool = False,
    db: AsyncSession = Depends(get_db),
):
    video = await _authorize_stream(video_id, request, db)
    try:
        path = storage.local_path(video.storage_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Video file is unavailable")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file is unavailable")
    size = path.stat().st_size
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": (
            f'attachment; filename="{video.filename.replace(chr(34), "")}"' if download else "inline"
        ),
        "Cache-Control": "private, max-age=60",
    }
    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        try:
            range_value = range_header.split("=", 1)[1].split(",")[0]
            start_text, end_text = range_value.split("-", 1)
            start = int(start_text) if start_text else 0
            end = int(end_text) if end_text else size - 1
        except ValueError:
            raise HTTPException(status_code=416, detail="Invalid range")
        start = max(0, start)
        end = min(size - 1, end)
        if start > end:
            raise HTTPException(status_code=416, detail="Invalid range")
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            _iter_file(path, start, end),
            status_code=206,
            media_type=video.mime_type,
            headers=headers,
        )
    headers["Content-Length"] = str(size)
    return StreamingResponse(_iter_file(path, 0, size - 1), media_type=video.mime_type, headers=headers)


@router.get("/{video_id}/download")
async def download_video(
    video_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await stream_video(video_id, request, download=True, db=db)


@router.get("/{video_id}/thumbnail")
async def stream_thumbnail(video_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    video = await _authorize_stream(video_id, request, db)
    if not video.thumbnail_key:
        raise HTTPException(status_code=404, detail="No thumbnail")
    try:
        path = storage.local_path(video.thumbnail_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Thumbnail is unavailable")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail is unavailable")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.delete("/{video_id}", response_model=MessageOut)
async def delete_video(
    video: Video = Depends(owned_video),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    from ..security import utcnow

    video.deleted_at = utcnow()
    try:
        await storage.delete(video.storage_key)
    except Exception:
        pass
    if video.thumbnail_key:
        try:
            await storage.delete(video.thumbnail_key)
        except Exception:
            pass
    await db.commit()
    return MessageOut(message="Video deleted")
