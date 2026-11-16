"""Job runner for the TAAFT-only site.

The Render free container (512MB) cannot host Chromium, so the site itself
never launches a browser. Instead it dispatches each job to GitHub Actions
(public repo = free minutes, 7GB RAM), where ``taaft_site/runner_job.py``
automates TAAFT and uploads the finished scenes back to the site.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from agent.core.errors import AgentError

DATA_DIR = Path("/app/data")
SCENE_SECONDS = 8.0


def ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise AgentError(f"ffmpeg failed: {proc.stderr[-400:]}")


def extract_last_frame(clip: Path, frame: Path) -> Path:
    ffmpeg(["-sseof", "-0.2", "-i", str(clip), "-frames:v", "1", "-q:v", "2", str(frame)])
    if not frame.exists():
        raise AgentError("could not extract continuation reference frame")
    return frame


def normalize_clip(raw: Path, final: Path) -> Path:
    ffmpeg(
        [
            "-i", str(raw),
            "-t", str(SCENE_SECONDS),
            "-vf", "scale=1280:720:flags=lanczos,fps=24,tpad=stop_mode=clone:stop_duration=2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-an",
            str(final),
        ]
    )
    if not final.exists() or final.stat().st_size == 0:
        raise AgentError("normalized clip is empty")
    return final


class JobRunner:
    """In-memory job registry; execution is delegated to GitHub Actions."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._active: str | None = None

    # ----- session management -----

    def session_path(self) -> Path:
        return DATA_DIR / "session.json"

    def session_connected(self) -> bool:
        return self.session_path().exists()

    def save_session(self, payload: bytes) -> int:
        parsed = json.loads(payload.decode("utf-8"))
        if not isinstance(parsed, dict) or not parsed.get("cookies"):
            raise ValueError("storage_state JSON must contain a 'cookies' array")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.session_path().write_bytes(payload)
        return len(payload)

    # ----- GitHub dispatch -----

    def _github_config(self) -> tuple[str, str]:
        repo = os.environ.get("GITHUB_REPO", "").strip()
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not repo or not token:
            raise AgentError("server is missing GITHUB_REPO/GITHUB_TOKEN for dispatch")
        return repo, token

    def _site_config(self) -> tuple[str, str]:
        site_url = os.environ.get("SITE_PUBLIC_URL", "").strip().rstrip("/")
        token = os.environ.get("SITE_TOKEN", "").strip()
        if not site_url or not token:
            raise AgentError("server is missing SITE_PUBLIC_URL/SITE_TOKEN for dispatch")
        return site_url, token

    def dispatch_job(self, job: dict[str, Any]) -> None:
        repo, token = self._github_config()
        site_url, site_token = self._site_config()
        resp = requests.post(
            f"https://api.github.com/repos/{repo}/dispatches",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "taaft-agent-site",
            },
            json={
                "event_type": "taaft-job",
                "client_payload": {
                    "job_id": job["job_id"],
                    "prompt": job["prompt"],
                    "scene_count": job["scene_count"],
                    "site_url": site_url,
                    "site_token": site_token,
                },
            },
            timeout=60,
        )
        if resp.status_code not in (204, 200):
            raise AgentError(f"GitHub dispatch failed: HTTP {resp.status_code} {resp.text[:200]}")

    # ----- job management -----

    def public_view(self, job: dict[str, Any]) -> dict[str, Any]:
        return job  # plain dicts already JSON-safe

    def create_job(self, prompt: str, scene_count: int) -> dict[str, Any]:
        scene_count = max(1, min(int(scene_count), 8))
        job_id = uuid.uuid4().hex[:12]
        job = {
            "job_id": job_id,
            "prompt": prompt,
            "scene_count": scene_count,
            "status": "queued",
            "error": None,
            "created_at": time.time(),
            "scenes": [
                {"scene": i, "status": "pending", "generation_id": None, "filename": None}
                for i in range(1, scene_count + 1)
            ],
        }
        with self._lock:
            self.jobs[job_id] = job
        if os.environ.get("JOB_DISPATCH", "github").strip().lower() == "github":
            self.dispatch_job(job)
            job["status"] = "dispatched"
            self._active = job_id
        else:
            # external runner mode: job stays queued until a runner claims it
            job["status"] = "queued"
        return job

    def claim_job(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] != "queued":
            raise ValueError(f"job {job_id} is {job['status']}, not queued")
        job["status"] = "dispatched"
        self._active = job_id
        return job

    # ----- runner callbacks (called by GitHub Actions via the API) -----

    def update_progress(self, job_id: str, scene: int, **updates: Any) -> None:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        entry = job["scenes"][scene - 1]
        entry.update(updates)
        if job["status"] in ("queued", "dispatched"):
            job["status"] = "running"

    def set_filename(self, job_id: str, scene: int, filename: str) -> None:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        safe = Path(filename).name
        entry = job["scenes"][scene - 1]
        entry["filename"] = safe
        target = DATA_DIR / "jobs" / job_id
        target.mkdir(parents=True, exist_ok=True)

    def store_file(self, job_id: str, filename: str, payload: bytes) -> Path:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        safe = Path(filename).name
        if not safe.endswith(".mp4"):
            raise ValueError("only mp4 files are accepted")
        path = DATA_DIR / "jobs" / job_id / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def complete_job(self, job_id: str, error: str | None = None) -> None:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if self._active == job_id:
            self._active = None
        if error:
            job["status"] = "failed"
            job["error"] = error[:600]
        else:
            job["status"] = "completed"
