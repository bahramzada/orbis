import asyncio
from pathlib import Path
import ssl
from typing import cast

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from app import migration_runner
from app.config import Settings
from app.db import DatabaseRepository, _ssl_config, metadata
from app.main import _initialize_database


def test_database_url_is_optional() -> None:
    settings = Settings(DATABASE_URL="", DATABASE_REQUIRED=False)
    repository = DatabaseRepository(settings)

    assert settings.is_database_configured is False
    assert repository.is_persistence_configured is False
    assert repository.is_configured is False


def test_database_url_is_required_by_default() -> None:
    settings = Settings(DATABASE_URL="")

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        asyncio.run(_initialize_database(settings))


def test_supabase_postgres_url_is_converted_for_asyncpg() -> None:
    settings = Settings(
        DATABASE_URL=(
            "postgresql://postgres.example:secret"
            "@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
        )
    )

    assert settings.is_database_configured is True
    assert settings.sqlalchemy_database_url.startswith("postgresql+asyncpg://")


def test_placeholder_password_keeps_database_disabled() -> None:
    settings = Settings(
        DATABASE_URL=(
            "postgresql://postgres.example:[YOUR-PASSWORD]"
            "@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
        )
    )

    assert settings.is_database_configured is False


def test_database_ssl_setting_verifies_certificates_by_default() -> None:
    require_context = _ssl_config("require")
    true_context = _ssl_config("true")
    insecure_context = _ssl_config("insecure-require")

    assert isinstance(require_context, ssl.SSLContext)
    assert isinstance(true_context, ssl.SSLContext)
    assert require_context.verify_mode == ssl.CERT_REQUIRED
    assert require_context.check_hostname is True
    assert isinstance(insecure_context, ssl.SSLContext)
    assert insecure_context.verify_mode == ssl.CERT_NONE
    assert insecure_context.check_hostname is False
    assert _ssl_config("disable") is False
    assert _ssl_config("disabled") is False


def test_database_performance_indexes_are_declared() -> None:
    index_names = {
        index.name
        for table in metadata.tables.values()
        for index in table.indexes
    }

    assert "ix_workflow_runs_completed_at_desc" in index_names
    assert "ix_workflow_runs_status_completed_at_desc" in index_names
    assert "ix_workflow_logs_run_id_created_at" in index_names
    assert "ix_memory_items_enabled_created" in index_names
    assert "ix_tool_calls_run_id_created" in index_names
    assert "ix_run_evaluations_run_id_created" in index_names
    assert "ix_users_role_created" in index_names
    assert "ix_auth_sessions_user_expires" in index_names


def test_pool_settings_are_configurable() -> None:
    settings = Settings(
        DATABASE_URL=(
            "postgresql://postgres.example:secret"
            "@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
        ),
        DATABASE_POOL_SIZE=4,
        DATABASE_MAX_OVERFLOW=1,
        DATABASE_POOL_TIMEOUT_SECONDS=7,
        DATABASE_SSL="require",
    )

    repository = DatabaseRepository(settings)

    assert repository.is_persistence_configured is True
    assert repository.is_configured is True


def test_runtime_performance_settings_have_safe_defaults() -> None:
    settings = Settings(DATABASE_AUTO_MIGRATE=True)

    assert settings.workflow_max_concurrency >= 1
    assert settings.workflow_step_timeout_seconds > 0
    assert settings.openrouter_max_connections >= settings.openrouter_max_keepalive
    assert settings.openrouter_retry_attempts >= 1
    assert settings.database_pool_size >= 1
    assert Settings.model_fields["database_auto_migrate"].default is True
    assert Settings.model_fields["database_required"].default is True
    assert settings.database_migration_lock_id > 0
    assert settings.database_migration_lock_timeout_seconds > 0
    assert settings.database_migration_statement_timeout_seconds > 0
    assert settings.auth_session_cleanup_interval_seconds > 0
    assert settings.auth_session_touch_interval_seconds > 0
    assert settings.system_settings_cache_ttl_seconds > 0
    assert Settings(DATABASE_AUTO_MIGRATE=False).database_auto_migrate is False


def test_migration_runner_uses_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    settings = Settings(
        DATABASE_URL=(
            "postgresql://postgres.example:secret"
            "@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
        ),
        DATABASE_SSL="require",
    )

    def fake_upgrade(config: Config, revision: str) -> None:
        captured["settings"] = config.attributes["settings"]
        captured["revision"] = revision

    monkeypatch.setattr(migration_runner.command, "upgrade", fake_upgrade)

    migration_runner._upgrade_to_head(settings)

    assert captured == {"settings": settings, "revision": "head"}


