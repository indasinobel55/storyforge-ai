"""FastAPI app for the TAAFT-only site. Single process, in-memory state."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from taaft_site.worker import DATA_DIR, JobRunner

app = FastAPI(title="TAAFT Agent Site", docs_url=None, redoc_url=None)
runner = JobRunner()
SITE_TOKEN = os.environ.get("SITE_TOKEN", "").strip()

_STATIC = Path(__file__).parent / "static"


def _check_token(token: str | None) -> None:
    if SITE_TOKEN and token != SITE_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing X-Site-Token")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "session_connected": runner.session_connected(),
        "jobs": len(runner.jobs),
        "active_job": runner._active,
    }


@app.get("/api/session")
def session_status() -> dict:
    return {"connected": runner.session_connected()}


@app.post("/api/session")
async def upload_session(file: UploadFile = File(...), x_site_token: str | None = Header(default=None)) -> dict:
    _check_token(x_site_token)
    try:
        size = runner.save_session(await file.read())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid storage_state: {exc}") from exc
    return {"connected": True, "bytes": size}


@app.post("/api/jobs")
async def create_job(body: "JobRequest", x_site_token: str | None = Header(default=None)) -> dict:
    _check_token(x_site_token)
    prompt = (body.prompt or "").strip()
    if len(prompt) < 20:
        raise HTTPException(status_code=400, detail="prompt too short (min 20 chars)")
    if runner.session_connected() is False:
        raise HTTPException(status_code=409, detail="no TAAFT session; upload one first")
    job = runner.create_job(prompt, body.scene_count)
    return runner.public_view(job)


@app.get("/api/jobs")
def list_jobs() -> dict:
    return {"jobs": [runner.public_view(j) for j in runner.jobs.values()]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = runner.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return runner.public_view(job)


@app.get("/api/jobs/{job_id}/files/{filename}")
def job_file(job_id: str, filename: str) -> FileResponse:
    job = runner.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    safe = Path(filename).name
    if not safe.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="only scene mp4 files are served")
    path = DATA_DIR / "jobs" / job_id / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, media_type="video/mp4", filename=safe)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html", media_type="text/html")


@app.get("/favicon.ico")
def favicon() -> JSONResponse:
    return JSONResponse(content={})


class JobRequest(BaseModel):
    prompt: str
    scene_count: int = 1
