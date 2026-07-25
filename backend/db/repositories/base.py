"""Generic repository base class.

Provides common CRUD operations so that concrete repositories can focus
on entity-specific queries.
"""

from __future__ import annotations

from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Generic CRUD repository.

    Subclasses must set :attr:`model` to the SQLAlchemy model class.
    """

    model: Type[T]

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[T]:
        """Return the entity with the given primary key, or ``None``."""
        return self.session.get(self.model, entity_id)

    def list_all(
        self,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[T]:
        """Return all entities, optionally paginated."""
        stmt = select(self.model)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def count(self) -> int:
        """Return the total number of entities."""
        from sqlalchemy import func

        return self.session.execute(
            select(func.count()).select_from(self.model)
        ).scalar_one()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: dict[str, Any]) -> T:
        """Insert a new entity from a dict of column values."""
        obj = self.model(**data)
        self.session.add(obj)
        self.session.flush()  # populate obj.id without committing
        self.session.refresh(obj)
        return obj

    def bulk_create(self, items: list[dict[str, Any]]) -> List[T]:
        """Insert multiple entities at once."""
        objs = [self.model(**item) for item in items]
        self.session.add_all(objs)
        self.session.flush()
        for obj in objs:
            self.session.refresh(obj)
        return objs

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, entity: T, data: dict[str, Any]) -> T:
        """Update an existing entity with the given column values."""
        for key, value in data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        self.session.flush()
        self.session.refresh(entity)
        return entity

    def update_by_id(self, entity_id: int, data: dict[str, Any]) -> Optional[T]:
        """Update an entity by primary key. Returns ``None`` if not found."""
        entity = self.get_by_id(entity_id)
        if entity is None:
            return None
        return self.update(entity, data)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, entity: T) -> bool:
        """Delete an entity. Returns ``True``."""
        self.session.delete(entity)
        self.session.flush()
        return True

    def delete_by_id(self, entity_id: int) -> bool:
        """Delete an entity by primary key. Returns ``False`` if not found."""
        entity = self.get_by_id(entity_id)
        if entity is None:
            return False
        return self.delete(entity)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def to_dict(self, entity: T) -> dict[str, Any]:
        """Convert an entity to a plain dict (useful for API responses)."""
        result: dict[str, Any] = {}
        for column in self.model.__table__.columns:
            value = getattr(entity, column.name, None)
            # Convert date/datetime to ISO format for JSON serialisation
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            result[column.name] = value
        return result