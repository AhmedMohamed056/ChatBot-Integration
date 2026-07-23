"""Campaign database layer – single source of truth for all campaign data.

Public API
----------
- :func:`init_db` – create all tables (idempotent).
- :func:`get_session` – context-managed SQLAlchemy session.
- :class:`Base` – declarative base for ORM models.
- Models: :class:`Campaign`, :class:`CampaignUpdate`, :class:`CalendarDay`,
  :class:`UploadedFile`, :class:`VisitorQuestion`.
- Repositories: :class:`CampaignRepository`, :class:`CampaignUpdateRepository`,
  :class:`CalendarRepository`, :class:`UploadedFileRepository`,
  :class:`VisitorQuestionRepository`.

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
    UploadedFile,
    VisitorQuestion,
)
from db.repositories import (
    BaseRepository,
    CampaignRepository,
    CampaignUpdateRepository,
    CalendarRepository,
    UploadedFileRepository,
    VisitorQuestionRepository,
)
from db.init_db import init_db, drop_all, get_schema_version, set_schema_version

__all__ = [
    # Base infrastructure
    "Base",
    "engine",
    "SessionLocal",
    "get_session",
    "init_engine",
    "init_db",
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
    "UploadedFile",
    "VisitorQuestion",
    # Repositories
    "BaseRepository",
    "CampaignRepository",
    "CampaignUpdateRepository",
    "CalendarRepository",
    "UploadedFileRepository",
    "VisitorQuestionRepository",
]