from app.config import Settings
from app.db import DatabaseRepository, _ssl_config, metadata


def test_database_url_is_optional() -> None:
    settings = Settings(DATABASE_URL="")
    repository = DatabaseRepository(settings)

    assert settings.is_database_configured is False
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


def test_database_ssl_setting_is_mapped_to_asyncpg_bool() -> None:
    assert _ssl_config("require") is not False
    assert _ssl_config("true") is not False
    assert _ssl_config("disable") is False


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
    )

    repository = DatabaseRepository(settings)

    assert repository.is_configured is True


def test_runtime_performance_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.workflow_max_concurrency >= 1
    assert settings.workflow_step_timeout_seconds > 0
    assert settings.openrouter_max_connections >= settings.openrouter_max_keepalive
    assert settings.openrouter_retry_attempts >= 1
    assert settings.database_pool_size >= 1
