from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

DEFAULT_WORKSPACE = "default"


def uuid_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Naive UTC timestamp used as a Python-side column default.

    Generating timestamps in Python (rather than relying only on the DB
    `func.now()` server default) guarantees microsecond precision that
    round-trips identically through SQLAlchemy on both SQLite and Postgres,
    which keyset (cursor) pagination depends on for a stable boundary.
    """
    return datetime.utcnow()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(50), default="operator")
    # Local-account auth (batch: identity & login). Nullable so external-only
    # identities need no local password. The hash is a self-describing scrypt
    # string; the plaintext password is never stored.
    password_hash: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | disabled
    mfa_state: Mapped[str] = mapped_column(String(20), default="none")  # none | totp | passkey

    calendars: Mapped[list[CalendarAccount]] = relationship(back_populates="user")
    inboxes: Mapped[list[InboxAccount]] = relationship(back_populates="user")


class Persona(TimestampMixin, Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(80), default="daypilot")
    install_state: Mapped[str] = mapped_column(String(80), default="INSTALLED_DISABLED")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    write_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class CalendarAccount(Base):
    __tablename__ = "calendar_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    external_account_id: Mapped[str] = mapped_column(String(320))
    sync_state: Mapped[str] = mapped_column(String(80), default="disabled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="calendars")


class InboxAccount(Base):
    __tablename__ = "inbox_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    external_account_id: Mapped[str] = mapped_column(String(320))
    sync_state: Mapped[str] = mapped_column(String(80), default="disabled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="inboxes")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    source_uri: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ingest_state: Mapped[str] = mapped_column(String(80), default="queued")
    # Presentation/routing metadata used by the Documents view and scale indexes.
    status: Mapped[str] = mapped_column(String(80), default="Not Yet Indexed")
    source: Mapped[str] = mapped_column(String(80), default="Local PC")
    # Version-safe outputs: generated files are new versions that reference the
    # original; the original is never modified.
    parent_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document")

    __table_args__ = (
        Index("ix_documents_project_status_source", "project_id", "status", "source"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    document: Mapped[Document] = relationship(back_populates="chunks")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("personas.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    risk: Mapped[str] = mapped_column(String(40), default="low")
    decision: Mapped[str] = mapped_column(String(80), default="recorded")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True)


# ---------------------------------------------------------------------------
# DayPilot domain model (batch B1)
#
# Designed for thousands of tasks/documents/agent runs per workspace. Every
# high-volume table carries a workspace_id and the composite indexes needed for
# fast server-side pagination, filtering, and sorting.
# ---------------------------------------------------------------------------


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    name: Mapped[str] = mapped_column(String(300))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="Active")
    risk: Mapped[str] = mapped_column(String(20), default="low")
    ai_activity: Mapped[str] = mapped_column(Text, default="")
    next_human_action: Mapped[str] = mapped_column(Text, default="")
    continue_action: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ai_actions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    designer_input: Mapped[list[Any]] = mapped_column(JSON, default=list)
    recent_signals: Mapped[list[Any]] = mapped_column(JSON, default=list)
    linked_sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    yesterday: Mapped[list[Any]] = mapped_column(JSON, default=list)
    today: Mapped[list[Any]] = mapped_column(JSON, default=list)
    blocked: Mapped[list[Any]] = mapped_column(JSON, default=list)

    __table_args__ = (Index("ix_projects_ws_status_risk", "workspace_id", "status", "risk"),)


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    title: Mapped[str] = mapped_column(String(500))
    owner: Mapped[str] = mapped_column(String(20), default="you")
    executor: Mapped[str] = mapped_column(String(120), default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="active")
    day: Mapped[str | None] = mapped_column(String(20), nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    parallel_ai: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_tasks_owner_status_project_due",
            "workspace_id",
            "owner",
            "status",
            "project_id",
            "due_date",
        ),
    )


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    name: Mapped[str] = mapped_column(String(200))
    agent_kind: Mapped[str] = mapped_column(String(80), default="assistant")
    current_work: Mapped[str] = mapped_column(Text, default="")
    # Durable run state (queued|running|succeeded|failed|cancelled) drives retries;
    # display_status maps to the UI (Running|Needs Approval|Blocked).
    state: Mapped[str] = mapped_column(String(40), default="queued")
    display_status: Mapped[str] = mapped_column(String(40), default="Running")
    provider: Mapped[str] = mapped_column(String(80), default="Ollabridge")
    model: Mapped[str] = mapped_column(String(120), default="")
    mode: Mapped[str] = mapped_column(String(20), default="Local")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)

    __table_args__ = (Index("ix_agent_runs_state_updated", "state", "updated_at"),)


class DayPlan(TimestampMixin, Base):
    __tablename__ = "day_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    plan_date: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(30), default="DRAFT")
    summary: Mapped[str] = mapped_column(Text, default="")

    blocks: Mapped[list[PlanBlock]] = relationship(
        back_populates="day_plan", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_day_plans_ws_date", "workspace_id", "plan_date"),)


class PlanBlock(Base):
    __tablename__ = "plan_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    day_plan_id: Mapped[str] = mapped_column(ForeignKey("day_plans.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    start_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    owner: Mapped[str] = mapped_column(String(20), default="you")
    source: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    day_plan: Mapped[DayPlan] = relationship(back_populates="blocks")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("personas.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    risk: Mapped[str] = mapped_column(String(20), default="low")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_approvals_ws_status_created", "workspace_id", "status", "created_at"),)


class Event(Base):
    """Today Context event stream. `seq` is a monotonic cursor for SSE resume."""

    __tablename__ = "events"

    # BigInteger on Postgres; INTEGER on SQLite so the PK maps to rowid and
    # autoincrements (a plain BIGINT PK does not autoincrement on SQLite).
    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    id: Mapped[str] = mapped_column(String(36), default=uuid_str, unique=True)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_events_ws_seq", "workspace_id", "seq"),)


class CodingRun(TimestampMixin, Base):
    __tablename__ = "coding_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    executor: Mapped[str] = mapped_column(String(40), default="gitpilot")
    repo: Mapped[str] = mapped_column(String(300), default="")
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="ask")
    status: Mapped[str] = mapped_column(String(40), default="queued")
    files_changed: Mapped[int] = mapped_column(Integer, default=0)
    tests_passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tests_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk: Mapped[str] = mapped_column(String(20), default="low")
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diff_summary: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (Index("ix_coding_runs_ws_status_updated", "workspace_id", "status", "updated_at"),)


class EmailItem(Base):
    __tablename__ = "email_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    inbox_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("inbox_accounts.id"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(500), default="")
    sender: Mapped[str] = mapped_column(String(320), default="")
    urgency: Mapped[str] = mapped_column(String(20), default="low")
    intent: Mapped[str] = mapped_column(String(80), default="")
    classification_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    draft_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="new")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_email_items_ws_status_received", "workspace_id", "status", "received_at"),)


class ChatSession(TimestampMixin, Base):
    """A persisted assistant conversation (ChatGPT / Claude style).

    Sessions let the user resume a conversation across refreshes and devices,
    rename/clear/delete them, and keep a browsable history. Only the
    conversation text is stored — never credentials or provider keys.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.seq"
    )

    __table_args__ = (Index("ix_chat_sessions_ws_updated", "workspace_id", "updated_at"),)


