from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from collections.abc import Mapping
import ssl
from typing import TypeAlias, cast
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    inspect,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import (
    JSONB,
    UUID as PostgresUUID,
    insert as pg_insert,
)
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings
from app.metrics import timer
from app.security import redact_sensitive_text
from app.schemas import (
    AuditEvent,
    AdminUser,
    AgentProfile,
    AuthUser,
    EvaluationResult,
    MemoryCreateRequest,
    MemoryItem,
    RunDetail,
    SystemSettings,
    UserRole,
    WorkerResult,
    WorkflowLog,
    WorkflowRun,
    WorkflowRunSummary,
    WorkflowTemplate,
)

SslConfig: TypeAlias = bool | ssl.SSLContext
logger = logging.getLogger(__name__)
SCHEMA_INCOMPLETE_ERROR = "schema_incomplete"

REQUIRED_TABLE_NAMES = frozenset(
    {
        "workflow_runs",
        "workflow_logs",
        "agent_profiles",
        "user_agent_profiles",
        "workflow_templates",
        "memory_items",
        "tool_calls",
        "run_evaluations",
        "security_audit_events",
        "rate_limit_counters",
        "users",
        "auth_sessions",
        "system_settings",
        "alembic_version",
    }
)
REQUIRED_TABLE_COLUMNS = {
    "auth_sessions": frozenset(
        {"csrf_hash", "last_seen_at", "user_agent", "ip_address"}
    ),
    "workflow_runs": frozenset({"owner_user_id"}),
    "memory_items": frozenset({"owner_user_id"}),
}


class DatabaseSchemaError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionAuthRecord:
    user: AuthUser
    csrf_hash: str


metadata = MetaData()

