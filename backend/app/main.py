from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .api import auth, local_execution, meta, notifications, projects, providers, realtime_api, videos
from .config import settings
from .database import SessionLocal, dispose_db, init_db
from .deps import CSRF_COOKIE, SESSION_COOKIE
from .models import Session
from .security import token_hash

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT_PREFIXES = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/password-reset",
    "/api/execution/",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_schema:
        await init_db()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    yield
    await dispose_db()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Cloud-first AI video generation platform with durable workers and a scoped local execution mode. "
        "Real TAAFT provider automation is gated pending written provider authorization."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method in UNSAFE_METHODS:
        exempt = any(request.url.path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES)
        has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
        if not exempt and not has_bearer:
            session_token = request.cookies.get(SESSION_COOKIE)
            if session_token:
                header_token = request.headers.get("x-csrf-token", "")
                async with SessionLocal() as db:
                    session = (
                        await db.execute(select(Session).where(Session.token_hash == token_hash(session_token)))
                    ).scalar_one_or_none()
                if session is None or not header_token or token_hash(header_token) != session.csrf_hash:
                    return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


app.include_router(meta.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(realtime_api.router, prefix="/api")
app.include_router(local_execution.router, prefix="/api")


@app.get("/")
async def root() -> dict:
    return {
        "app": settings.app_name,
        "status": "ok",
        "docs": "/docs",
        "execution_mode": settings.effective_execution_mode,
    }
