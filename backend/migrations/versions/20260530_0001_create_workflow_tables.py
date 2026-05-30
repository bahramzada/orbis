"""create workflow tables

Revision ID: 20260530_0001
Revises:
Create Date: 2026-05-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260530_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if not _table_exists("workflow_runs"):
        op.create_table(
            "workflow_runs",
            sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("task", sa.Text(), nullable=False),
            sa.Column("model", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column(
                "worker_results",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("final_answer", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not _table_exists("workflow_logs"):
        op.create_table(
            "workflow_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "run_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("workflow_runs.run_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("agent_id", sa.String(length=64), nullable=False),
            sa.Column("agent_name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_completed_at_desc "
        "ON workflow_runs (completed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_status_completed_at_desc "
        "ON workflow_runs (status, completed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_logs_run_id_created_at "
        "ON workflow_logs (run_id, created_at)"
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_logs_run_id_created_at", table_name="workflow_logs")
    op.drop_index(
        "ix_workflow_runs_status_completed_at_desc",
        table_name="workflow_runs",
    )
    op.drop_index("ix_workflow_runs_completed_at_desc", table_name="workflow_runs")
    op.drop_table("workflow_logs")
    op.drop_table("workflow_runs")