class ChatMessage(Base):
    """One turn in a ChatSession. `seq` orders turns within a session."""

    __tablename__ = "chat_messages"

    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    id: Mapped[str] = mapped_column(String(36), default=uuid_str, unique=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), default="user")  # user | assistant
    body: Mapped[str] = mapped_column(Text, default="")
    action_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_chat_messages_session_seq", "session_id", "seq"),)


class MailboxConnection(TimestampMixin, Base):
    """A workspace's real mailbox connection (Gmail/Microsoft OAuth or generic
    IMAP/SMTP). The backend owns mail connection state; the UI never infers a
    mailbox from local state. Passwords/OAuth tokens live in the credential
    store by `secret_reference` and are never stored here, returned, or logged."""

    __tablename__ = "mailbox_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    provider: Mapped[str] = mapped_column(String(30))  # gmail | microsoft | imap | mailu
    email_address: Mapped[str] = mapped_column(String(320), default="")
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    username: Mapped[str | None] = mapped_column(String(320), nullable=True)
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    imap_security: Mapped[str] = mapped_column(String(10), default="ssl")  # ssl | starttls
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_security: Mapped[str] = mapped_column(String(10), default="starttls")
    status: Mapped[str] = mapped_column(String(20), default="unconfigured")
    secret_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    oauth_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (Index("ix_mailbox_ws", "workspace_id", unique=True),)


