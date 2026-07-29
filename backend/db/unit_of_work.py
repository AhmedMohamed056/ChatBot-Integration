"""Transaction boundary abstractions for application services."""

from __future__ import annotations

from types import TracebackType
from typing import Optional, Protocol, Type

from sqlalchemy.orm import Session, sessionmaker

from db.base import SessionLocal


class UnitOfWork(Protocol):
    """Minimal service-facing transaction contract."""

    session: Session

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork:
    """SQLAlchemy implementation; commits only when explicitly requested."""

    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if exc_type is not None:
            self.rollback()
        self.session.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
