"""add auth and admin settings tables

Revision ID: 20260531_0003
Revises: 20260530_0002
Create Date: 2026-05-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260531_0003"
down_revision: str | None = "20260530_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("email", sa.String(length=320), nullable=False, unique=True),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False, server_default="guest"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("auth_sessions"):
        op.create_table(
            "auth_sessions",
            sa.Column("token_hash", sa.String(length=64), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(length=64),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("system_settings"):
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(length=80), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_role_created "
        "ON users (role, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_expires "
        "ON auth_sessions (user_id, expires_at)"
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_user_expires", table_name="auth_sessions")
    op.drop_index("ix_users_role_created", table_name="users")
    op.drop_table("system_settings")
    op.drop_table("auth_sessions")
    op.drop_table("users")
