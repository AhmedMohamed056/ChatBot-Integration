"""Database initialization and lightweight migration support.

This module provides:
- :func:`init_db` – create all tables (idempotent, safe to call on startup).
- :func:`drop_all` – drop all tables (useful for tests / resets).
- A simple schema-version mechanism stored in a ``schema_version`` table
  so future migrations can detect the current state and apply changes
  incrementally.

Usage
-----
    from db import init_db
    init_db()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from sqlalchemy import inspect, text

from db import base as _base
from db.base import Base
from db.models import (  # noqa: F401 – import so models register with Base
    Campaign,
    CampaignUpdate,
    CalendarDay,
    CalendarEvent,
    UploadedFile,
    VisitorQuestion,
    CampaignVisitor,
)
from db import platform_models as _platform_models  # noqa: F401

logger = logging.getLogger(__name__)

#: Current schema version.  Increment when a migration is added.
CURRENT_SCHEMA_VERSION = "0001_phase1_foundation"

_SCHEMA_VERSION_TABLE = "schema_version"


def _get_engine():
    """Return the current engine from :mod:`db.base`.

    This is looked up dynamically so that :func:`db.init_engine` calls
    (which reassign ``db.base.engine``) are reflected here.
    """
    return _base.engine


def init_db() -> None:
    """Create all tables for tests and staged SQLite compatibility.

    Production deployments must call :func:`upgrade_database` so Alembic
    owns schema evolution. This helper remains idempotent for legacy callers.
    """
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)
    from db.sqlite_compat import apply_sqlite_schema_patches

    apply_sqlite_schema_patches()
    logger.info("Database metadata created for compatibility/testing")


def upgrade_database(revision: str = "head") -> None:
    """Upgrade the configured database using the repository Alembic config."""
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", str(_get_engine().url))
    command.upgrade(config, revision)


def drop_all() -> None:
    """Drop **all** tables.  Mainly for tests and full resets."""
    engine = _get_engine()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Schema version helpers
# ---------------------------------------------------------------------------


def _ensure_schema_version_table() -> None:
    """Create the ``schema_version`` table if it doesn't exist."""
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {_SCHEMA_VERSION_TABLE} (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )
        )


def get_schema_version() -> Optional[Union[int, str]]:
    """Return the Alembic revision (or a legacy integer), if present."""
    engine = _get_engine()
    inspector = inspect(engine)
    if inspector.has_table("alembic_version"):
        with engine.begin() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if not inspector.has_table(_SCHEMA_VERSION_TABLE):
        return None
    with engine.begin() as conn:
        result = conn.execute(
            text(f"SELECT version FROM {_SCHEMA_VERSION_TABLE} ORDER BY version DESC LIMIT 1")
        )
        row = result.fetchone()
    return row[0] if row else None


def set_schema_version(version: int) -> None:
    """Legacy compatibility helper; Alembic owns new schema versions."""
    engine = _get_engine()
    _ensure_schema_version_table()
    with engine.begin() as conn:
        # Delete any existing rows then insert the new version
        conn.execute(text(f"DELETE FROM {_SCHEMA_VERSION_TABLE}"))
        conn.execute(
            text(f"INSERT INTO {_SCHEMA_VERSION_TABLE} (version) VALUES (:version)"),
            {"version": version},
        )


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------


def _run_migrations(from_version: int) -> None:
    """Apply incremental migrations from *from_version* to current.

    Migrations are applied in order as ``if from_version < N: ...`` blocks.
    """
    engine = _get_engine()

    # Migration 2: rebuild the ``visitor_questions`` table to match the
    # Task 10 schema (phone_number, visitor_name, campaign_name, question,
    # detected_language, message_timestamp, created_at).  The previous
    # schema had different columns (detected_campaign, ai_answer, answered,
    # campaign_id FK).  SQLite cannot drop columns cheaply, so we drop and
    # recreate the table.  Existing logged questions are discarded because
    # they used the old (pre-Task-10) schema.
    if from_version < 2:
        logger.info("Migration 2: rebuilding visitor_questions table")
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS visitor_questions"))
        # Recreate the table from the current model definition.
        VisitorQuestion.__table__.create(bind=engine, checkfirst=True)
        set_schema_version(2)

    set_schema_version(CURRENT_SCHEMA_VERSION)
    logger.info("Migrations applied – now at schema version %d", CURRENT_SCHEMA_VERSION)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print(f"Database initialised. Schema version: {get_schema_version()}")
    print(f"Tables: {sorted(Base.metadata.tables.keys())}")