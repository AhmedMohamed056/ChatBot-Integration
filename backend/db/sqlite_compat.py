"""Add missing columns on legacy SQLite ``campaigns.db`` files."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from db import base as _base

logger = logging.getLogger(__name__)

# (table, column, SQLite ADD COLUMN fragment)
_SQLITE_COLUMN_PATCHES: tuple[tuple[str, str, str], ...] = (
    ("campaign_updates", "campaign_version_id", "INTEGER"),
    ("campaigns", "owner_supervisor_id", "INTEGER"),
    ("campaigns", "lock_version", "INTEGER NOT NULL DEFAULT 1"),
    ("campaigns", "campaign_type", "VARCHAR(100)"),
    ("campaigns", "start_date", "DATE"),
    ("campaigns", "end_date", "DATE"),
    ("campaigns", "description", "TEXT"),
    ("campaigns", "notes", "TEXT"),
    ("campaigns", "created_at", "DATETIME"),
    ("campaigns", "updated_at", "DATETIME"),
)


def apply_sqlite_schema_patches() -> None:
    """Bring an older local SQLite file in line with current ORM models."""
    engine = _base.engine
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, column, col_type in _SQLITE_COLUMN_PATCHES:
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column in existing:
                continue
            stmt = text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            conn.execute(stmt)
            logger.info("SQLite patch: added %s.%s", table, column)
