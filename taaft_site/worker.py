"""Job runner for the TAAFT-only site.

One job = one prompt + N scenes. All scenes of a job share a single
Chromium session (``TaaftProvider.session()``); scene 2+ extends the
previous generation, falling back to a reference-image submission.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests

from agent.core.errors import AgentError
from agent.providers.taaft import TaaftProvider

DATA_DIR = Path("/app/data")
SCENE_SECONDS = 8.0


def _ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise AgentError(f"ffmpeg failed: {proc.stderr[-400:]}")


def extract_last_frame(clip: Path, frame: Path) -> Path:
    _ffmpeg(["-sseof", "-0.2", "-i", str(clip), "-frames:v", "1", "-q:v", "2", str(frame)])
    if not frame.exists():
        raise AgentError("could not extract continuation reference frame")
    return frame


def normalize_clip(raw: Path, final: Path) -> Path:
    _ffmpeg(
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
    """In-memory job registry. Jobs are ephemeral (container-local) by design."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
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

    # ----- job management -----

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
        self.jobs[job_id] = job
        asyncio.get_running_loop().run_in_executor(None, self._run_job, job_id, prompt, scene_count)
        return job

    def public_view(self, job: dict[str, Any]) -> dict[str, Any]:
        return job  # plain dicts already JSON-safe

    def _set_scene(self, job_id: str, scene: int, **updates: Any) -> None:
        job = self.jobs.get(job_id)
        if job is None:
            return
        entry = job["scenes"][scene - 1]
        entry.update(updates)

    # ----- the actual automation -----

    def _run_job(self, job_id: str, prompt: str, scene_count: int) -> None:
        job = self.jobs.get(job_id)
        if job is None:
            return
        if not self.session_connected():
            job["status"] = "failed"
            job["error"] = "No TAAFT session uploaded yet"
            return
        if self._active is not None:
            job["status"] = "failed"
            job["error"] = f"another job ({self._active}) is already running; TAAFT allows one render at a time"
            return
        self._active = job_id
        job["status"] = "running"
        work_dir = DATA_DIR / "jobs" / job_id
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
            self._run_job_sync(job_id, prompt, scene_count, work_dir)
            job["status"] = "completed"
        except Exception as exc:  # noqa: BLE001 - report everything to the UI
            job["status"] = "failed"
            job["error"] = f"{type(exc).__name__}: {exc}"[:600]
        finally:
            self._active = None

    def _run_job_sync(self, job_id: str, prompt: str, scene_count: int, work_dir: Path) -> None:
        provider = TaaftProvider(
            enabled=True,
            storage_state_path=self.session_path(),
            headless=True,
            poll_seconds=20,
            job_timeout_seconds=3600,
            tier="quality",
            orientation="landscape",
        )
        with provider.session() as page:
            parent_id: str | None = None
            parent_clip: Path | None = None
            for scene in range(1, scene_count + 1):
                scene_prompt = prompt
                if scene_count > 1:
                    scene_prompt = (
                        f"{prompt}\n\nThis is scene {scene} of {scene_count} of one continuous film. "
                        "Keep characters, wardrobe, environment, lighting and film style consistent "
                        "with the previous shot."
                    )
                raw = work_dir / f"scene_{scene:02d}_raw.mp4"
                final = work_dir / f"scene_{scene:02d}.mp4"
                entry_status = lambda s: self._set_scene(job_id, scene, status=s)  # noqa: E731

                reference: Path | None = None
                if parent_clip is not None:
                    entry_status("reference")
                    reference = extract_last_frame(parent_clip, work_dir / f"frame_{scene - 1:02d}.png")

                generation_id: str | None = None
                if parent_id is not None:
                    entry_status("extending")
                    try:
                        raw_data = provider._sync_extend(
                            parent_id, scene_prompt, reference, provider.tier, provider.orientation
                        )
                        generation_id = str(raw_data.get("id"))
                    except Exception:  # noqa: BLE001 - fall back to fresh submit
                        generation_id = None
                if generation_id is None:
                    entry_status("submitting")
                    submit_prompt = provider.REFERENCE_PREFIX + scene_prompt if reference else scene_prompt
                    raw_data = provider._sync_submit(submit_prompt, provider.tier, provider.orientation, reference)
                    generation_id = str(raw_data.get("id"))

                self._set_scene(job_id, scene, status="rendering", generation_id=generation_id)
                done = provider._sync_status(generation_id, wait=True)
                if str(done.get("status") or "").lower() not in {"succeeded", "success", "completed"}:
                    raise AgentError(f"scene {scene} render failed: {str(done.get('error') or done.get('status'))[:200]}")
                video_url = done.get("video_url")
                if not video_url:
                    raise AgentError(f"scene {scene} finished without a video URL")

                entry_status("downloading")
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                    "Referer": "https://www.thisagentdoesnotexist.com/",
                }
                resp = requests.get(video_url, headers=headers, timeout=300)
                resp.raise_for_status()
                raw.write_bytes(resp.content)

                entry_status("normalizing")
                normalize_clip(raw, final)
                raw.unlink(missing_ok=True)
                self._set_scene(job_id, scene, status="done", filename=final.name)

                parent_id = generation_id
                parent_clip = final
