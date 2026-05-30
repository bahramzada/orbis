import asyncio
import ssl
from typing import cast

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from app import migration_runner
from app.config import Settings
from app.db import DatabaseRepository, _ssl_config, metadata


def test_database_url_is_optional() -> None:
    settings = Settings(DATABASE_URL="")
    repository = DatabaseRepository(settings)

    assert settings.is_database_configured is False
    assert repository.is_persistence_configured is False
    assert repository.is_configured is False


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
    assert "database unavailable" in repository.last_error
