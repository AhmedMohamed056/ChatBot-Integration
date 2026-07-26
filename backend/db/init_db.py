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
from typing import Optional

from sqlalchemy import inspect, text

from db import base as _base
from db.base import Base
from db.models import (  # noqa: F401 – import so models register with Base
    Campaign,
    CampaignUpdate,
    CalendarDay,
    UploadedFile,
    VisitorQuestion,
    CampaignVisitor,
)

logger = logging.getLogger(__name__)

#: Current schema version.  Increment when a migration is added.
CURRENT_SCHEMA_VERSION = 1

_SCHEMA_VERSION_TABLE = "schema_version"


def _get_engine():
    """Return the current engine from :mod:`db.base`.

    This is looked up dynamically so that :func:`db.init_engine` calls
    (which reassign ``db.base.engine``) are reflected here.
    """
    return _base.engine


def init_db() -> None:
    """Create all tables if they don't already exist.

    This is **idempotent** – calling it multiple times is safe.  It also
    records the schema version for future migration logic.
    """
    engine = _get_engine()
    # Import all models so they are registered on Base.metadata
    Base.metadata.create_all(bind=engine)

    _ensure_schema_version_table()
    version = get_schema_version()
    if version is None:
        set_schema_version(CURRENT_SCHEMA_VERSION)
        logger.info("Database initialised at schema version %d", CURRENT_SCHEMA_VERSION)
    elif version < CURRENT_SCHEMA_VERSION:
        logger.info(
            "Database at schema version %d, current is %d – running migrations",
            version,
            CURRENT_SCHEMA_VERSION,
        )
        _run_migrations(version)
    else:
        logger.debug("Database already at schema version %d", version)


def drop_all() -> None:
    """Drop **all** tables.  Mainly for tests and full resets."""
    engine = _get_engine()
    Base.metadata.drop_all(bind=engine)
    # Also drop the schema-version table if present
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {_SCHEMA_VERSION_TABLE}"))


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


def get_schema_version() -> Optional[int]:
    """Return the current schema version, or ``None`` if not set."""
    engine = _get_engine()
    inspector = inspect(engine)
    if not inspector.has_table(_SCHEMA_VERSION_TABLE):
        return None
    with engine.begin() as conn:
        result = conn.execute(
            text(f"SELECT version FROM {_SCHEMA_VERSION_TABLE} ORDER BY version DESC LIMIT 1")
        )
        row = result.fetchone()
    return row[0] if row else None


def set_schema_version(version: int) -> None:
    """Record a schema version (insert or update the single row)."""
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
# Migration runner (placeholder for future migrations)
# ---------------------------------------------------------------------------


def _run_migrations(from_version: int) -> None:
    """Apply incremental migrations from *from_version* to current.

    Currently a no-op because we're at version 1.  Future migrations
    should be added as ``if from_version < N: ...`` blocks.
    """
    # Example for future use:
    # if from_version < 2:
    #     engine = _get_engine()
    #     with engine.begin() as conn:
    #         conn.execute(text("ALTER TABLE campaigns ADD COLUMN new_col TEXT"))
    #     set_schema_version(2)

    set_schema_version(CURRENT_SCHEMA_VERSION)
    logger.info("Migrations applied – now at schema version %d", CURRENT_SCHEMA_VERSION)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print(f"Database initialised. Schema version: {get_schema_version()}")
    print(f"Tables: {sorted(Base.metadata.tables.keys())}")