"""SQLAlchemy engine, session management, and declarative base.

This module provides the core database infrastructure for the new
campaign database layer. It uses a **separate** SQLite database file
(``campaigns.db``) so that the existing ``app.db`` (managed by the
legacy ``database.py`` module) is not affected.

Usage
-----
    from db import get_session, CampaignRepository

    with get_session() as session:
        repo = CampaignRepository(session)
        campaign = repo.create({"campaign_name": "Ramadan 1447", ...})
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from settings import get_settings

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
_settings = get_settings()

# Compatibility exports. New code should consume ``get_settings()``.
DATABASE_URL = _settings.database_url
DB_PATH = Path(DATABASE_URL.removeprefix("sqlite:///")) if DATABASE_URL.startswith(
    "sqlite:///"
) else None

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

def _engine_options(url: str) -> dict:
    options: dict = {
        "echo": get_settings().database_echo,
        "future": True,
        "pool_pre_ping": get_settings().database_pool_pre_ping,
    }
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    else:
        options["pool_size"] = get_settings().database_pool_size
        options["max_overflow"] = get_settings().database_max_overflow
    return options


def create_database_engine(url: str) -> Engine:
    """Create an engine with dialect-appropriate production defaults."""
    new_engine = create_engine(url, **_engine_options(url))
    if new_engine.dialect.name == "sqlite":
        event.listen(new_engine, "connect", _set_sqlite_pragma)
    return new_engine


def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001, ARG001
    """Enable SQLite foreign keys for parity with PostgreSQL."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


engine: Engine = create_database_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Common declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware ``datetime``."""
    return datetime.now(timezone.utc)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session with automatic commit / rollback.

    Usage::

        with get_session() as session:
            repo = CampaignRepository(session)
            ...

    The session is committed on normal exit and rolled back on any
    exception.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_engine(db_path: str | Path | None = None) -> Engine:
    """Rebind sessions to a URL or legacy SQLite path.

    This compatibility helper is primarily intended for tests. Production
    processes should configure ``DATABASE_URL`` before importing the app.
    """
    global engine, SessionLocal

    if db_path is None:
        url = get_settings().database_url
    else:
        value = str(db_path)
        url = value if "://" in value else f"sqlite:///{value}"

    engine.dispose()
    engine = create_database_engine(url)
    SessionLocal.configure(bind=engine)
    return engine