from functools import lru_cache
from typing import Literal, cast

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_ORIGIN_MARKERS = ("localhost", "127.0.0.1")


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    orbis_api_token: str = Field(default="", alias="ORBIS_API_TOKEN")
    metrics_api_token: str = Field(default="", alias="METRICS_API_TOKEN")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="openai/gpt-4.1-mini",
        alias="OPENROUTER_MODEL",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_site_url: str = Field(
        default="http://localhost:5173",
        alias="OPENROUTER_SITE_URL",
    )
    openrouter_app_name: str = Field(default="Orbis", alias="OPENROUTER_APP_NAME")
    frontend_origin: str = Field(
        default="",
        alias="FRONTEND_ORIGIN",
    )
    frontend_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="FRONTEND_ORIGINS",
    )
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")
    request_timeout_seconds: float = Field(default=45.0, alias="REQUEST_TIMEOUT_SECONDS")
    workflow_max_concurrency: int = Field(default=2, alias="WORKFLOW_MAX_CONCURRENCY")
    workflow_step_timeout_seconds: float = Field(
        default=90.0,
        alias="WORKFLOW_STEP_TIMEOUT_SECONDS",
    )
    workflow_cache_ttl_seconds: float = Field(
        default=0.0,
        alias="WORKFLOW_CACHE_TTL_SECONDS",
    )
    openrouter_max_connections: int = Field(
        default=20,
        alias="OPENROUTER_MAX_CONNECTIONS",
    )
    openrouter_max_keepalive: int = Field(
        default=10,
        alias="OPENROUTER_MAX_KEEPALIVE",
    )
    openrouter_retry_attempts: int = Field(
        default=3,
        alias="OPENROUTER_RETRY_ATTEMPTS",
    )
    openrouter_retry_base_seconds: float = Field(
        default=0.4,
        alias="OPENROUTER_RETRY_BASE_SECONDS",
    )
    database_url: str = Field(default="", alias="DATABASE_URL")
    database_required: bool = Field(default=True, alias="DATABASE_REQUIRED")
    database_connect_timeout_seconds: float = Field(
        default=10.0,
        alias="DATABASE_CONNECT_TIMEOUT_SECONDS",
    )
    database_ssl: str = Field(default="require", alias="DATABASE_SSL")
    database_pool_size: int = Field(default=3, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=2, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout_seconds: float = Field(
        default=10.0,
        alias="DATABASE_POOL_TIMEOUT_SECONDS",
    )
    database_auto_create_tables: bool = Field(
        default=False,
        alias="DATABASE_AUTO_CREATE_TABLES",
    )
    database_auto_migrate: bool = Field(
        default=True,
        alias="DATABASE_AUTO_MIGRATE",
    )
    database_migration_lock_id: int = Field(
        default=739_421_317,
        alias="DATABASE_MIGRATION_LOCK_ID",
    )
    database_migration_lock_timeout_seconds: int = Field(
        default=30,
        alias="DATABASE_MIGRATION_LOCK_TIMEOUT_SECONDS",
    )
    database_migration_statement_timeout_seconds: int = Field(
        default=240,
        alias="DATABASE_MIGRATION_STATEMENT_TIMEOUT_SECONDS",
    )
    max_recent_runs: int = Field(default=100, alias="MAX_RECENT_RUNS")
    max_evaluations_per_run: int = Field(
        default=20,
        alias="MAX_EVALUATIONS_PER_RUN",
    )
    enable_metrics: bool = Field(default=True, alias="ENABLE_METRICS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    otel_exporter_otlp_endpoint: str = Field(
        default="",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    auth_session_ttl_hours: int = Field(default=720, alias="AUTH_SESSION_TTL_HOURS")
    auth_session_cleanup_interval_seconds: int = Field(
        default=900,
        alias="AUTH_SESSION_CLEANUP_INTERVAL_SECONDS",
    )
    auth_session_touch_interval_seconds: int = Field(
        default=300,
        alias="AUTH_SESSION_TOUCH_INTERVAL_SECONDS",
    )
    auth_rate_limit_max_attempts: int = Field(
        default=5,
        alias="AUTH_RATE_LIMIT_MAX_ATTEMPTS",
    )
    auth_rate_limit_window_seconds: int = Field(
        default=900,
        alias="AUTH_RATE_LIMIT_WINDOW_SECONDS",
    )
    session_cookie_name: str = Field(
        default="orbis_session",
        alias="SESSION_COOKIE_NAME",
    )
    session_cookie_secure: bool = Field(
        default=False,
        alias="SESSION_COOKIE_SECURE",
    )
    session_cookie_samesite: str = Field(
        default="lax",
        alias="SESSION_COOKIE_SAMESITE",
    )
    session_cookie_domain: str = Field(default="", alias="SESSION_COOKIE_DOMAIN")
    system_settings_cache_ttl_seconds: int = Field(
        default=30,
        alias="SYSTEM_SETTINGS_CACHE_TTL_SECONDS",
    )

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def is_openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key.strip())

    @property
    def is_database_configured(self) -> bool:
        value = self.database_url.strip()
        return bool(value) and "[YOUR-PASSWORD]" not in value

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def sqlalchemy_database_url(self) -> str:
        value = self.database_url.strip()
        if value.startswith("postgresql+asyncpg://"):
            return value
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.frontend_origins.split(",")]
        legacy_origin = self.frontend_origin.strip()
        if legacy_origin:
            origins.append(legacy_origin)
        return sorted({origin for origin in origins if origin})

    @property
    def effective_metrics_token(self) -> str:
        return self.metrics_api_token.strip() or self.orbis_api_token.strip()

    @property
    def normalized_session_cookie_samesite(self) -> Literal["lax", "strict", "none"]:
        value = self.session_cookie_samesite.strip().lower()
        if value in {"lax", "strict", "none"}:
            return cast(Literal["lax", "strict", "none"], value)
        return "lax"

    def validate_security_settings(self) -> None:
        if self.session_cookie_samesite.strip().lower() not in {"lax", "strict", "none"}:
            raise RuntimeError("SESSION_COOKIE_SAMESITE must be lax, strict, or none.")
        if (
            self.session_cookie_samesite.strip().lower() == "none"
            and not self.session_cookie_secure
        ):
            raise RuntimeError("SESSION_COOKIE_SAMESITE=none requires Secure cookies.")
        if not self.is_production:
            return
        if not self.orbis_api_token.strip():
            raise RuntimeError("ORBIS_API_TOKEN is required in production.")
        if not self.database_required:
            raise RuntimeError("DATABASE_REQUIRED must be true in production.")
        if self.database_auto_create_tables:
            raise RuntimeError("DATABASE_AUTO_CREATE_TABLES must be false in production.")
        if self.database_ssl.strip().lower() in {
            "0",
            "false",
            "no",
            "off",
            "disable",
            "disabled",
        }:
            raise RuntimeError("Encrypted DATABASE_SSL is required in production.")
        if not self.session_cookie_secure:
            raise RuntimeError("SESSION_COOKIE_SECURE must be true in production.")
        if not self.cors_allow_credentials:
            raise RuntimeError("CORS_ALLOW_CREDENTIALS must be true for cookie auth.")
        if any(
            marker in origin
            for origin in self.cors_origins
            for marker in LOCAL_ORIGIN_MARKERS
        ):
            raise RuntimeError("Production FRONTEND_ORIGINS must not include local origins.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
