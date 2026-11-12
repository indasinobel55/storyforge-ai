from __future__ import annotations

import asyncio
import time

from tests.helpers import register_and_project, running_server


def test_cloud_worker_end_to_end(tmp_path):
    log_path = tmp_path / "server.log"
    with running_server("cloud", log_path) as base:
        session, project_id = register_and_project(base, "cloud-e2e@example.com", scenes=2)

        from workers.generation_worker import GenerationWorker

        worker = GenerationWorker("pytest-cloud-worker")
        processed = asyncio.run(worker.run_until_idle(max_iterations=10))
        assert processed >= 3

        deadline = time.monotonic() + 60
        detail = {}
        while time.monotonic() < deadline:
            detail = session.get(f"{base}/api/projects/{project_id}", timeout=30).json()
            if detail["status"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.5)

        assert detail["status"] == "COMPLETED", detail.get("error")
        assert detail["execution_mode"] == "cloud"
        assert all(scene["status"] == "SUCCEEDED" for scene in detail["scenes"])
        assert detail["report"]["validation"]["passed"] is True
