import asyncio
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import Settings
from app.db import DatabaseRepository, SessionAuthRecord
from app.main import (
    _auth_failures,
    _is_authorized,
    app,
    get_database,
    require_api_token,
    settings,
)
from app.schemas import AdminUser, AuthUser, MemoryCreateRequest, MemoryItem, SystemSettings, UserRole
from app.security import hash_pbkdf2_password


AUTH_HEADERS = {"Authorization": "Bearer test-token"}


class FakeAuthDatabase:
    def __init__(self) -> None:
        self.system_settings = SystemSettings()
        self.users: dict[str, dict[str, object]] = {}
        self.sessions: dict[str, dict[str, str]] = {}
        self.memories: list[MemoryItem] = []

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def is_persistence_configured(self) -> bool:
        return True

    async def get_system_settings(self) -> SystemSettings:
        return self.system_settings

    async def save_system_settings(self, settings: SystemSettings) -> SystemSettings:
        self.system_settings = settings
        return settings

    async def create_user(
        self,
        user_id: str,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> AuthUser:
        row = {
            "id": user_id,
            "email": email,
            "display_name": display_name,
            "password_hash": password_hash,
            "role": "guest",
            "is_active": True,
            "created_at": "2026-05-31T00:00:00+00:00",
            "updated_at": "2026-05-31T00:00:00+00:00",
        }
        self.users[user_id] = row
        return AuthUser(
            id=user_id,
            email=email,
            display_name=display_name,
            role="guest",
            created_at=str(row["created_at"]),
        )

    async def get_user_by_email(self, email: str) -> dict[str, object] | None:
        for row in self.users.values():
            if row["email"] == email:
                return row
        return None

    async def create_session(
        self,
        token_hash: str,
        user_id: str,
        expires_at: object,
        csrf_hash: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> None:
        self.sessions[token_hash] = {"user_id": user_id, "csrf_hash": csrf_hash}

    async def get_user_by_session(self, token_hash: str) -> AuthUser | None:
        session = self.sessions.get(token_hash)
        user_id = session["user_id"] if session else None
        if user_id is None:
            return None
        row = self.users[user_id]
        if not bool(row["is_active"]):
            return None
        return AuthUser(
            id=str(row["id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            role=cast(UserRole, row["role"]),
            created_at=str(row["created_at"]),
        )

    async def get_session_auth(self, token_hash: str) -> SessionAuthRecord | None:
        user = await self.get_user_by_session(token_hash)
        session = self.sessions.get(token_hash)
        if user is None or session is None:
            return None
        return SessionAuthRecord(user=user, csrf_hash=session["csrf_hash"])

    async def rotate_session_csrf(self, token_hash: str, csrf_hash: str) -> None:
        if token_hash in self.sessions:
            self.sessions[token_hash]["csrf_hash"] = csrf_hash

    async def delete_expired_sessions(self) -> None:
        return None

    async def update_password_hash(self, user_id: str, password_hash: str) -> None:
        self.users[user_id]["password_hash"] = password_hash

    async def get_user_by_id(self, user_id: str) -> AuthUser | None:
        row = self.users.get(user_id)
        if row is None:
            return None
        return AuthUser(
            id=str(row["id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            role=cast(UserRole, row["role"]),
            created_at=str(row["created_at"]),
        )

    async def delete_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    async def list_users(self) -> list[AdminUser]:
        return [
            AdminUser(
                id=str(row["id"]),
                email=str(row["email"]),
                display_name=str(row["display_name"]),
                role=cast(UserRole, row["role"]),
                created_at=str(row["created_at"]),
                is_active=bool(row["is_active"]),
                updated_at=str(row["updated_at"]),
            )
            for row in self.users.values()
        ]

    async def update_user_role(
        self,
        user_id: str,
        role: UserRole,
        is_active: bool | None,
    ) -> AdminUser | None:
        row = self.users.get(user_id)
        if row is None:
            return None
        row["role"] = role
        if is_active is not None:
            row["is_active"] = is_active
        row["updated_at"] = "2026-05-31T00:01:00+00:00"
        return AdminUser(
            id=str(row["id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            role=cast(UserRole, row["role"]),
            created_at=str(row["created_at"]),
            is_active=bool(row["is_active"]),
            updated_at=str(row["updated_at"]),
        )

    async def create_memory(self, item_id: str, payload: MemoryCreateRequest) -> MemoryItem:
        item = MemoryItem(
            id=item_id,
            title=payload.title,
            category=payload.category,
            content=payload.content,
            enabled=payload.enabled,
            created_at="2026-05-31T00:00:00+00:00",
        )
        self.memories.append(item)
        return item


@pytest.fixture(autouse=True)
def secure_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "orbis_api_token", "test-token")
    monkeypatch.setattr(settings, "metrics_api_token", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "database_required", False)
    monkeypatch.setattr(settings, "database_auto_create_tables", False)
    monkeypatch.setattr(settings, "database_auto_migrate", False)
    monkeypatch.setattr(settings, "database_ssl", "require")
    monkeypatch.setattr(settings, "session_cookie_name", "orbis_session")
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    monkeypatch.setattr(settings, "session_cookie_samesite", "lax")
    monkeypatch.setattr(settings, "session_cookie_domain", "")
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", 5)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 900)
    _auth_failures.clear()


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


def test_system_read_endpoints_require_authorization() -> None:
    with TestClient(app) as client:
        agents_unauthorized = client.get("/api/agents")
        templates_unauthorized = client.get("/api/templates")
        agents_authorized = client.get("/api/agents", headers=AUTH_HEADERS)
        templates_authorized = client.get("/api/templates", headers=AUTH_HEADERS)

    assert agents_unauthorized.status_code == 401
    assert templates_unauthorized.status_code == 401
    assert agents_authorized.status_code == 200
    assert templates_authorized.status_code == 200


def test_cors_preflight_allows_admin_patch_requests() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/admin/settings",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "X-CSRF-Token",
            },
        )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "X-CSRF-Token" in response.headers["access-control-allow-headers"]


def test_development_fallback_does_not_bypass_configured_database_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "orbis_api_token", "")
    fake_database = FakeAuthDatabase()
    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("testclient", 50000),
            "path": "/",
        }
    )

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            require_api_token(request, "", cast(DatabaseRepository, fake_database))
        )

    assert caught.value.status_code == 401


def test_register_creates_guest_user_and_session() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "person@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "Person",
                },
            )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["user"]["role"] == "guest"
    assert payload["token"] == ""
    assert payload["csrf_token"]
    assert "orbis_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert len(fake_database.users) == 1
    assert len(fake_database.sessions) == 1


