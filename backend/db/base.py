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

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent

#: Database file path.  Override via the ``CAMPAIGN_DB_PATH`` environment
#: variable so tests / deployments can redirect it.
DB_PATH = Path(os.getenv("CAMPAIGN_DB_PATH", str(BACKEND_DIR / "campaigns.db")))

#: SQLite connection URL.
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

engine: Engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """Enable foreign-key enforcement on every new SQLite connection.

    SQLite does **not** enforce foreign keys by default; this PRAGMA must be
    set per-connection.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


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
    """Re-create the engine pointing at *db_path*.

    Primarily useful for tests that need an in-memory or temporary
    database.  When *db_path* is ``None`` the default :data:`DB_PATH` is
    used.
    """
    global engine, SessionLocal

    if db_path is None:
        url = DATABASE_URL
    else:
        url = f"sqlite:///{db_path}"

    engine = create_engine(
        url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    # Re-attach the PRAGMA hook
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    SessionLocal.configure(bind=engine)
    return engine