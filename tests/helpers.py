from __future__ import annotations

import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def running_server(mode: str, log_path: Path):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(__import__("os").environ)
    env["EXECUTION_MODE"] = mode
    env["PYTHONPATH"] = str(ROOT)
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        ready = False
        for _ in range(120):
            if process.poll() is not None:
                break
            try:
                if requests.get(f"{base}/api/health", timeout=2).status_code == 200:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.25)
        if not ready:
            log.close()
            raise RuntimeError(f"Server failed to start:\n{log_path.read_text(encoding='utf-8', errors='replace')}")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()


def register_and_project(base: str, email: str, *, auto_start: bool = True, scenes: int = 3) -> tuple[requests.Session, str]:
    session = requests.Session()
    response = session.post(
        f"{base}/api/auth/register",
        json={"email": email, "password": "Testpass123", "display_name": "E2E"},
        timeout=30,
    )
    response.raise_for_status()
    headers = {"X-CSRF-Token": response.json()["csrf_token"]}
    project = session.post(
        f"{base}/api/projects",
        headers=headers,
        json={
            "title": "E2E project",
            "script": (
                "A curious child follows a glowing firefly into an ancient forest and discovers a hidden village. "
                "Kindness lights the way home."
            ),
            "target_scene_count": scenes,
            "scene_seconds": 2,
            "target_duration_seconds": scenes * 2,
            "auto_start": auto_start,
            "start_planning": True,
            "provider": "simulated",
        },
        timeout=30,
    )
    project.raise_for_status()
    return session, project.json()["id"]