workflow_runs = Table(
    "workflow_runs",
    metadata,
    Column("run_id", PostgresUUID(as_uuid=True), primary_key=True),
    Column("owner_user_id", String(64), ForeignKey("users.id"), nullable=True),
    Column("task", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("plan", JSONB, nullable=False),
    Column("worker_results", JSONB, nullable=False),
    Column("final_answer", Text, nullable=False),
    Column("tool_calls", JSONB, nullable=False, default=list),
    Column("output_format", String(32), nullable=False, default="markdown"),
    Column("duration_ms", Integer, nullable=False, default=0),
    Column("estimated_tokens", Integer, nullable=False, default=0),
    Column("estimated_cost_usd", Float, nullable=False, default=0),
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

agent_profiles = Table(
    "agent_profiles",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("role", String(120), nullable=False),
    Column("goal", Text, nullable=False),
    Column("system_prompt", Text, nullable=False, default=""),
    Column("model", Text, nullable=False, default=""),
    Column("temperature", Float, nullable=False, default=0.3),
    Column("max_tokens", Integer, nullable=False, default=900),
    Column("enabled", Boolean, nullable=False, default=True),
)

user_agent_profiles = Table(
    "user_agent_profiles",
    metadata,
    Column(
        "owner_user_id",
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("id", String(64), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("role", String(120), nullable=False),
    Column("goal", Text, nullable=False),
    Column("system_prompt", Text, nullable=False, default=""),
    Column("model", Text, nullable=False, default=""),
    Column("temperature", Float, nullable=False, default=0.3),
    Column("max_tokens", Integer, nullable=False, default=900),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

workflow_templates = Table(
    "workflow_templates",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(160), nullable=False),
    Column("description", Text, nullable=False),
    Column("task_prompt", Text, nullable=False),
    Column("output_format", String(32), nullable=False, default="markdown"),
)

memory_items = Table(
    "memory_items",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_user_id", String(64), ForeignKey("users.id"), nullable=True),
    Column("title", String(120), nullable=False),
    Column("category", String(64), nullable=False),
    Column("content", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

tool_calls = Table(
    "tool_calls",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("run_id", PostgresUUID(as_uuid=True), nullable=False),
    Column("tool_name", String(80), nullable=False),
    Column("status", String(32), nullable=False),
    Column("input", Text, nullable=False),
    Column("output", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

run_evaluations = Table(
    "run_evaluations",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "run_id",
        PostgresUUID(as_uuid=True),
        ForeignKey("workflow_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("rubric", Text, nullable=False),
    Column("completeness", Integer, nullable=False),
    Column("actionability", Integer, nullable=False),
    Column("hallucination_risk", Integer, nullable=False),
    Column("overall", Integer, nullable=False),
    Column("notes", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

users = Table(
    "users",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("display_name", String(120), nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("role", String(16), nullable=False, default="guest"),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column(
        "user_id",
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("csrf_hash", String(64), nullable=False),
    Column("user_agent", String(256), nullable=False, default=""),
    Column("ip_address", String(64), nullable=False, default=""),
)

system_settings = Table(
    "system_settings",
    metadata,
    Column("key", String(80), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

security_audit_events = Table(
    "security_audit_events",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("actor_user_id", String(64), nullable=True),
    Column("actor_email", String(320), nullable=False, default=""),
    Column("actor_role", String(32), nullable=False, default=""),
    Column("action", String(120), nullable=False),
    Column("resource_type", String(80), nullable=False, default=""),
    Column("resource_id", String(120), nullable=False, default=""),
    Column("ip_address", String(64), nullable=False, default=""),
    Column("user_agent", String(256), nullable=False, default=""),
    Column("detail", JSONB, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

rate_limit_counters = Table(
    "rate_limit_counters",
    metadata,
    Column("key", String(240), primary_key=True),
    Column("window_start", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("count", Integer, nullable=False, default=0),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

Index(
    "ix_workflow_runs_owner_completed",
    workflow_runs.c.owner_user_id,
    workflow_runs.c.completed_at.desc(),
)
Index(
    "ix_memory_items_enabled_created",
    memory_items.c.enabled,
    memory_items.c.created_at,
)
Index(
    "ix_memory_items_owner_enabled_created",
    memory_items.c.owner_user_id,
    memory_items.c.enabled,
    memory_items.c.created_at.desc(),
)
Index("ix_tool_calls_run_id_created", tool_calls.c.run_id, tool_calls.c.created_at)
Index("ix_run_evaluations_run_id_created", run_evaluations.c.run_id, run_evaluations.c.created_at)
Index("ix_users_role_created", users.c.role, users.c.created_at.desc())
Index("ix_auth_sessions_user_expires", auth_sessions.c.user_id, auth_sessions.c.expires_at)
Index("ix_security_audit_events_created", security_audit_events.c.created_at.desc())
Index(
    "ix_security_audit_events_actor_created",
    security_audit_events.c.actor_user_id,
    security_audit_events.c.created_at.desc(),
)
Index("ix_rate_limit_counters_expires", rate_limit_counters.c.expires_at)


class DatabaseRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._last_error = ""
        self._last_error_code = ""
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

    @property
    def is_persistence_configured(self) -> bool:
        return self._settings.is_database_configured

    @property
    def status(self) -> str:
        if not self._settings.is_database_configured:
            return "disabled"
        if self._engine is None:
            return "unavailable"
        return "ready"

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def error_code(self) -> str:
        return self._last_error_code

    async def init(self) -> None:
        if self._engine is None:
            return

        try:
            if self._settings.database_auto_create_tables:
                async with self._engine.begin() as connection:
                    await connection.run_sync(metadata.create_all)
            await self._verify_schema()
        except Exception as exc:
            self._disable_after_error("init", exc)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    async def get_system_settings(self) -> SystemSettings:
        if self._engine is None:
            return SystemSettings()

        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(select(system_settings))
                values = {row["key"]: row["value"] for row in result.mappings()}
            return SystemSettings(
                system_enabled=_text_to_bool(values.get("system_enabled"), True),
                register_enabled=_text_to_bool(values.get("register_enabled"), True),
            )
        except Exception as exc:
            self._disable_after_error("get_system_settings", exc)
            return SystemSettings()

    async def save_system_settings(self, settings: SystemSettings) -> SystemSettings:
        if self._engine is None:
            return settings

        now = _now()
        values = {
            "system_enabled": _bool_to_text(settings.system_enabled),
            "register_enabled": _bool_to_text(settings.register_enabled),
        }
        try:
            async with self._engine.begin() as connection:
                for key, value in values.items():
                    await connection.execute(
                        delete(system_settings).where(system_settings.c.key == key)
                    )
                    await connection.execute(
                        insert(system_settings).values(
                            key=key,
                            value=value,
                            updated_at=now,
                        )
                    )
            return settings
        except Exception as exc:
            self._disable_after_error("save_system_settings", exc)
            return settings

    async def create_user(
        self,
        user_id: str,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> AuthUser | None:
        if self._engine is None:
            return None

        now = _now()
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    insert(users).values(
                        id=user_id,
                        email=email,
                        display_name=display_name,
                        password_hash=password_hash,
                        role="guest",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
            return AuthUser(
                id=user_id,
                email=email,
                display_name=display_name,
                role="guest",
                created_at=now.isoformat(),
            )
        except Exception as exc:
            self._disable_after_error("create_user", exc)
            return None

    async def get_user_by_email(self, email: str) -> dict[str, object] | None:
        if self._engine is None:
            return None

        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    select(users).where(users.c.email == email)
                )
                row = result.mappings().first()
            return dict(row) if row is not None else None
        except Exception as exc:
            self._disable_after_error("get_user_by_email", exc)
            return None

    async def get_user_by_id(self, user_id: str) -> AuthUser | None:
        if self._engine is None:
            return None

        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    select(users).where(users.c.id == user_id)
                )
                row = result.mappings().first()
            return _row_to_auth_user(dict(row)) if row is not None else None
        except Exception as exc:
            self._disable_after_error("get_user_by_id", exc)
            return None

    async def list_users(self) -> list[AdminUser]:
        if self._engine is None:
            return []

        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    select(users).order_by(users.c.created_at.desc())
                )
                rows = result.mappings().all()
            return [_row_to_admin_user(dict(row)) for row in rows]
        except Exception as exc:
            self._disable_after_error("list_users", exc)
            return []

    async def update_user_role(
        self,
        user_id: str,
        role: UserRole,
        is_active: bool | None,
    ) -> AdminUser | None:
        if self._engine is None:
            return None

        values: dict[str, object] = {"role": role, "updated_at": _now()}
        if is_active is not None:
            values["is_active"] = is_active

        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    update(users)
                    .where(users.c.id == user_id)
                    .values(**values)
                    .returning(users)
                )
                row = result.mappings().first()
            return _row_to_admin_user(dict(row)) if row is not None else None
        except Exception as exc:
            self._disable_after_error("update_user_role", exc)
            return None

    async def update_password_hash(self, user_id: str, password_hash: str) -> None:
        if self._engine is None:
            return

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    update(users)
                    .where(users.c.id == user_id)
                    .values(password_hash=password_hash, updated_at=_now())
                )
        except Exception as exc:
            self._disable_after_error("update_password_hash", exc)

    async def create_session(
        self,
        token_hash: str,
        user_id: str,
        expires_at: datetime,
        csrf_hash: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> None:
        if self._engine is None:
            return

        now = _now()
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    insert(auth_sessions).values(
                        token_hash=token_hash,
                        user_id=user_id,
                        created_at=now,
                        last_seen_at=now,
                        expires_at=expires_at,
                        csrf_hash=csrf_hash,
                        user_agent=user_agent[:256],
                        ip_address=ip_address[:64],
                    )
                )
        except Exception as exc:
            self._disable_after_error("create_session", exc)

    async def get_user_by_session(self, token_hash: str) -> AuthUser | None:
        record = await self.get_session_auth(token_hash)
        return record.user if record is not None else None

    async def get_session_auth(
        self,
        token_hash: str,
        touch_interval_seconds: int = 300,
    ) -> SessionAuthRecord | None:
        if self._engine is None:
            return None

        now = _now()
        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    select(
                        users,
                        auth_sessions.c.csrf_hash,
                        auth_sessions.c.last_seen_at,
                    )
                    .select_from(
                        users.join(auth_sessions, users.c.id == auth_sessions.c.user_id)
                    )
                    .where(auth_sessions.c.token_hash == token_hash)
                    .where(auth_sessions.c.expires_at > now)
                    .where(users.c.is_active.is_(True))
                )
                row = result.mappings().first()
                if row is not None and _should_touch_session(
                    row["last_seen_at"],
                    now,
                    touch_interval_seconds,
                ):
                    await connection.execute(
                        update(auth_sessions)
                        .where(auth_sessions.c.token_hash == token_hash)
                        .values(last_seen_at=now)
                    )
            if row is None:
                return None
            row_dict = dict(row)
            return SessionAuthRecord(
                user=_row_to_auth_user(row_dict),
                csrf_hash=str(row_dict["csrf_hash"]),
            )
        except Exception as exc:
            self._disable_after_error("get_user_by_session", exc)
            return None

    async def rotate_session_csrf(self, token_hash: str, csrf_hash: str) -> None:
        if self._engine is None:
            return

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    update(auth_sessions)
                    .where(auth_sessions.c.token_hash == token_hash)
                    .values(csrf_hash=csrf_hash, last_seen_at=_now())
                )
        except Exception as exc:
            self._disable_after_error("rotate_session_csrf", exc)

    async def delete_expired_sessions(self) -> None:
        if self._engine is None:
            return

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    delete(auth_sessions).where(auth_sessions.c.expires_at <= _now())
                )
        except Exception as exc:
            self._disable_after_error("delete_expired_sessions", exc)

    async def delete_session(self, token_hash: str) -> None:
        if self._engine is None:
            return

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    delete(auth_sessions).where(auth_sessions.c.token_hash == token_hash)
                )
        except Exception as exc:
            self._disable_after_error("delete_session", exc)

    async def save_workflow_run(self, run: WorkflowRun, owner_user_id: str) -> None:
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
                        owner_user_id=owner_user_id,
                        task=run.task,
                        model=run.model,
                        status=run.status,
                        plan=[item.model_dump(mode="json") for item in run.plan],
                        worker_results=[
                            result.model_dump(mode="json")
                            for result in run.worker_results
                        ],
                        final_answer=run.final_answer,
                        tool_calls=[
                            tool_call.model_dump(mode="json")
                            for tool_call in run.tool_calls
                        ],
                        output_format=run.output_format,
                        duration_ms=run.duration_ms,
                        estimated_tokens=run.estimated_tokens,
                        estimated_cost_usd=run.estimated_cost_usd,
                        created_at=created_at,
                        completed_at=completed_at,
                    )
                )
                if run.tool_calls:
                    await connection.execute(
                        insert(tool_calls),
                        [
                            {
                                "id": tool_call.id,
                                "run_id": UUID(tool_call.run_id),
                                "tool_name": tool_call.tool_name,
                                "status": tool_call.status,
                                "input": tool_call.input,
                                "output": tool_call.output,
                                "created_at": _parse_datetime(tool_call.created_at),
                            }
                            for tool_call in run.tool_calls
                        ],
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
        except Exception as exc:
            self._disable_after_error("save_run", exc)
        finally:
            db_timer.stop()

    async def list_workflow_runs(
        self,
        limit: int = 20,
        *,
        owner_user_id: str | None = None,
        include_all: bool = False,
    ) -> list[WorkflowRunSummary]:
        if self._engine is None:
            return []

        db_timer = timer("orbis_db_operation_duration_seconds", {"operation": "list_runs"})
        try:
            statement = (
                select(
                    workflow_runs.c.run_id,
                    workflow_runs.c.owner_user_id,
                    workflow_runs.c.task,
                    workflow_runs.c.model,
                    workflow_runs.c.status,
                    workflow_runs.c.created_at,
                    workflow_runs.c.completed_at,
                )
                .order_by(workflow_runs.c.completed_at.desc())
                .limit(limit)
            )
            if not include_all:
                if owner_user_id is None:
                    return []
                statement = statement.where(workflow_runs.c.owner_user_id == owner_user_id)

            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except Exception as exc:
            self._disable_after_error("list_runs", exc)
            return []
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
                owner_user_id=row["owner_user_id"],
            )
            for row in rows
        ]

    async def get_workflow_run(
        self,
        run_id: str,
        *,
        owner_user_id: str | None = None,
        include_all: bool = False,
    ) -> RunDetail | None:
        if self._engine is None:
            return None

        try:
            statement = select(workflow_runs).where(
                workflow_runs.c.run_id == UUID(run_id)
            )
            if not include_all:
                if owner_user_id is None:
                    return None
                statement = statement.where(workflow_runs.c.owner_user_id == owner_user_id)
            async with self._engine.connect() as connection:
                row = (
                    await connection.execute(statement)
                ).mappings().first()
                if row is None:
                    return None
                log_rows = (
                    await connection.execute(
                        select(workflow_logs)
                        .where(workflow_logs.c.run_id == UUID(run_id))
                        .order_by(workflow_logs.c.created_at.asc())
                    )
                ).mappings().all()
                evaluation_rows = (
                    await connection.execute(
                        select(run_evaluations)
                        .where(run_evaluations.c.run_id == UUID(run_id))
                        .order_by(run_evaluations.c.created_at.desc())
                    )
                ).mappings().all()
        except Exception as exc:
            self._disable_after_error("get_run", exc)
            return None

        return RunDetail(
            run_id=str(row["run_id"]),
            owner_user_id=(
                str(row["owner_user_id"]) if row["owner_user_id"] else None
            ),
            task=row["task"],
            model=row["model"],
            status=row["status"],
            logs=[
                WorkflowLog(
                    run_id=str(log["run_id"]),
                    created_at=log["created_at"].isoformat(),
                    agent_id=log["agent_id"],
                    agent_name=log["agent_name"],
                    status=log["status"],
                    message=log["message"],
                )
                for log in log_rows
            ],
            plan=row["plan"],
            worker_results=row["worker_results"],
            final_answer=row["final_answer"],
            tool_calls=row["tool_calls"] or [],
            output_format=row["output_format"] or "markdown",
            duration_ms=row["duration_ms"] or 0,
            estimated_tokens=row["estimated_tokens"] or 0,
            estimated_cost_usd=row["estimated_cost_usd"] or 0,
            evaluations=[
                EvaluationResult(
                    id=evaluation["id"],
                    run_id=str(evaluation["run_id"]),
                    rubric=evaluation["rubric"],
                    completeness=evaluation["completeness"],
                    actionability=evaluation["actionability"],
                    hallucination_risk=evaluation["hallucination_risk"],
                    overall=evaluation["overall"],
                    notes=evaluation["notes"],
                    created_at=evaluation["created_at"].isoformat(),
                )
                for evaluation in evaluation_rows
            ],
        )

    async def update_run_outputs(
        self,
        run_id: str,
        worker_results: list[WorkerResult],
        final_answer: str,
        output_format: str,
        *,
        owner_user_id: str | None = None,
        include_all: bool = False,
    ) -> None:
        if self._engine is None:
            return

        try:
            statement = update(workflow_runs).where(workflow_runs.c.run_id == UUID(run_id))
            if not include_all:
                if owner_user_id is None:
                    return
                statement = statement.where(workflow_runs.c.owner_user_id == owner_user_id)
            async with self._engine.begin() as connection:
                await connection.execute(
                    statement.values(
                        worker_results=[
                            result.model_dump(mode="json") for result in worker_results
                        ],
                        final_answer=final_answer,
                        output_format=output_format,
                        completed_at=_now(),
                    )
                )
        except Exception as exc:
            self._disable_after_error("update_run", exc)

    async def list_global_agent_profiles(self) -> list[AgentProfile]:
        if self._engine is None:
            return []
        try:
            async with self._engine.connect() as connection:
                rows = (await connection.execute(select(agent_profiles))).mappings().all()
        except Exception as exc:
            self._disable_after_error("list_agent_profiles", exc)
            return []
        return [AgentProfile.model_validate(dict(row)) for row in rows]

    async def list_agent_profiles(self, owner_user_id: str | None = None) -> list[AgentProfile]:
        if owner_user_id is None:
            return await self.list_global_agent_profiles()
        if self._engine is None:
            return []
        try:
            async with self._engine.connect() as connection:
                rows = (
                    await connection.execute(
                        select(user_agent_profiles).where(
                            user_agent_profiles.c.owner_user_id == owner_user_id
                        )
                    )
                ).mappings().all()
        except Exception as exc:
            self._disable_after_error("list_user_agent_profiles", exc)
            return []
        return [AgentProfile.model_validate(dict(row)) for row in rows]

    async def save_agent_profiles(
        self,
        profiles: list[AgentProfile],
        owner_user_id: str | None = None,
    ) -> None:
        if self._engine is None:
            return
        try:
            async with self._engine.begin() as connection:
                if owner_user_id is None:
                    await connection.execute(delete(agent_profiles))
                    table = agent_profiles
                    rows = [profile.model_dump(mode="json") for profile in profiles]
                else:
                    await connection.execute(
                        delete(user_agent_profiles).where(
                            user_agent_profiles.c.owner_user_id == owner_user_id
                        )
                    )
                    table = user_agent_profiles
                    updated_at = _now()
                    rows = [
                        {
                            **profile.model_dump(mode="json"),
                            "owner_user_id": owner_user_id,
                            "updated_at": updated_at,
                        }
                        for profile in profiles
                    ]
                if profiles:
                    await connection.execute(insert(table), rows)
        except Exception as exc:
            self._disable_after_error("save_agent_profiles", exc)

    async def list_memories(
        self,
        *,
        owner_user_id: str | None = None,
        include_all: bool = False,
    ) -> list[MemoryItem]:
        if self._engine is None:
            return []
        try:
            statement = select(memory_items).order_by(memory_items.c.created_at.desc())
            if not include_all:
                if owner_user_id is None:
                    return []
                statement = statement.where(memory_items.c.owner_user_id == owner_user_id)
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except Exception as exc:
            self._disable_after_error("list_memories", exc)
            return []
        return [
            MemoryItem(
                id=row["id"],
                owner_user_id=row["owner_user_id"],
                title=row["title"],
                category=row["category"],
                content=row["content"],
                enabled=row["enabled"],
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]

    async def create_memory(
        self,
        item_id: str,
        payload: MemoryCreateRequest,
        owner_user_id: str,
    ) -> MemoryItem:
        item = MemoryItem(
            id=item_id,
            owner_user_id=owner_user_id,
            title=payload.title,
            category=payload.category,
            content=payload.content,
            enabled=payload.enabled,
            created_at=_now().isoformat(),
        )
        if self._engine is not None:
            values = item.model_dump(mode="json")
            values["created_at"] = _parse_datetime(item.created_at)
            try:
                async with self._engine.begin() as connection:
                    await connection.execute(insert(memory_items).values(**values))
            except Exception as exc:
                self._disable_after_error("create_memory", exc)
        return item

    async def list_templates(self) -> list[WorkflowTemplate]:
        if self._engine is None:
            return []
        try:
            async with self._engine.connect() as connection:
                rows = (
                    await connection.execute(select(workflow_templates))
                ).mappings().all()
        except Exception as exc:
            self._disable_after_error("list_templates", exc)
            return []
        return [WorkflowTemplate.model_validate(dict(row)) for row in rows]

    async def save_evaluation(self, evaluation: EvaluationResult) -> None:
        if self._engine is None:
            return
        values = evaluation.model_dump(mode="json")
        values["run_id"] = UUID(evaluation.run_id)
        values["created_at"] = _parse_datetime(evaluation.created_at)
        try:
            async with self._engine.begin() as connection:
                await connection.execute(insert(run_evaluations).values(**values))
        except Exception as exc:
            self._disable_after_error("save_evaluation", exc)

    async def record_audit_event(
        self,
        *,
        event_id: str,
        action: str,
        actor_user_id: str | None = None,
        actor_email: str = "",
        actor_role: str = "",
        resource_type: str = "",
        resource_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        detail: Mapping[str, object] | None = None,
    ) -> None:
        if self._engine is None:
            return
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    insert(security_audit_events).values(
                        id=event_id,
                        actor_user_id=actor_user_id,
                        actor_email=actor_email,
                        actor_role=actor_role,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        ip_address=ip_address[:64],
                        user_agent=user_agent[:256],
                        detail=_sanitize_audit_detail(detail or {}),
                        created_at=_now(),
                    )
                )
        except Exception as exc:
            self._disable_after_error("record_audit_event", exc)

    async def list_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        if self._engine is None:
            return []
        try:
            async with self._engine.connect() as connection:
                rows = (
                    await connection.execute(
                        select(security_audit_events)
                        .order_by(security_audit_events.c.created_at.desc())
                        .limit(limit)
                    )
                ).mappings().all()
        except Exception as exc:
            self._disable_after_error("list_audit_events", exc)
            return []
        return [
            AuditEvent(
                id=str(row["id"]),
                actor_user_id=(
                    str(row["actor_user_id"]) if row["actor_user_id"] else None
                ),
                actor_email=str(row["actor_email"]),
                actor_role=str(row["actor_role"]),
                action=str(row["action"]),
                resource_type=str(row["resource_type"]),
                resource_id=str(row["resource_id"]),
                ip_address=str(row["ip_address"]),
                user_agent=str(row["user_agent"]),
                detail=cast(dict[str, object], row["detail"] or {}),
                created_at=_datetime_to_text(row["created_at"]),
            )
            for row in rows
        ]

    async def increment_rate_limit(
        self,
        key: str,
        *,
        window_seconds: int,
    ) -> int:
        if self._engine is None:
            return 1
        now = _now()
        expires_at = now + timedelta(seconds=max(1, window_seconds))
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    delete(rate_limit_counters)
                    .where(rate_limit_counters.c.key == key)
                    .where(rate_limit_counters.c.expires_at <= now)
                )
                statement = (
                    pg_insert(rate_limit_counters)
                    .values(
                        key=key,
                        window_start=now,
                        expires_at=expires_at,
                        count=1,
                        updated_at=now,
                    )
                    .on_conflict_do_update(
                        index_elements=[rate_limit_counters.c.key],
                        set_={
                            "count": rate_limit_counters.c.count + 1,
                            "updated_at": now,
                        },
                    )
                    .returning(rate_limit_counters.c.count)
                )
                row = (await connection.execute(statement)).first()
                return int(row[0]) if row is not None else 1
        except Exception as exc:
            self._disable_after_error("increment_rate_limit", exc)
            return 1

    async def reset_rate_limit(self, key: str) -> None:
        if self._engine is None:
            return
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    delete(rate_limit_counters).where(rate_limit_counters.c.key == key)
                )
        except Exception as exc:
            self._disable_after_error("reset_rate_limit", exc)

    async def delete_expired_rate_limits(self) -> None:
        if self._engine is None:
            return
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    delete(rate_limit_counters).where(
                        rate_limit_counters.c.expires_at <= _now()
                    )
                )
        except Exception as exc:
            self._disable_after_error("delete_expired_rate_limits", exc)

    async def _verify_schema(self) -> None:
        if self._engine is None:
            return

        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            table_names = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
            missing_tables = sorted(REQUIRED_TABLE_NAMES - table_names)
            missing_columns: list[str] = []
            if not missing_tables:
                for table_name, column_names in REQUIRED_TABLE_COLUMNS.items():
                    actual_columns = await connection.run_sync(
                        _inspect_column_names,
                        table_name,
                    )
                    missing_columns.extend(
                        f"{table_name}.{column_name}"
                        for column_name in sorted(column_names - actual_columns)
                    )

        if missing_tables:
            missing = ", ".join(missing_tables)
            raise DatabaseSchemaError(
                "Database schema is incomplete. "
                f"Missing tables: {missing}. "
                "Keep DATABASE_AUTO_MIGRATE=true for automatic startup migrations, "
                "or run `alembic upgrade head` from a release step."
            )
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise DatabaseSchemaError(
                "Database schema is incomplete. "
                f"Missing columns: {missing}. "
                "Keep DATABASE_AUTO_MIGRATE=true for automatic startup migrations, "
                "or run `alembic upgrade head` from a release step."
            )

    def _disable_after_error(self, operation: str, exc: Exception) -> None:
        self._last_error = _safe_db_error(exc)
        self._last_error_code = _classify_db_error(exc)
        logger.warning(
            "Database operation failed; database is unavailable for this process. "
            "operation=%s code=%s error=%s",
            operation,
            self._last_error_code,
            self._last_error,
        )
        self._engine = None


def _now() -> datetime:
    return datetime.now(UTC)


def _should_touch_session(
    last_seen_at: object,
    now: datetime,
    touch_interval_seconds: int,
) -> bool:
    if touch_interval_seconds <= 0 or not isinstance(last_seen_at, datetime):
        return True
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)
    return last_seen_at <= now - timedelta(seconds=touch_interval_seconds)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _row_to_auth_user(row: Mapping[str, object]) -> AuthUser:
    return AuthUser(
        id=str(row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        role=cast_user_role(str(row["role"])),
        created_at=_datetime_to_text(row["created_at"]),
    )


def _row_to_admin_user(row: Mapping[str, object]) -> AdminUser:
    return AdminUser(
        **_row_to_auth_user(row).model_dump(),
        is_active=bool(row["is_active"]),
        updated_at=_datetime_to_text(row["updated_at"]),
    )


def _datetime_to_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def cast_user_role(value: str) -> UserRole:
    if value in {"admin", "guest", "vip"}:
        return cast(UserRole, value)
    return "guest"


def _inspect_column_names(connection: Connection, table_name: str) -> set[str]:
    return {
        column["name"]
        for column in inspect(connection).get_columns(table_name)
    }


def _text_to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bool_to_text(value: bool) -> str:
    return "true" if value else "false"


def _sanitize_audit_detail(value: object) -> object:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            sensitive_terms = (
                "password",
                "token",
                "csrf",
                "api_key",
                "secret",
                "database_url",
                "db_url",
                "dsn",
                "authorization",
            )
            if any(term in key_lower for term in sensitive_terms):
                sanitized[key_text] = "[redacted]"
            else:
                sanitized[key_text] = _sanitize_audit_detail(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_audit_detail(item) for item in value]
    return value


def _safe_db_error(exc: Exception) -> str:
    message = redact_sensitive_text(str(exc).replace("\n", " ").strip())
    if len(message) > 280:
        message = f"{message[:277]}..."
    return f"{exc.__class__.__name__}: {message}"


def _classify_db_error(exc: Exception) -> str:
    if isinstance(exc, DatabaseSchemaError):
        return SCHEMA_INCOMPLETE_ERROR

    text = f"{exc.__class__.__name__}: {exc}".lower()
    if "password authentication failed" in text or "invalidpassword" in text:
        return "auth_failed"
    if "ssl" in text or "certificate" in text:
        return "ssl_failed"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "gaierror" in text or "name or service not known" in text or "nodename" in text:
        return "dns_failed"
    if "connection refused" in text:
        return "connection_refused"
    if "already exists" in text or "duplicatetable" in text:
        return "migration_conflict"
    return "connection_failed"


def _ssl_config(value: str) -> SslConfig:
    normalized = value.strip().lower()
    if normalized in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    if normalized in {
        "1",
        "true",
        "yes",
        "on",
        "require",
        "verify",
        "verify-ca",
        "verify-full",
        "strict",
    }:
        return ssl.create_default_context()
    if normalized == "insecure-require":
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    raise ValueError("Unsupported DATABASE_SSL mode.")
