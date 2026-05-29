from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
        default="http://localhost:5173",
        alias="FRONTEND_ORIGIN",
    )
    frontend_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="FRONTEND_ORIGINS",
    )
    request_timeout_seconds: float = Field(default=45.0, alias="REQUEST_TIMEOUT_SECONDS")
    database_url: str = Field(default="", alias="DATABASE_URL")
    database_connect_timeout_seconds: float = Field(
        default=10.0,
        alias="DATABASE_CONNECT_TIMEOUT_SECONDS",
    )
    database_ssl: str = Field(default="require", alias="DATABASE_SSL")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
