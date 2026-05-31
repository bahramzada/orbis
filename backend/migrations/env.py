from asyncio import run, sleep
from logging.config import fileConfig
from time import monotonic

from alembic import context
import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.config import Settings, get_settings
from app.db import _ssl_config, metadata


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _active_settings() -> Settings:
    configured_settings = config.attributes.get("settings")
    if isinstance(configured_settings, Settings):
        return configured_settings
    return get_settings()


def run_migrations_offline() -> None:
    settings = _active_settings()
    context.configure(
        url=settings.sqlalchemy_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _apply_statement_timeouts(connection, _active_settings())
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def _apply_statement_timeouts(connection: Connection, settings: Settings) -> None:
    lock_timeout_ms = max(1, settings.database_migration_lock_timeout_seconds) * 1000
    statement_timeout_ms = (
        max(1, settings.database_migration_statement_timeout_seconds) * 1000
    )
    connection.execute(sa.text(f"SET lock_timeout TO '{lock_timeout_ms}ms'"))
    connection.execute(sa.text(f"SET statement_timeout TO '{statement_timeout_ms}ms'"))


async def _acquire_migration_lock(
    connection: AsyncConnection,
    settings: Settings,
) -> bool:
    deadline = monotonic() + max(1, settings.database_migration_lock_timeout_seconds)
    while True:
        result = await connection.execute(
            sa.text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": settings.database_migration_lock_id},
        )
        if bool(result.scalar_one()):
            return True
        if monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for the database migration lock.")
        await sleep(1)


async def run_migrations_online() -> None:
    settings = _active_settings()
    connectable = create_async_engine(
        settings.sqlalchemy_database_url,
        poolclass=pool.NullPool,
        connect_args={
            "timeout": settings.database_connect_timeout_seconds,
            "ssl": _ssl_config(settings.database_ssl),
        },
    )

    async with connectable.connect() as connection:
        locked = await _acquire_migration_lock(connection, settings)
        try:
            await connection.run_sync(do_run_migrations)
        finally:
            if locked:
                await connection.execute(
                    sa.text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": settings.database_migration_lock_id},
                )

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run(run_migrations_online())
