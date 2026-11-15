"""GitHub Actions worker for the TAAFT-only site.

Runs on a free ubuntu runner (7GB RAM): fetches the job + TAAFT session from
the site, automates TAAFT scene by scene (extend chaining with last-frame
references), and uploads progress + finished mp4s back to the site.
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
JOB_ID = os.environ["JOB_ID"]
WORK_DIR = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "taaft" / JOB_ID


def api(method: str, path: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers["X-Site-Token"] = SITE_TOKEN
    return requests.request(method, f"{SITE_URL}{path}", headers=headers, timeout=120, **kwargs)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def progress(scene: int, status: str, generation_id: str | None = None) -> None:
    for attempt in range(3):
        try:
            r = api("POST", f"/api/jobs/{JOB_ID}/progress",
                    json={"scene": scene, "status": status, "generation_id": generation_id})
            if r.status_code == 200:
                return
            log(f"progress HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            log(f"progress failed: {exc}")
        time.sleep(5 * (attempt + 1))


def upload_file(scene: int, path: Path) -> None:
    for attempt in range(4):
        try:
            with open(path, "rb") as f:
                r = api("POST", f"/api/jobs/{JOB_ID}/files/{path.name}",
                        files={"file": (path.name, f, "video/mp4")})
            if r.status_code == 200:
                progress(scene, "done", None)
                return
            log(f"upload HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            log(f"upload failed: {exc}")
        time.sleep(10 * (attempt + 1))
    raise AgentError(f"could not upload {path.name}")


def main() -> None:
    job = api("GET", f"/api/jobs/{JOB_ID}").json()
    prompt = job["prompt"]
    scene_count = int(job["scene_count"])
    log(f"job {JOB_ID}: {scene_count} scene(s)")

    session_resp = api("GET", "/api/session/file")
    session_resp.raise_for_status()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    session_path = WORK_DIR / "session.json"
    session_path.write_bytes(session_resp.content)
    log(f"session fetched ({len(session_resp.content)} bytes)")

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
                raw = WORK_DIR / f"scene_{scene:02d}_raw.mp4"
                final = WORK_DIR / f"scene_{scene:02d}.mp4"

                reference: Path | None = None
                if parent_clip is not None:
                    progress(scene, "reference")
                    reference = extract_last_frame(parent_clip, WORK_DIR / f"frame_{scene - 1:02d}.png")

                generation_id: str | None = None
                if parent_id is not None:
                    progress(scene, "extending")
                    try:
                        raw_data = provider._sync_extend(
                            parent_id, scene_prompt, reference, provider.tier, provider.orientation
                        )
                        generation_id = str(raw_data.get("id"))
                    except Exception as exc:  # noqa: BLE001
                        log(f"extend failed, falling back to fresh submit: {exc}")
                        generation_id = None
                if generation_id is None:
                    progress(scene, "submitting")
                    submit_prompt = provider.REFERENCE_PREFIX + scene_prompt if reference else scene_prompt
                    raw_data = provider._sync_submit(submit_prompt, provider.tier, provider.orientation, reference)
                    generation_id = str(raw_data.get("id"))

                progress(scene, "rendering", generation_id)
                done = provider._sync_status(generation_id, wait=True)
                status = str(done.get("status") or "").lower()
                if status not in {"succeeded", "success", "completed"}:
                    raise AgentError(
                        f"scene {scene} render failed: {str(done.get('error') or done.get('status'))[:200]}"
                    )
                video_url = done.get("video_url")
                if not video_url:
                    raise AgentError(f"scene {scene} finished without a video URL")

                progress(scene, "downloading")
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                    "Referer": "https://www.thisagentdoesnotexist.com/",
                }
                resp = requests.get(video_url, headers=headers, timeout=300)
                resp.raise_for_status()
                raw.write_bytes(resp.content)

                progress(scene, "normalizing")
                normalize_clip(raw, final)
                raw.unlink(missing_ok=True)

                progress(scene, "uploading")
                upload_file(scene, final)

                parent_id = generation_id
                parent_clip = final
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"[:600]
        log(f"FAILED: {error}")

    for attempt in range(3):
        try:
            r = api("POST", f"/api/jobs/{JOB_ID}/complete", json={"error": error})
            if r.status_code == 200:
                break
        except Exception as exc:  # noqa: BLE001
            log(f"complete failed: {exc}")
        time.sleep(10 * (attempt + 1))
    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
