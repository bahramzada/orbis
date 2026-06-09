"""add stride remediation ownership and audit controls

Revision ID: 20260609_0005
Revises: 20260531_0004
Create Date: 2026-06-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260609_0005"
down_revision: str | None = "20260531_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return column_name in {column["name"] for column in columns}


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    keys = sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    return constraint_name in {key["name"] for key in keys}


def _add_column_if_missing(table_name: str, column: sa.Column[object]) -> None:
    if _table_exists(table_name) and not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def _create_fk_if_missing(
    table_name: str,
    constraint_name: str,
    local_cols: list[str],
    remote_table: str,
    remote_cols: list[str],
    *,
    ondelete: str | None = None,
) -> None:
    if _table_exists(table_name) and not _foreign_key_exists(table_name, constraint_name):
        op.create_foreign_key(
            constraint_name,
            table_name,
            remote_table,
            local_cols,
            remote_cols,
            ondelete=ondelete,
        )


def upgrade() -> None:
    _add_column_if_missing(
        "workflow_runs",
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "memory_items",
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
    )

    _create_fk_if_missing(
        "workflow_runs",
        "fk_workflow_runs_owner_user_id_users",
        ["owner_user_id"],
        "users",
        ["id"],
    )
    _create_fk_if_missing(
        "memory_items",
        "fk_memory_items_owner_user_id_users",
        ["owner_user_id"],
        "users",
        ["id"],
    )
    _create_fk_if_missing(
        "run_evaluations",
        "fk_run_evaluations_run_id_workflow_runs",
        ["run_id"],
        "workflow_runs",
        ["run_id"],
        ondelete="CASCADE",
    )

    if not _table_exists("user_agent_profiles"):
        op.create_table(
            "user_agent_profiles",
            sa.Column(
                "owner_user_id",
                sa.String(length=64),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("role", sa.String(length=120), nullable=False),
            sa.Column("goal", sa.Text(), nullable=False),
            sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
            sa.Column("model", sa.Text(), nullable=False, server_default=""),
            sa.Column("temperature", sa.Float(), nullable=False, server_default="0.3"),
            sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="900"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("security_audit_events"):
        op.create_table(
            "security_audit_events",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("actor_user_id", sa.String(length=64), nullable=True),
            sa.Column(
                "actor_email",
                sa.String(length=320),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "actor_role",
                sa.String(length=32),
                nullable=False,
                server_default="",
            ),
            sa.Column("action", sa.String(length=120), nullable=False),
            sa.Column(
                "resource_type",
                sa.String(length=80),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "resource_id",
                sa.String(length=120),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "ip_address",
                sa.String(length=64),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "user_agent",
                sa.String(length=256),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "detail",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("rate_limit_counters"):
        op.create_table(
            "rate_limit_counters",
            sa.Column("key", sa.String(length=240), primary_key=True),
            sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_owner_completed "
        "ON workflow_runs (owner_user_id, completed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memory_items_owner_enabled_created "
        "ON memory_items (owner_user_id, enabled, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_security_audit_events_created "
        "ON security_audit_events (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_security_audit_events_actor_created "
        "ON security_audit_events (actor_user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rate_limit_counters_expires "
        "ON rate_limit_counters (expires_at)"
    )


def downgrade() -> None:
    for index_name, table_name in (
        ("ix_rate_limit_counters_expires", "rate_limit_counters"),
        ("ix_security_audit_events_actor_created", "security_audit_events"),
        ("ix_security_audit_events_created", "security_audit_events"),
        ("ix_memory_items_owner_enabled_created", "memory_items"),
        ("ix_workflow_runs_owner_completed", "workflow_runs"),
    ):
        if _table_exists(table_name):
            op.execute(f"DROP INDEX IF EXISTS {index_name}")

    for table_name in (
        "rate_limit_counters",
        "security_audit_events",
        "user_agent_profiles",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)

    for table_name, constraint_name in (
        ("run_evaluations", "fk_run_evaluations_run_id_workflow_runs"),
        ("memory_items", "fk_memory_items_owner_user_id_users"),
        ("workflow_runs", "fk_workflow_runs_owner_user_id_users"),
    ):
        if _foreign_key_exists(table_name, constraint_name):
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")

    for table_name, column_name in (
        ("memory_items", "owner_user_id"),
        ("workflow_runs", "owner_user_id"),
    ):
        if _column_exists(table_name, column_name):
            op.drop_column(table_name, column_name)
