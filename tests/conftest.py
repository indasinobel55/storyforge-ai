from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMP = Path(tempfile.mkdtemp(prefix="storyforge-tests-"))
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{(TEMP / 'tests.db').as_posix()}"


def force_sqlite_test_environment() -> str:
    """Force every database setting onto an isolated temporary SQLite file.

    Unconditional assignment (never ``setdefault``) so an ambient production URL
    can never leak into a test session.
    """
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["MIGRATION_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["AUTO_CREATE_SCHEMA"] = "true"
    return TEST_DATABASE_URL


force_sqlite_test_environment()

os.environ.setdefault("EXECUTION_MODE", "cloud")
os.environ.setdefault("STORAGE_DIR", str(TEMP / "storage"))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("SIMULATED_GENERATION_SECONDS", "0.2")
os.environ.setdefault("DEV_EXPOSE_RESET_TOKEN", "true")

from backend.app.config import get_settings  # noqa: E402

_RESOLVED_TEST_URL = get_settings().database_url
if not _RESOLVED_TEST_URL.startswith("sqlite"):
    pytest.exit(
        "Refusing to run tests: the resolved database URL is not SQLite. "
        "Tests must never reach a remote database.",
        returncode=3,
    )

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_test_env():
    """Snapshot os.environ around every test.

    Several suites mutate DATABASE_URL / STORAGE_DIR / EXECUTION_MODE to point
    at their own temporary files. Without restoring, later tests (in-process
    workers and spawned uvicorn subprocesses alike) inherit a polluted
    environment and fail with mismatched or missing databases.
    """
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_session(client: TestClient):
    def register(email: str, password: str = "Testpass123", name: str = "Tester") -> tuple[dict, dict]:
        response = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": name},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        return body, {"X-CSRF-Token": body["csrf_token"]}

    return register