class KnowledgeSource(TimestampMixin, Base):
    """A persisted knowledge source a workspace has granted for RAG (Issue 1).

    The backend owns source state — the Settings screen lists real rows, not
    hard-coded samples. Re-indexing runs as a durable background job; status
    reflects the real lifecycle (queued → indexing → indexed | failed)."""

    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    provider: Mapped[str] = mapped_column(String(20), default="local")  # local | box | vault
    display_name: Mapped[str] = mapped_column(String(300), default="")
    location: Mapped[str] = mapped_column(String(1000), default="")  # server path or box ref
    scope: Mapped[str] = mapped_column(String(200), default="")
    permission: Mapped[str] = mapped_column(String(20), default="read_index")  # read | read_index
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|indexing|indexed|failed|unconfigured
    project_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(400), nullable=True)

    __table_args__ = (Index("ix_knowledge_sources_ws", "workspace_id", "created_at"),)


class AssistantRun(TimestampMixin, Base):
    """One assistant turn, orchestrated server-side (Batch 4).

    The backend owns intent routing and capability dispatch — the browser sends
    a message and renders the result. Every run records the classified intent,
    the tools invoked with their risk class, the deterministic reply/action, and
    whether the run was in limited mode (no AI provider connected). Runs are the
    audit trail for what the assistant did on the user's behalf; it never sends
    email or calls a provider directly, and every write stays approval-gated."""

    __tablename__ = "assistant_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(40), default="unknown")
    state: Mapped[str] = mapped_column(String(20), default="running")  # running|succeeded|failed|cancelled
    reply: Mapped[str] = mapped_column(Text, default="")
    action_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tools_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    limited: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(40), default="deterministic")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_assistant_runs_ws_created", "workspace_id", "created_at"),)


class AssistantRunEvent(Base):
    """An ordered event emitted during an assistant run (intent classified, tool
    invoked, completed). `seq` orders events within the run."""

    __tablename__ = "assistant_run_events"

    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    type: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    __table_args__ = (Index("ix_assistant_run_events_run_seq", "run_id", "seq"),)


class ProviderConnection(TimestampMixin, Base):
    """A workspace's AI-provider connection (local Ollabridge or Ollabridge
    Cloud). The backend owns provider state — the browser never determines it.
    Only safe metadata lives here; keys/tokens are held by the credential store,
    referenced by `secret_reference`, and never returned or logged."""

    __tablename__ = "provider_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    kind: Mapped[str] = mapped_column(String(30))  # local | ollabridge_cloud
    base_url: Mapped[str] = mapped_column(String(500), default="")
    state: Mapped[str] = mapped_column(String(20), default="unconfigured")
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    account_subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    account_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    models_count: Mapped[int] = mapped_column(Integer, default=0)
    secret_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (Index("ix_provider_ws_kind", "workspace_id", "kind", unique=True),)


