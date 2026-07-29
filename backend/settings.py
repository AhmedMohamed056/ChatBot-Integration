"""Typed, centralized application settings.

Environment variables remain the deployment boundary.  No database
credentials are read from source files or persisted in application tables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = BACKEND_DIR / "campaigns.db"


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    database_url: str
    database_echo: bool = False
    database_pool_pre_ping: bool = True
    database_pool_size: int = 5
    database_max_overflow: int = 10

    @classmethod
    def from_env(cls) -> "Settings":
        legacy_path = os.getenv("CAMPAIGN_DB_PATH")
        default_url = f"sqlite:///{legacy_path or DEFAULT_SQLITE_PATH}"
        return cls(
            database_url=os.getenv("DATABASE_URL", default_url),
            database_echo=_as_bool(os.getenv("DATABASE_ECHO"), False),
            database_pool_pre_ping=_as_bool(
                os.getenv("DATABASE_POOL_PRE_PING"), True
            ),
            database_pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
            database_max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
        )


def get_settings() -> Settings:
    """Return a fresh settings snapshot (friendly to tests and workers)."""
    return Settings.from_env()
