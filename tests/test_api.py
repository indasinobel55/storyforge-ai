from __future__ import annotations


def test_registration_login_and_config(client):
    email = "api-first@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "Testpass123", "display_name": "First"},
    )
    assert response.status_code == 201
    csrf = response.json()["csrf_token"]
    assert response.json()["user"]["email"] == email

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["id"] == response.json()["user"]["id"]

    config = client.get("/api/config")
    assert config.status_code == 200
    assert config.json()["execution_mode"] == "cloud"

    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert client.get("/api/auth/me").status_code == 401

    login = client.post("/api/auth/login", json={"email": email, "password": "Testpass123"})
    assert login.status_code == 200
    assert login.json()["csrf_token"]


def test_csrf_is_required_for_unsafe_requests(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "csrf@example.com", "password": "Testpass123", "display_name": "CSRF"},
    )
    assert response.status_code == 201
    blocked = client.post("/api/projects", json={"title": "x", "script": "A" * 30})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "CSRF validation failed"


def test_projects_are_isolated_between_users(client, user_session):
    first, headers = user_session("owner@example.com")
    created = client.post(
        "/api/projects",
        headers=headers,
        json={
            "title": "Private project",
            "script": "A private story that must never be visible to another account.",
            "start_planning": False,
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    user_session("intruder@example.com")
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get("/api/projects").json()["total"] == 0

    client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Testpass123"})
    assert client.get(f"/api/projects/{project_id}").status_code == 200


def test_taaft_provider_is_gated(client, user_session):
    _, headers = user_session("taaft@example.com")
    response = client.post(
        "/api/projects",
        headers=headers,
        json={
            "title": "Blocked provider",
            "script": "A story that should not be submitted to an unauthorized provider.",
            "provider": "taaft",
            "start_planning": False,
        },
    )
    assert response.status_code == 409
    assert "TAAFT" in response.json()["detail"]


def test_local_execution_claim_requires_local_mode(client, user_session):
    _, headers = user_session("localmode@example.com")
    token_response = client.post("/api/execution/token", headers=headers, json={"label": "test"})
    assert token_response.status_code == 201
    token = token_response.json()["token"]
    claim = client.post("/api/execution/claim", headers={"Authorization": f"Bearer {token}"})
    assert claim.status_code == 409
    assert "EXECUTION_MODE=local" in claim.json()["detail"]
    assert client.post("/api/execution/claim", headers={"Authorization": "Bearer nope"}).status_code == 401
