from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import _is_authorized, app, settings


AUTH_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def secure_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "orbis_api_token", "test-token")
    monkeypatch.setattr(settings, "metrics_api_token", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "database_auto_create_tables", False)
    monkeypatch.setattr(settings, "database_auto_migrate", False)
    monkeypatch.setattr(settings, "database_ssl", "require")


def test_bearer_token_auth_uses_constant_time_compare() -> None:
    assert _is_authorized("Bearer test-token", "test-token") is True
    assert _is_authorized("Bearer wrong-token", "test-token") is False
    assert _is_authorized("Basic test-token", "test-token") is False


def test_mutating_endpoints_require_authorization() -> None:
    with TestClient(app) as client:
        unauthorized = client.post(
            "/api/memories",
            json={
                "title": "Brand voice",
                "category": "brand",
                "content": "Use concise language.",
                "enabled": True,
            },
        )
        authorized = client.post(
            "/api/memories",
            headers=AUTH_HEADERS,
            json={
                "title": "Brand voice",
                "category": "brand",
                "content": "Use concise language.",
                "enabled": True,
            },
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


def test_metrics_requires_authorization_when_token_is_configured() -> None:
    with TestClient(app) as client:
        unauthorized = client.get("/metrics")
        authorized = client.get("/metrics", headers=AUTH_HEADERS)

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


def test_health_reports_database_status() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database_status"] == "disabled"


def test_run_detail_rejects_invalid_uuid_path() -> None:
    with TestClient(app) as client:
        response = client.get("/api/runs/not-a-uuid", headers=AUTH_HEADERS)

    assert response.status_code == 422


def test_plan_request_rejects_oversized_memory_id_list() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/plans",
            headers=AUTH_HEADERS,
            json={
                "task": "Create a short support workflow.",
                "memory_ids": [str(uuid4()) for _ in range(26)],
                "agent_profiles": [],
            },
        )

    assert response.status_code == 422


def test_production_security_guard_rejects_missing_api_token() -> None:
    production_settings = Settings(
        APP_ENV="production",
        ORBIS_API_TOKEN="",
        DATABASE_AUTO_CREATE_TABLES=False,
        DATABASE_SSL="require",
        FRONTEND_ORIGINS="https://orbis.example.com",
        FRONTEND_ORIGIN="",
    )

    with pytest.raises(RuntimeError, match="ORBIS_API_TOKEN"):
        production_settings.validate_security_settings()
