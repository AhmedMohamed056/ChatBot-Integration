"""SQLite extract helpers for staged PostgreSQL migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(f"SELECT * FROM {table}")
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.Error:
        return []


def extract_legacy_app_db(path: Path) -> dict[str, list[dict[str, Any]]]:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return {
            "campaigns": _rows(conn, "campaigns"),
            "campaign_messages": _rows(conn, "campaign_messages"),
            "system_settings": _rows(conn, "system_settings"),
            "uploaded_files": _rows(conn, "uploaded_files"),
            "visitor_questions": _rows(conn, "visitor_questions"),
        }
    finally:
        conn.close()


def extract_campaign_db(path: Path) -> dict[str, list[dict[str, Any]]]:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        tables = [
            "campaigns",
            "campaign_updates",
            "campaign_visitors",
            "calendar_events",
            "visitor_questions",
            "uploaded_files",
        ]
        return {name: _rows(conn, name) for name in tables}
    finally:
        conn.close()


def reconcile_counts(
    legacy: dict[str, list[dict[str, Any]]],
    modern: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, int]]:
    keys = sorted(set(legacy.keys()) | set(modern.keys()))
    return {
        key: {
            "legacy": len(legacy.get(key, [])),
            "modern": len(modern.get(key, [])),
        }
        for key in keys
    }
