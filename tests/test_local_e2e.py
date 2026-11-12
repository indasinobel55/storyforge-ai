from __future__ import annotations

import asyncio
import time

from local_agent import LocalApiClient, LocalConfig, LocalRunner
from tests.helpers import register_and_project, running_server


def test_local_execution_end_to_end(tmp_path):
    log_path = tmp_path / "server.log"
    with running_server("local", log_path) as base:
        session, project_id = register_and_project(base, "local-e2e@example.com", scenes=2)
        headers = {"X-CSRF-Token": session.cookies.get("sf_csrf")}
        token = session.post(
            f"{base}/api/execution/token", headers=headers, json={"label": "pytest local"}, timeout=30
        ).json()["token"]

        runner = LocalRunner(
            LocalApiClient(base, token),
            LocalConfig(work_dir=tmp_path / "work", simulated_generation_seconds=0.2, simulated_clip_seconds=2.0),
        )
        processed = asyncio.run(runner.run_until_idle(max_jobs=10))
        assert processed >= 3

        deadline = time.monotonic() + 60
        detail = {}
        while time.monotonic() < deadline:
            detail = session.get(f"{base}/api/projects/{project_id}", timeout=30).json()
            if detail["status"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.5)

        assert detail["status"] == "COMPLETED", detail.get("error")
        assert detail["execution_mode"] == "local"
        assert detail["progress"] == 100
        assert all(scene["status"] == "SUCCEEDED" for scene in detail["scenes"])
        assert detail["final_video_id"]
        assert detail["report"]["validation"]["passed"] is True

        stream = session.get(
            f"{base}/api/videos/{detail['final_video_id']}/stream",
            headers={"Range": "bytes=0-511"},
            timeout=30,
        )
        assert stream.status_code == 206
        assert len(stream.content) == 512