class Workspace(TimestampMixin, Base):
    """A tenant boundary. Every data row is workspace-scoped; membership decides
    who may act in it. The default single-user install has one workspace."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(200), default="My workspace")
    mode: Mapped[str] = mapped_column(String(20), default="local")  # local | team
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class WorkspaceMembership(Base):
    """Grants a user a role within a workspace. Authorization is derived from
    this — arbitrary browser-supplied workspace ids are never trusted."""

    __tablename__ = "workspace_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | operator | reviewer | read_only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_membership_user_ws", "user_id", "workspace_id", unique=True),)


class AuthSession(Base):
    """A server-side session. Only the SHA-256 of the opaque session token is
    stored (`id_hash`); the token itself lives in an HttpOnly cookie and is
    never persisted or logged. Revocable and expiring."""

    __tablename__ = "auth_sessions"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36))
    csrf_token: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExternalIdentity(Base):
    """A federated identity (e.g. Ollabridge Cloud, enterprise OIDC) linked to a
    local user. Secrets live in the secret store by reference, never here."""

    __tablename__ = "external_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    issuer: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    secret_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_extid_issuer_subject", "issuer", "subject", unique=True),)


class AuthEvent(Base):
    """Append-only auth audit trail (login success/failure, logout, bootstrap).
    Drives rate limiting/backoff. No passwords or tokens are recorded."""

    __tablename__ = "auth_events"

    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(20))  # success | failure | locked
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_authevent_email_created", "email", "created_at"),)


class Job(TimestampMixin, Base):
    """Durable background job (batch B12) — agent runs and document indexing.

    State machine: queued -> running -> succeeded | failed(retry) -> dead_letter.
    `run_after` supports backoff scheduling; `attempts`/`max_attempts` bound retries.
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_jobs_state_runafter", "state", "run_after"),)


class IntegrationConnection(TimestampMixin, Base):
    """A workspace's connection to an external integration provider (Integration
    Platform, batch I0).

    The record holds only non-sensitive metadata — credentials live in the
    secrets backend keyed by connection id and are never persisted here.
    `permissions_json` optionally overrides the default per-capability
    permission (read=allowed, write/destructive=approval_required).
    """

    __tablename__ = "integration_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), default="connected")  # connected | error | expired
    auth_type: Mapped[str] = mapped_column(String(20), default="api_key")  # oauth | api_key | mcp
    capabilities: Mapped[list[Any]] = mapped_column(JSON, default=list)     # list[str]
    permissions_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    detail: Mapped[str] = mapped_column(Text, default="")                   # health detail — never secrets
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_integration_connections_ws_provider", "workspace_id", "provider"),)


class MCPConnection(TimestampMixin, Base):
    """A remote or local MCP server attached to a workspace (batch I4/I5).

    Tools discovered from the server are stored with an auto-classification
    (read/write/destructive) that an administrator can override. Only
    `enabled_tools` are callable, and calls flow through the same policy +
    approval layer as any other integration.
    """

    __tablename__ = "mcp_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    name: Mapped[str] = mapped_column(String(200))
    transport: Mapped[str] = mapped_column(String(20), default="streamable_http")  # stdio | streamable_http
    endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="connected")  # connected | unavailable | error
    enabled_tools: Mapped[list[Any]] = mapped_column(JSON, default=list)
    tools_json: Mapped[list[Any]] = mapped_column(JSON, default=list)   # [{name, description, kind}]
    overrides_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {tool: kind}
    detail: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (Index("ix_mcp_connections_ws", "workspace_id", "name"),)


class CalendarEvent(TimestampMixin, Base):
    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(String(36), default=DEFAULT_WORKSPACE, index=True)
    calendar_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("calendar_accounts.id"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[str] = mapped_column(String(80), default="you")
    source: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="confirmed")
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)

    __table_args__ = (Index("ix_calendar_events_ws_start", "workspace_id", "start_at"),)
