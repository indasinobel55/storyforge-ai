from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import CSRF_COOKIE, SESSION_COOKIE, require_session
from ..models import AuditEvent, PasswordResetToken, Session, User
from ..schemas import (
    AccountDeleteIn,
    AuthResponse,
    LoginIn,
    MessageOut,
    PasswordChangeIn,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    ProfileUpdateIn,
    RegisterIn,
    UserOut,
)
from ..security import (
    auth_limiter,
    hash_password,
    new_token,
    token_hash,
    utcnow,
    verify_password,
)
from ..services.project_service import ensure_simulated_account

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


async def _create_session(db: AsyncSession, user: User, request: Request) -> tuple[str, str, Session]:
    token = new_token()
    csrf = new_token(24)
    session = Session(
        user_id=user.id,
        token_hash=token_hash(token),
        csrf_hash=token_hash(csrf),
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        user_agent=(request.headers.get("user-agent") or "")[:480],
        ip_address=_client_ip(request)[:60],
    )
    db.add(session)
    await db.commit()
    return token, csrf, session


def _limit(request: Request) -> None:
    allowed, retry_after = auth_limiter.check(_client_ip(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    payload: RegisterIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    _limit(request)
    email = payload.email.lower().strip()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await ensure_simulated_account(db, user.id)
    token, csrf, _ = await _create_session(db, user, request)
    db.add(AuditEvent(user_id=user.id, action="user_registered", ip_address=_client_ip(request)))
    await db.commit()
    _set_cookies(response, token, csrf)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    _limit(request)
    email = payload.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token, csrf, _ = await _create_session(db, user, request)
    db.add(AuditEvent(user_id=user.id, action="user_login", ip_address=_client_ip(request)))
    await db.commit()
    _set_cookies(response, token, csrf)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/logout", response_model=MessageOut)
async def logout(
    response: Response,
    found: tuple[User, Session] = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    _, session = found
    session.revoked_at = utcnow()
    await db.commit()
    _clear_cookies(response)
    return MessageOut(message="Logged out")


@router.get("/me", response_model=AuthResponse)
async def me(
    request: Request,
    response: Response,
    found: tuple[User, Session] = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user, session = found
    csrf = request.cookies.get(CSRF_COOKIE)
    if not csrf:
        csrf = new_token(24)
        session.csrf_hash = token_hash(csrf)
        await db.commit()
        response.set_cookie(
            CSRF_COOKIE,
            csrf,
            max_age=settings.session_ttl_hours * 3600,
            httponly=False,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    payload: ProfileUpdateIn,
    found: tuple[User, Session] = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user, _ = found
    user.display_name = payload.display_name.strip()
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/password", response_model=MessageOut)
async def change_password(
    payload: PasswordChangeIn,
    found: tuple[User, Session] = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    user, session = found
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    await db.execute(
        Session.__table__.update()
        .where(Session.user_id == user.id, Session.id != session.id)
        .values(revoked_at=utcnow())
    )
    await db.commit()
    return MessageOut(message="Password updated; other sessions were signed out")


@router.post("/password-reset/request", response_model=MessageOut)
async def request_password_reset(
    payload: PasswordResetRequestIn, request: Request, db: AsyncSession = Depends(get_db)
) -> MessageOut:
    _limit(request)
    email = payload.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    message = "If an account exists for that email, a reset link has been generated."
    if user is not None:
        token = new_token(32)
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash(token),
                expires_at=utcnow() + timedelta(hours=1),
            )
        )
        await db.commit()
        if settings.dev_expose_reset_token and not settings.is_production:
            return MessageOut(
                message=message
                + " Development token (email delivery is not configured): "
                + token
            )
    return MessageOut(message=message)


@router.post("/password-reset/confirm", response_model=MessageOut)
async def confirm_password_reset(payload: PasswordResetConfirmIn, db: AsyncSession = Depends(get_db)) -> MessageOut:
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash(payload.token),
            PasswordResetToken.used_at.is_(None),
        )
    )
    reset = result.scalar_one_or_none()
    if reset is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    expires = reset.expires_at.replace(tzinfo=timezone.utc) if reset.expires_at.tzinfo is None else reset.expires_at
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user = await db.get(User, reset.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.password_hash = hash_password(payload.new_password)
    reset.used_at = utcnow()
    await db.execute(
        Session.__table__.update().where(Session.user_id == user.id).values(revoked_at=utcnow())
    )
    await db.commit()
    return MessageOut(message="Password reset. Sign in with your new password.")


@router.delete("/account", response_model=MessageOut)
async def delete_account(
    payload: AccountDeleteIn,
    found: tuple[User, Session] = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    user, _ = found
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password is incorrect")
    user_dir = settings.storage_path / "users" / user.id
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    shutil.rmtree(user_dir, ignore_errors=True)
    return MessageOut(message="Account deleted")
