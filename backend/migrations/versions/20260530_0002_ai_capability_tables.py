"""add ai capability tables

Revision ID: 20260530_0002
Revises: 20260530_0001
Create Date: 2026-05-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260530_0002"
down_revision: str | None = "20260530_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "workflow_runs",
        sa.Column(
            "output_format",
            sa.String(length=32),
            nullable=False,
            server_default="markdown",
        ),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("estimated_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workflow_runs",
        sa.Column(
            "estimated_cost_usd",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "agent_profiles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.Text(), nullable=False, server_default=""),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="900"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("task_prompt", sa.Text(), nullable=False),
        sa.Column(
            "output_format",
            sa.String(length=32),
            nullable=False,
            server_default="markdown",
        ),
    )
    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "run_evaluations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rubric", sa.Text(), nullable=False),
        sa.Column("completeness", sa.Integer(), nullable=False),
        sa.Column("actionability", sa.Integer(), nullable=False),
        sa.Column("hallucination_risk", sa.Integer(), nullable=False),
        sa.Column("overall", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_memory_items_enabled_created",
        "memory_items",
        ["enabled", "created_at"],
    )
    op.create_index(
        "ix_tool_calls_run_id_created",
        "tool_calls",
        ["run_id", "created_at"],
    )
    op.create_index(
        "ix_run_evaluations_run_id_created",
        "run_evaluations",
        ["run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_evaluations_run_id_created", table_name="run_evaluations")
    op.drop_index("ix_tool_calls_run_id_created", table_name="tool_calls")
    op.drop_index("ix_memory_items_enabled_created", table_name="memory_items")
    op.drop_table("run_evaluations")
    op.drop_table("tool_calls")
    op.drop_table("memory_items")
    op.drop_table("workflow_templates")
    op.drop_table("agent_profiles")
    op.drop_column("workflow_runs", "estimated_cost_usd")
    op.drop_column("workflow_runs", "estimated_tokens")
    op.drop_column("workflow_runs", "duration_ms")
    op.drop_column("workflow_runs", "output_format")
    op.drop_column("workflow_runs", "tool_calls")