def test_database_read_failure_disables_optional_persistence() -> None:
    asyncio.run(_run_database_read_failure_test())


async def _run_database_read_failure_test() -> None:
    class BrokenEngine:
        def connect(self) -> None:
            raise OSError("database unavailable")

    repository = DatabaseRepository(
        Settings(
            DATABASE_URL=(
                "postgresql://postgres.example:secret"
                "@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
            ),
            DATABASE_SSL="require",
        )
    )
    repository._engine = cast(AsyncEngine, BrokenEngine())

    assert await repository.list_agent_profiles() == []
    assert repository.is_persistence_configured is True
    assert repository.is_configured is False
    assert repository.status == "unavailable"
    assert repository.error_code == "connection_failed"
    assert "database unavailable" in repository.last_error


def test_migrations_are_safe_for_partial_bootstrap() -> None:
    first_migration = (
        "backend/migrations/versions/20260530_0001_create_workflow_tables.py"
    )
    second_migration = (
        "backend/migrations/versions/20260530_0002_ai_capability_tables.py"
    )
    third_migration = "backend/migrations/versions/20260531_0003_auth_tables.py"
    fourth_migration = (
        "backend/migrations/versions/20260531_0004_secure_sessions.py"
    )
    fifth_migration = (
        "backend/migrations/versions/20260609_0005_stride_remediation.py"
    )

    with open(first_migration, encoding="utf-8") as migration_file:
        first_source = migration_file.read()
    with open(second_migration, encoding="utf-8") as migration_file:
        second_source = migration_file.read()
    with open(third_migration, encoding="utf-8") as migration_file:
        third_source = migration_file.read()
    with open(fourth_migration, encoding="utf-8") as migration_file:
        fourth_source = migration_file.read()
    with open(fifth_migration, encoding="utf-8") as migration_file:
        fifth_source = migration_file.read()

    assert "_table_exists" in first_source
    assert "CREATE INDEX IF NOT EXISTS" in first_source
    assert "_table_exists" in second_source
    assert "_add_column_if_missing" in second_source
    assert "CREATE INDEX IF NOT EXISTS" in second_source
    assert "_table_exists" in third_source
    assert "CREATE INDEX IF NOT EXISTS" in third_source
    assert "_column_exists" in fourth_source
    assert "_add_column_if_missing" in fourth_source
    assert "_foreign_key_exists" in fifth_source
    assert "owner_user_id" in fifth_source
    assert "security_audit_events" in fifth_source
    assert "rate_limit_counters" in fifth_source
    assert "CREATE INDEX IF NOT EXISTS" in fifth_source


def test_secure_session_columns_are_declared() -> None:
    auth_sessions = metadata.tables["auth_sessions"]

    assert "csrf_hash" in auth_sessions.c
    assert "last_seen_at" in auth_sessions.c
    assert "user_agent" in auth_sessions.c
    assert "ip_address" in auth_sessions.c


def test_stride_remediation_tables_and_columns_are_declared() -> None:
    workflow_runs = metadata.tables["workflow_runs"]
    memory_items = metadata.tables["memory_items"]
    run_evaluations = metadata.tables["run_evaluations"]

    assert "owner_user_id" in workflow_runs.c
    assert "owner_user_id" in memory_items.c
    assert run_evaluations.c.run_id.foreign_keys
    assert "user_agent_profiles" in metadata.tables
    assert "security_audit_events" in metadata.tables
    assert "rate_limit_counters" in metadata.tables


def test_docker_entrypoint_runs_migrations_before_api_start() -> None:
    dockerfile = Path("backend/Dockerfile").read_text(encoding="utf-8")
    entrypoint = Path("backend/docker-entrypoint.sh").read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["./docker-entrypoint.sh"]' in dockerfile
    assert "--start-period=300s" in dockerfile
    assert "python -m app.migration_runner" in entrypoint
    assert "export DATABASE_AUTO_MIGRATE=false" in entrypoint


def test_migration_env_uses_locking_and_timeouts() -> None:
    migration_env = Path("backend/migrations/env.py").read_text(encoding="utf-8")

    assert "pg_try_advisory_lock" in migration_env
    assert "pg_advisory_unlock" in migration_env
    assert "SET lock_timeout" in migration_env
    assert "SET statement_timeout" in migration_env
