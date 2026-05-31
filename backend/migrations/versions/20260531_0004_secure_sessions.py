"""harden auth sessions with csrf metadata

Revision ID: 20260531_0004
Revises: 20260531_0003
Create Date: 2026-05-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260531_0004"
down_revision: str | None = "20260531_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return column_name in {column["name"] for column in columns}


def _add_column_if_missing(table_name: str, column: sa.Column[str]) -> None:
    if not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    if not _table_exists("auth_sessions"):
        return

    _add_column_if_missing(
        "auth_sessions",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "auth_sessions",
        sa.Column("csrf_hash", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "auth_sessions",
        sa.Column("user_agent", sa.String(length=256), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "auth_sessions",
        sa.Column("ip_address", sa.String(length=64), nullable=False, server_default=""),
    )

    op.execute(
        "UPDATE auth_sessions SET last_seen_at = created_at "
        "WHERE last_seen_at IS NULL"
    )
    op.execute(
        "UPDATE auth_sessions SET csrf_hash = token_hash "
        "WHERE csrf_hash IS NULL"
    )
    op.alter_column("auth_sessions", "last_seen_at", nullable=False)
    op.alter_column("auth_sessions", "csrf_hash", nullable=False)


def downgrade() -> None:
    if not _table_exists("auth_sessions"):
        return
    for column_name in ("ip_address", "user_agent", "csrf_hash", "last_seen_at"):
        if _column_exists("auth_sessions", column_name):
            op.drop_column("auth_sessions", column_name)
