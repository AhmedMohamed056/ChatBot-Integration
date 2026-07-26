"""Repository for :class:`CalendarEvent` entities.

This repository is intentionally **independent** of the
:class:`CalendarRepository` (which manages the prayer-times / Hijri
``calendar_days`` table).  It only deals with the simple event rows
imported from the administrator-uploaded Calendar Excel file.
"""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import CalendarEvent
from db.repositories.base import BaseRepository


class CalendarEventRepository(BaseRepository[CalendarEvent]):
    """CRUD + domain-specific queries for calendar events."""

    model = CalendarEvent

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Read – domain-specific lookups
    # ------------------------------------------------------------------

    def list_by_date(self, event_date: str) -> List[CalendarEvent]:
        """Return all events whose ``event_date`` matches (case-insensitive)."""
        stmt = (
            select(CalendarEvent)
            .where(func.lower(CalendarEvent.event_date) == event_date.lower())
            .order_by(CalendarEvent.id)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_by_day(self, day_name: str) -> List[CalendarEvent]:
        """Return all events whose ``day_name`` matches (case-insensitive)."""
        stmt = (
            select(CalendarEvent)
            .where(func.lower(CalendarEvent.day_name) == day_name.lower())
            .order_by(CalendarEvent.id)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_all_ordered(self) -> List[CalendarEvent]:
        """Return all events ordered by date then id."""
        stmt = (
            select(CalendarEvent)
            .order_by(CalendarEvent.event_date, CalendarEvent.id)
        )
        return list(self.session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def replace_all(self, items: list[dict[str, Any]]) -> int:
        """Delete every existing event and insert *items* in one transaction.

        Returns the number of inserted rows.  This keeps the table an
        exact mirror of the latest uploaded Excel file.
        """
        # Wipe the table
        self.session.query(CalendarEvent).delete()
        self.session.flush()

        if not items:
            return 0

        objs = [CalendarEvent(**item) for item in items]
        self.session.add_all(objs)
        self.session.flush()
        return len(objs)