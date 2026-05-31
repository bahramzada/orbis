import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import Settings, get_settings


logger = logging.getLogger(__name__)


def _alembic_config(settings: Settings) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.attributes["settings"] = settings
    return config


def _upgrade_to_head(settings: Settings) -> None:
    command.upgrade(_alembic_config(settings), "head")


async def run_database_migrations(settings: Settings) -> None:
    await asyncio.to_thread(_upgrade_to_head, settings)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    if not settings.is_database_configured:
        raise SystemExit("DATABASE_URL is required before running migrations.")

    logger.info("Applying database migrations.")
    asyncio.run(run_database_migrations(settings))
    logger.info("Database migrations are up to date.")


if __name__ == "__main__":
    main()