def test_secure_cookie_flags_can_be_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "session_cookie_secure", True)
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app, base_url="https://testserver") as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "secure@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "Secure",
                },
            )
    finally:
        app.dependency_overrides.clear()

    cookie = response.headers["set-cookie"]
    assert response.status_code == 200
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie


def test_cookie_session_requires_csrf_for_mutations() -> None:
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            register = client.post(
                "/api/auth/register",
                json={
                    "email": "csrf@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "CSRF",
                },
            )
            missing_csrf = client.post("/api/auth/logout")
            valid_csrf = client.post(
                "/api/auth/logout",
                headers={"X-CSRF-Token": register.json()["csrf_token"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert register.status_code == 200
    assert missing_csrf.status_code == 403
    assert valid_csrf.status_code == 200


def test_register_respects_registration_switch() -> None:
    fake_database = FakeAuthDatabase()
    fake_database.system_settings = SystemSettings(register_enabled=False)
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "person@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                    "display_name": "Person",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Registration is disabled."


def test_login_rate_limit_blocks_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", 2)
    fake_database = FakeAuthDatabase()
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/auth/login",
                json={"email": "missing@example.com", "password": "bad"},  # pragma: allowlist secret
            )
            second = client.post(
                "/api/auth/login",
                json={"email": "missing@example.com", "password": "bad"},  # pragma: allowlist secret
            )
            locked = client.post(
                "/api/auth/login",
                json={"email": "missing@example.com", "password": "bad"},  # pragma: allowlist secret
            )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 401
    assert second.status_code == 401
    assert locked.status_code == 429


def test_pbkdf2_password_is_rehashed_to_argon2_on_login() -> None:
    fake_database = FakeAuthDatabase()
    user_id = str(uuid4())
    fake_database.users[user_id] = {
        "id": user_id,
        "email": "legacy@example.com",
        "display_name": "Legacy",
        "password_hash": hash_pbkdf2_password("strong-password"),  # pragma: allowlist secret
        "role": "guest",
        "is_active": True,
        "created_at": "2026-05-31T00:00:00+00:00",
        "updated_at": "2026-05-31T00:00:00+00:00",
    }
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login",
                json={
                    "email": "legacy@example.com",
                    "password": "strong-password",  # pragma: allowlist secret
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert str(fake_database.users[user_id]["password_hash"]).startswith("$argon2")


def test_admin_can_update_system_settings_and_user_role() -> None:
    fake_database = FakeAuthDatabase()
    created = asyncio.run(
        fake_database.create_user(
            str(uuid4()),
            "person@example.com",
            "Person",
            "stored-password-hash",
        )
    )
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            settings_response = client.patch(
                "/api/admin/settings",
                headers=AUTH_HEADERS,
                json={"system_enabled": False, "register_enabled": False},
            )
            role_response = client.patch(
                f"/api/admin/users/{created.id}",
                headers=AUTH_HEADERS,
                json={"role": "vip", "is_active": False},
            )
    finally:
        app.dependency_overrides.clear()

    assert settings_response.status_code == 200
    assert settings_response.json() == {
        "system_enabled": False,
        "register_enabled": False,
    }
    assert role_response.status_code == 200
    assert role_response.json()["role"] == "vip"
    assert role_response.json()["is_active"] is False


def test_last_active_admin_cannot_be_downgraded() -> None:
    fake_database = FakeAuthDatabase()
    admin_id = str(uuid4())
    fake_database.users[admin_id] = {
        "id": admin_id,
        "email": "admin@example.com",
        "display_name": "Admin",
        "password_hash": "stored-password-hash",  # pragma: allowlist secret
        "role": "admin",
        "is_active": True,
        "created_at": "2026-05-31T00:00:00+00:00",
        "updated_at": "2026-05-31T00:00:00+00:00",
    }
    app.dependency_overrides[get_database] = lambda: fake_database
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/admin/users/{admin_id}",
                headers=AUTH_HEADERS,
                json={"role": "vip", "is_active": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "At least one active admin must remain."


def test_health_reports_database_status() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database_status"] == "disabled"
    assert response.json()["database_error_code"] == ""


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
        SESSION_COOKIE_SECURE=True,
    )

    with pytest.raises(RuntimeError, match="ORBIS_API_TOKEN"):
        production_settings.validate_security_settings()


def test_production_security_guard_accepts_supabase_pooler_ssl_mode() -> None:
    production_settings = Settings(
        APP_ENV="production",
        ORBIS_API_TOKEN="test-token",
        DATABASE_AUTO_CREATE_TABLES=False,
        DATABASE_SSL="insecure-require",
        FRONTEND_ORIGINS="https://orbis.example.com",
        FRONTEND_ORIGIN="",
        SESSION_COOKIE_SECURE=True,
    )

    production_settings.validate_security_settings()


def test_production_security_guard_rejects_disabled_database_ssl() -> None:
    production_settings = Settings(
        APP_ENV="production",
        ORBIS_API_TOKEN="test-token",
        DATABASE_AUTO_CREATE_TABLES=False,
        DATABASE_SSL="disabled",
        FRONTEND_ORIGINS="https://orbis.example.com",
        FRONTEND_ORIGIN="",
        SESSION_COOKIE_SECURE=True,
    )

    with pytest.raises(RuntimeError, match="Encrypted DATABASE_SSL"):
        production_settings.validate_security_settings()


def test_production_security_guard_rejects_optional_database() -> None:
    production_settings = Settings(
        APP_ENV="production",
        ORBIS_API_TOKEN="test-token",
        DATABASE_REQUIRED=False,
        DATABASE_AUTO_CREATE_TABLES=False,
        DATABASE_SSL="require",
        FRONTEND_ORIGINS="https://orbis.example.com",
        FRONTEND_ORIGIN="",
        SESSION_COOKIE_SECURE=True,
    )

    with pytest.raises(RuntimeError, match="DATABASE_REQUIRED"):
        production_settings.validate_security_settings()
