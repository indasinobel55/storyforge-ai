from __future__ import annotations

import asyncio
import time

import requests

from tests.helpers import running_server


def _extract_ids(payload):
    if isinstance(payload, list):
        return [p["id"] for p in payload]
    if isinstance(payload, dict):
        for key in ("projects", "items", "data", "results"):
            if key in payload:
                val = payload[key]
                if isinstance(val, list):
                    return [p["id"] for p in val]
                if isinstance(val, dict):
                    return list(val.keys())
        # get-by-id responses sometimes return the object itself.
        if "id" in payload and isinstance(payload["id"], str):
            return [payload["id"]]
    return []


def test_multi_user_isolation(tmp_path):
    log_path = tmp_path / "server.log"
    with running_server("local", log_path) as base:
        alice = requests.Session()
        rb = alice.post(
            f"{base}/api/auth/register",
            json={
                "email": "alice-iso@example.com",
                "password": "Testpass123",
                "display_name": "Alice",
            },
            timeout=30,
        )
        rb.raise_for_status()
        alice_csrf = rb.json()["csrf_token"]

        bob = requests.Session()
        rb = bob.post(
            f"{base}/api/auth/register",
            json={
                "email": "bob-iso@example.com",
                "password": "Testpass123",
                "display_name": "Bob",
            },
            timeout=30,
        )
        rb.raise_for_status()
        bob_csrf = rb.json()["csrf_token"]

        headers_a = {"X-CSRF-Token": alice_csrf}
        headers_b = {"X-CSRF-Token": bob_csrf}

        # Alice creates a project.
        ap = alice.post(
            f"{base}/api/projects",
            headers=headers_a,
            json={
                "title": "alice-secret",
                "script": "Alice writes a secret scene here.",
                "target_scene_count": 1,
                "scene_seconds": 2,
                "target_duration_seconds": 4,
                "auto_start": True,
                "start_planning": True,
                "provider": "simulated",
            },
            timeout=30,
        )
        ap.raise_for_status()
        alice_project_id = ap.json()["id"]

        # Bob cannot list or read Alice's project.
        alice_list = alice.get(f"{base}/api/projects", timeout=30).json()
        bob_list = bob.get(f"{base}/api/projects", timeout=30).json()
        alice_ids = _extract_ids(alice_list)
        bob_ids = _extract_ids(bob_list)
        assert alice_project_id not in bob_ids
        assert alice_project_id in alice_ids

        # Bob cannot approve Alice's project.
        bob_approve = bob.post(
            f"{base}/api/projects/{alice_project_id}/approve",
            headers=headers_b,
            timeout=30,
        )
        assert bob_approve.status_code in {401, 403, 404}, bob_approve.status_code

        # Bob cannot access Alice's scenes.
        bob_scenes = bob.get(
            f"{base}/api/projects/{alice_project_id}/scenes", timeout=30
        )
        bob_scenes_text = bob_scenes.text[:200]
        assert bob_scenes.status_code in {401, 403, 404}, bob_scenes_text

        # Advance Alice's pipeline fully so we can test storage isolation.
        from workers.generation_worker import GenerationWorker

        worker = GenerationWorker("alice-worker")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            asyncio.run(worker.run_until_idle(max_iterations=1))
            detail = alice.get(
                f"{base}/api/projects/{alice_project_id}", timeout=30
            ).json()
            if detail["status"] == "COMPLETED":
                break
            time.sleep(0.2)
        else:
            raise AssertionError(
                f"Alice pipeline did not complete: {detail.get('error')}"
            )

        # Bob cannot download Alice's final video.
        alice_detail = alice.get(
            f"{base}/api/projects/{alice_project_id}", timeout=30
        ).json()
        video_id = alice_detail["final_video_id"]
        assert video_id is not None
        bob_video = bob.get(
            f"{base}/api/videos/{video_id}/download", timeout=30
        )
        assert bob_video.status_code in {401, 403, 404}, bob_video.status_code        # Alice can download her own video.  The project endpoint already
        # returned 200 for this session, so the download endpoint should
        # recognize the authenticated owner.
        alice_video = alice.get(
            f"{base}/api/videos/{video_id}/download", timeout=30
        )
        print(
            "DEBUG alice download status:",
            alice_video.status_code,
            "text:",
            alice_video.text[:200],
        )
        assert alice_video.status_code == 200, (
            alice_video.status_code,
            alice_video.text[:200],
        )
        assert len(alice_video.content) > 0
