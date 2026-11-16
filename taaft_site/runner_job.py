"""TAAFT job runner.

Default mode (used by GitHub Actions): the job id comes from the JOB_ID env
var and a single job is rendered.

Poll mode (used by an always-on external runner, e.g. Oracle free VM): set
``RUNNER_MODE=poll``; the process loops forever, claiming queued jobs from
the site (``POST /api/jobs/{id}/claim``) and rendering them one at a time.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from agent.core.errors import AgentError
from agent.providers.taaft import TaaftProvider
from taaft_site.worker import extract_last_frame, normalize_clip

SITE_URL = os.environ["SITE_URL"].rstrip("/")
SITE_TOKEN = os.environ["SITE_TOKEN"]
WORK_BASE = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "taaft"


def api(method: str, path: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers["X-Site-Token"] = SITE_TOKEN
    return requests.request(method, f"{SITE_URL}{path}", headers=headers, timeout=120, **kwargs)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def progress(job_id: str, scene: int, status: str, generation_id: str | None = None) -> None:
    for attempt in range(3):
        try:
            r = api("POST", f"/api/jobs/{job_id}/progress",
                    json={"scene": scene, "status": status, "generation_id": generation_id})
            if r.status_code == 200:
                return
            log(f"progress HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            log(f"progress failed: {exc}")
        time.sleep(5 * (attempt + 1))


def upload_file(job_id: str, scene: int, path: Path) -> None:
    for attempt in range(4):
        try:
            with open(path, "rb") as f:
                r = api("POST", f"/api/jobs/{job_id}/files/{path.name}",
                        files={"file": (path.name, f, "video/mp4")})
            if r.status_code == 200:
                progress(job_id, scene, "done", None)
                return
            log(f"upload HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            log(f"upload failed: {exc}")
        time.sleep(10 * (attempt + 1))
    raise AgentError(f"could not upload {path.name}")


def _fetch_session(work_dir: Path) -> Path:
    session_resp = api("GET", "/api/session/file")
    session_resp.raise_for_status()
    work_dir.mkdir(parents=True, exist_ok=True)
    session_path = work_dir / "session.json"
    session_path.write_bytes(session_resp.content)
    log(f"session fetched ({len(session_resp.content)} bytes)")
    return session_path


def render_job(job_id: str) -> None:
    work_dir = WORK_BASE / job_id
    job = api("GET", f"/api/jobs/{job_id}").json()
    prompt = job["prompt"]
    scene_count = int(job["scene_count"])
    log(f"job {job_id}: {scene_count} scene(s)")

    session_path = _fetch_session(work_dir)

    provider = TaaftProvider(
        enabled=True,
        storage_state_path=session_path,
        headless=True,
        poll_seconds=20,
        job_timeout_seconds=3600,
        tier="quality",
        orientation="landscape",
    )

    error: str | None = None
    try:
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

                reference: Path | None = None
                if parent_clip is not None:
                    progress(job_id, scene, "reference")
                    reference = extract_last_frame(parent_clip, work_dir / f"frame_{scene - 1:02d}.png")

                generation_id: str | None = None
                if parent_id is not None:
                    progress(job_id, scene, "extending")
                    try:
                        raw_data = provider._sync_extend(
                            parent_id, scene_prompt, reference, provider.tier, provider.orientation
                        )
                        generation_id = str(raw_data.get("id"))
                    except Exception as exc:  # noqa: BLE001
                        log(f"extend failed, falling back to fresh submit: {exc}")
                        generation_id = None
                if generation_id is None:
                    progress(job_id, scene, "submitting")
                    submit_prompt = provider.REFERENCE_PREFIX + scene_prompt if reference else scene_prompt
                    raw_data = provider._sync_submit(submit_prompt, provider.tier, provider.orientation, reference)
                    generation_id = str(raw_data.get("id"))

                progress(job_id, scene, "rendering", generation_id)
                done = provider._sync_status(generation_id, wait=True)
                status = str(done.get("status") or "").lower()
                if status not in {"succeeded", "success", "completed"}:
                    raise AgentError(
                        f"scene {scene} render failed: {str(done.get('error') or done.get('status'))[:200]}"
                    )
                video_url = done.get("video_url")
                if not video_url:
                    raise AgentError(f"scene {scene} finished without a video URL")

                progress(job_id, scene, "downloading")
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                    "Referer": "https://www.thisagentdoesnotexist.com/",
                }
                resp = requests.get(video_url, headers=headers, timeout=300)
                resp.raise_for_status()
                raw.write_bytes(resp.content)

                progress(job_id, scene, "normalizing")
                normalize_clip(raw, final)
                raw.unlink(missing_ok=True)

                progress(job_id, scene, "uploading")
                upload_file(job_id, scene, final)

                parent_id = generation_id
                parent_clip = final
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"[:600]
        log(f"FAILED: {error}")

    for attempt in range(3):
        try:
            r = api("POST", f"/api/jobs/{job_id}/complete", json={"error": error})
            if r.status_code == 200:
                break
        except Exception as exc:  # noqa: BLE001
            log(f"complete failed: {exc}")
        time.sleep(10 * (attempt + 1))
    if error:
        raise SystemExit(1)


def claim_queued_job() -> str | None:
    try:
        listing = api("GET", "/api/jobs").json()
    except Exception as exc:  # noqa: BLE001
        log(f"job list failed: {exc}")
        return None
    for job in listing.get("jobs", []):
        if job.get("status") != "queued":
            continue
        job_id = job.get("job_id")
        if not job_id:
            continue
        try:
            r = api("POST", f"/api/jobs/{job_id}/claim")
            if r.status_code == 200:
                return job_id
            log(f"claim {job_id} -> HTTP {r.status_code} {r.text[:150]}")
        except Exception as exc:  # noqa: BLE001
            log(f"claim {job_id} failed: {exc}")
    return None


def poll_loop() -> None:
    log(f"poll mode: watching {SITE_URL} for queued jobs")
    idle_logged = False
    while True:
        job_id = claim_queued_job()
        if job_id is None:
            if not idle_logged:
                log("no queued jobs; idling")
                idle_logged = True
            time.sleep(30)
            continue
        idle_logged = False
        try:
            render_job(job_id)
        except Exception as exc:  # noqa: BLE001
            log(f"render_job crashed: {type(exc).__name__}: {exc}"[:400])


def main() -> None:
    if os.environ.get("RUNNER_MODE", "").strip().lower() == "poll":
        poll_loop()
        return
    render_job(os.environ["JOB_ID"])


if __name__ == "__main__":
    main()
