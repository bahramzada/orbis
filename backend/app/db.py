from datetime import UTC, datetime
import ssl
from typing import TypeAlias
from uuid import UUID

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings
from app.metrics import timer
from app.schemas import WorkflowRun, WorkflowRunSummary

SslConfig: TypeAlias = bool | ssl.SSLContext


metadata = MetaData()

workflow_runs = Table(
    "workflow_runs",
    metadata,
    Column("run_id", PostgresUUID(as_uuid=True), primary_key=True),
    Column("task", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("plan", JSONB, nullable=False),
    Column("worker_results", JSONB, nullable=False),
    Column("final_answer", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
)

workflow_logs = Table(
    "workflow_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "run_id",
        PostgresUUID(as_uuid=True),
        ForeignKey("workflow_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("agent_id", String(64), nullable=False),
    Column("agent_name", String(120), nullable=False),
    Column("status", String(32), nullable=False),
    Column("message", Text, nullable=False),
)

Index("ix_workflow_runs_completed_at_desc", workflow_runs.c.completed_at.desc())
Index(
    "ix_workflow_runs_status_completed_at_desc",
    workflow_runs.c.status,
    workflow_runs.c.completed_at.desc(),
)
Index(
    "ix_workflow_logs_run_id_created_at",
    workflow_logs.c.run_id,
    workflow_logs.c.created_at.asc(),
)


class DatabaseRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        if settings.is_database_configured:
            self._engine = create_async_engine(
                settings.sqlalchemy_database_url,
                pool_pre_ping=True,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_timeout=settings.database_pool_timeout_seconds,
                connect_args={
                    "timeout": settings.database_connect_timeout_seconds,
                    "ssl": _ssl_config(settings.database_ssl),
                },
            )

    @property
    def is_configured(self) -> bool:
        return self._engine is not None

    async def init(self) -> None:
        if self._engine is None:
            return
        if not self._settings.database_auto_create_tables:
            return

        async with self._engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    async def save_workflow_run(self, run: WorkflowRun) -> None:
        if self._engine is None:
            return

        db_timer = timer("orbis_db_operation_duration_seconds", {"operation": "save_run"})
        try:
            created_at = _parse_datetime(run.logs[0].created_at) if run.logs else _now()
            completed_at = _parse_datetime(run.logs[-1].created_at) if run.logs else _now()

            async with self._engine.begin() as connection:
                await connection.execute(
                    insert(workflow_runs).values(
                        run_id=UUID(run.run_id),
                        task=run.task,
                        model=run.model,
                        status=run.status,
                        plan=[item.model_dump(mode="json") for item in run.plan],
                        worker_results=[
                            result.model_dump(mode="json")
                            for result in run.worker_results
                        ],
                        final_answer=run.final_answer,
                        created_at=created_at,
                        completed_at=completed_at,
                    )
                )
                if run.logs:
                    await connection.execute(
                        insert(workflow_logs),
                        [
                            {
                                "run_id": UUID(log.run_id),
                                "created_at": _parse_datetime(log.created_at),
                                "agent_id": log.agent_id,
                                "agent_name": log.agent_name,
                                "status": log.status,
                                "message": log.message,
                            }
                            for log in run.logs
                        ],
                    )
        finally:
            db_timer.stop()

    async def list_workflow_runs(self, limit: int = 20) -> list[WorkflowRunSummary]:
        if self._engine is None:
            return []

        db_timer = timer("orbis_db_operation_duration_seconds", {"operation": "list_runs"})
        try:
            statement = (
                select(
                    workflow_runs.c.run_id,
                    workflow_runs.c.task,
                    workflow_runs.c.model,
                    workflow_runs.c.status,
                    workflow_runs.c.created_at,
                    workflow_runs.c.completed_at,
                )
                .order_by(workflow_runs.c.completed_at.desc())
                .limit(limit)
            )

            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        finally:
            db_timer.stop()

        return [
            WorkflowRunSummary(
                run_id=str(row["run_id"]),
                task=row["task"],
                model=row["model"],
                status=row["status"],
                created_at=row["created_at"].isoformat(),
                completed_at=row["completed_at"].isoformat(),
            )
            for row in rows
        ]


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _ssl_config(value: str) -> SslConfig:
    normalized = value.strip().lower()
    if normalized in {"0", "false", "no", "off", "disable"}:
        return False
    if normalized in {"verify", "verify-ca", "verify-full", "strict"}:
        return ssl.create_default_context()

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context
