from app.config import Settings
from app.db import DatabaseRepository, _ssl_config


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
