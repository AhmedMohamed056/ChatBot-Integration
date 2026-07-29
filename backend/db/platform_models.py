"""Phase 1 platform models sharing the application's unified metadata."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, utc_now


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Supervisor(TimestampMixin, Base):
    __tablename__ = "supervisors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    owned_campaigns: Mapped[List["Campaign"]] = relationship(
        "Campaign", back_populates="owner"
    )

    __table_args__ = (
        Index("ix_supervisors_active_phone", "is_active", "phone_number"),
        CheckConstraint(
            "NOT is_active OR deactivated_at IS NULL",
            name="ck_supervisors_active_not_deactivated",
        ),
    )


class CampaignVersion(Base):
    """Immutable snapshot; application code must only insert rows."""

    __tablename__ = "campaign_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_by_supervisor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("supervisors.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "version_number", name="uq_campaign_versions_number"
        ),
        Index("ix_campaign_versions_campaign_created", "campaign_id", "created_at"),
        CheckConstraint("version_number >= 1", name="ck_campaign_versions_positive"),
    )


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    participant_phone: Mapped[Optional[str]] = mapped_column(String(50))
    chat_type: Mapped[str] = mapped_column(String(20), nullable=False, default="private")
    campaign_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    lock_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    state: Mapped[Optional["ConversationState"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", uselist=False
    )
    memories: Mapped[List["ConversationMemory"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    __mapper_args__ = {"version_id_col": lock_version}
    __table_args__ = (
        UniqueConstraint(
            "channel", "external_chat_id", name="uq_conversations_channel_chat"
        ),
        Index("ix_conversations_participant_phone", "participant_phone"),
        Index("ix_conversations_campaign_status", "campaign_id", "status"),
        CheckConstraint("lock_version >= 1", name="ck_conversations_lock_positive"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    external_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    sender_phone: Mapped[Optional[str]] = mapped_column(String(50))
    message_type: Mapped[str] = mapped_column(String(30), nullable=False, default="text")
    body: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "external_message_id",
            name="uq_messages_conversation_external",
        ),
        Index("ix_messages_conversation_occurred", "conversation_id", "occurred_at"),
        CheckConstraint(
            "direction IN ('inbound','outbound','system')",
            name="ck_messages_direction",
        ),
    )


class ConversationState(TimestampMixin, Base):
    __tablename__ = "conversation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    state_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lock_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    conversation: Mapped["Conversation"] = relationship(back_populates="state")

    __mapper_args__ = {"version_id_col": lock_version}


class ConversationMemory(Base):
    __tablename__ = "conversation_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    memory_key: Mapped[str] = mapped_column(String(100), nullable=False)
    memory_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    retained_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tombstoned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    conversation: Mapped["Conversation"] = relationship(back_populates="memories")

    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "memory_key", name="uq_conversation_memory_key"
        ),
        Index("ix_conversation_memories_retention", "retained_until", "tombstoned_at"),
    )


class ImportBatch(TimestampMixin, Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    requested_by_admin_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    source_file_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="SET NULL")
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_import_batches_type_status", "import_type", "status"),
        CheckConstraint("row_count >= 0", name="ck_import_batches_rows"),
        CheckConstraint("error_count >= 0", name="ck_import_batches_errors"),
    )


class PrayerTime(Base):
    __tablename__ = "prayer_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prayer_date: Mapped[date] = mapped_column(Date, nullable=False)
    location_key: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Riyadh"
    )
    fajr: Mapped[str] = mapped_column(String(8), nullable=False)
    dhuhr: Mapped[str] = mapped_column(String(8), nullable=False)
    asr: Mapped[str] = mapped_column(String(8), nullable=False)
    maghrib: Mapped[str] = mapped_column(String(8), nullable=False)
    isha: Mapped[str] = mapped_column(String(8), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        UniqueConstraint("prayer_date", "location_key", name="uq_prayer_times_day_place"),
    )


class RagDocument(TimestampMixin, Base):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stable_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    campaign_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("campaign_versions.id", ondelete="CASCADE")
    )
    source_file_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    tombstoned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_rag_documents_campaign_version", "campaign_id", "campaign_version_id"),
        Index("ix_rag_documents_checksum", "checksum"),
    )


class RagIndexManifest(TimestampMixin, Base):
    __tablename__ = "rag_index_manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    index_name: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    __table_args__ = (
        UniqueConstraint(
            "document_id", "index_name", "embedding_model",
            name="uq_rag_manifest_document_index_model",
        ),
        CheckConstraint("chunk_count >= 0", name="ck_rag_manifest_chunks"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(255))
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100))
    before_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    after_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id", "occurred_at"),
        Index("ix_audit_events_correlation", "correlation_id"),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_outbox_events_pending", "published_at", "available_at"),
        CheckConstraint("attempts >= 0", name="ck_outbox_attempts"),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[Optional[int]] = mapped_column(Integer)
    response_body: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
        Index("ix_idempotency_expires_at", "expires_at"),
    )


class AdminUser(TimestampMixin, Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    lock_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    __mapper_args__ = {"version_id_col": lock_version}


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_admin_sessions_user_expiry", "admin_user_id", "expires_at"),
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)


class AdminUserRole(Base):
    __tablename__ = "admin_user_roles"

    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )
