"""Campaign database layer – single source of truth for all campaign data.

Public API
----------
- :func:`init_db` – create all tables (idempotent).
- :func:`get_session` – context-managed SQLAlchemy session.
- :class:`Base` – declarative base for ORM models.
- Models: :class:`Campaign`, :class:`CampaignUpdate`, :class:`CalendarDay`,
  :class:`CalendarEvent`, :class:`UploadedFile`, :class:`VisitorQuestion`.
- Repositories: :class:`CampaignRepository`, :class:`CampaignUpdateRepository`,
  :class:`CalendarRepository`, :class:`CalendarEventRepository`,
  :class:`UploadedFileRepository`, :class:`VisitorQuestionRepository`.

This package uses a **separate** SQLite database (``campaigns.db``) so
that the legacy ``app.db`` is not affected.
"""

from db.base import (
    Base,
    DATABASE_URL,
    DB_PATH,
    SessionLocal,
    engine,
    get_session,
    init_engine,
    utc_now,
)
from db.models import (
    Campaign,
    CampaignUpdate,
    CalendarDay,
    CalendarEvent,
    UploadedFile,
    VisitorQuestion,
    CampaignVisitor,
)
from db.platform_models import (
    AdminSession,
    AdminUser,
    AdminUserRole,
    AuditEvent,
    CampaignVersion,
    Conversation,
    ConversationMemory,
    ConversationState,
    IdempotencyKey,
    ImportBatch,
    Message,
    OutboxEvent,
    Permission,
    PrayerTime,
    RagDocument,
    RagIndexManifest,
    Role,
    RolePermission,
    Supervisor,
)
from db.repositories import (
    BaseRepository,
    CampaignRepository,
    CampaignUpdateRepository,
    CampaignVisitorRepository,
    CalendarRepository,
    CalendarEventRepository,
    UploadedFileRepository,
    VisitorQuestionRepository,
)
from db.init_db import (
    drop_all,
    get_schema_version,
    init_db,
    set_schema_version,
    upgrade_database,
)

__all__ = [
    # Base infrastructure
    "Base",
    "engine",
    "SessionLocal",
    "get_session",
    "init_engine",
    "init_db",
    "upgrade_database",
    "drop_all",
    "get_schema_version",
    "set_schema_version",
    "utc_now",
    "DATABASE_URL",
    "DB_PATH",
    # Models
    "Campaign",
    "CampaignUpdate",
    "CalendarDay",
    "CalendarEvent",
    "UploadedFile",
    "VisitorQuestion",
    "CampaignVisitor",
    "Supervisor",
    "CampaignVersion",
    "Conversation",
    "Message",
    "ConversationState",
    "ConversationMemory",
    "ImportBatch",
    "PrayerTime",
    "RagDocument",
    "RagIndexManifest",
    "AuditEvent",
    "OutboxEvent",
    "IdempotencyKey",
    "AdminUser",
    "AdminSession",
    "Role",
    "Permission",
    "AdminUserRole",
    "RolePermission",
    # Repositories
    "BaseRepository",
    "CampaignRepository",
    "CampaignUpdateRepository",
    "CampaignVisitorRepository",
    "CalendarRepository",
    "CalendarEventRepository",
    "UploadedFileRepository",
    "VisitorQuestionRepository",
]