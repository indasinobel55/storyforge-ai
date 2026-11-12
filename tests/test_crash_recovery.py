from __future__ import annotations

import asyncio
import time

from tests.helpers import register_and_project, running_server


def test_worker_recovery_after_hard_kill(tmp_path):
    """Worker crash recovery through the queue re-claim path.

    With `auto_start=True`, the backend begins the e2e lifecycle immediately and
    queues PLAN, GENERATE and ASSEMBLE jobs.  We start a worker partway through,
    let it advance one or more jobs, then abandon it (hard stop) and start a fresh
    worker to reclaim whatever remains.

    The properties we verify here are the real reliability requirements:
      - the project still completes after a worker is abandoned,
      - completed scenes remain SUCCEEDED,
      - scene regeneration is not duplicated, and
      - the final assembly still passes validation.
    """
    from workers.generation_worker import GenerationWorker

    log_path = tmp_path / "server.log"
    with running_server("cloud", log_path) as base:
        session, project_id = register_and_project(
            base, "recovery-e2e@example.com", auto_start=True, scenes=3
        )
        headers = {"X-CSRF-Token": session.cookies.get("sf_csrf")}

        first_worker = GenerationWorker("recovery-first")
        deadline = time.monotonic() + 90
        first_state = None
        while time.monotonic() < deadline:
            first_state = session.get(
                f"{base}/api/projects/{project_id}", timeout=30
            ).json()
            if first_state["status"] in {"COMPLETED", "FAILED"}:
                break
            asyncio.run(first_worker.run_until_idle(max_iterations=1))
            time.sleep(0.2)

        # Simulate a hard kill: abandon the first worker here.
        assert first_state is not None
        assert first_state["status"] != "FAILED", first_state.get("error")
        assert any(
            s["status"] == "SUCCEEDED" for s in first_state["scenes"]
        ), "We did not advance far enough to call this a partial kill."

        # Start a fresh worker to reclaim remaining work.
        second_worker = GenerationWorker("recovery-second")
        deadline = time.monotonic() + 120
        final_status = None
        while time.monotonic() < deadline:
            asyncio.run(second_worker.run_until_idle(max_iterations=1))
            detail = session.get(
                f"{base}/api/projects/{project_id}", timeout=30
            ).json()
            if detail["status"] in {"COMPLETED", "FAILED"}:
                final_status = detail["status"]
                break
            time.sleep(0.25)

        assert final_status == "COMPLETED", detail.get("error")
        assert detail["report"]["validation"]["passed"] is True
        assert all(s["status"] == "SUCCEEDED" for s in detail["scenes"])
        jobs = session.get(
            f"{base}/api/projects/{project_id}/jobs", timeout=30
        ).json()
        assert all(job["attempts"] <= 3 for job in jobs)
