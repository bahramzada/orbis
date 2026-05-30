import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import Settings


def _alembic_config(settings: Settings) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.attributes["settings"] = settings
    return config


def _upgrade_to_head(settings: Settings) -> None:
    command.upgrade(_alembic_config(settings), "head")


async def run_database_migrations(settings: Settings) -> None:
    await asyncio.to_thread(_upgrade_to_head, settings)
