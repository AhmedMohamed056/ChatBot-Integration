"""Repository for :class:`CalendarDay` entities."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from db.models import CalendarDay
from db.repositories.base import BaseRepository


class CalendarRepository(BaseRepository[CalendarDay]):
    """CRUD + domain-specific queries for calendar days.

    Each row contains prayer times, Hijri date, Ramadan / Eid flags,
    and Islamic / public events – there is **no** separate prayer-times
    table.
    """

    model = CalendarDay

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Read – domain-specific lookups
    # ------------------------------------------------------------------

    def get_by_date(self, gregorian_date: date) -> Optional[CalendarDay]:
        """Return the calendar day for a specific Gregorian date."""
        stmt = select(CalendarDay).where(CalendarDay.gregorian_date == gregorian_date)
        return self.session.execute(stmt).scalars().first()

    def get_by_hijri_date(self, hijri_date: str) -> Optional[CalendarDay]:
        """Return the calendar day for a specific Hijri date string."""
        stmt = select(CalendarDay).where(CalendarDay.hijri_date == hijri_date)
        return self.session.execute(stmt).scalars().first()

    def list_in_range(
        self,
        start_date: date,
        end_date: date,
    ) -> List[CalendarDay]:
        """Return all calendar days in ``[start_date, end_date]`` inclusive."""
        stmt = (
            select(CalendarDay)
            .where(CalendarDay.gregorian_date >= start_date)
            .where(CalendarDay.gregorian_date <= end_date)
            .order_by(CalendarDay.gregorian_date)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_ramadan_days(self) -> List[CalendarDay]:
        """Return all Ramadan days, ordered by Gregorian date."""
        stmt = (
            select(CalendarDay)
            .where(CalendarDay.is_ramadan == True)  # noqa: E712
            .order_by(CalendarDay.gregorian_date)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_eid_days(self) -> List[CalendarDay]:
        """Return all Eid days, ordered by Gregorian date."""
        stmt = (
            select(CalendarDay)
            .where(CalendarDay.is_eid == True)  # noqa: E712
            .order_by(CalendarDay.gregorian_date)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_with_islamic_events(self) -> List[CalendarDay]:
        """Return all days that have an Islamic event."""
        stmt = (
            select(CalendarDay)
            .where(CalendarDay.islamic_event.is_not(None))
            .where(CalendarDay.islamic_event != "")
            .order_by(CalendarDay.gregorian_date)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_with_public_events(self) -> List[CalendarDay]:
        """Return all days that have a public event."""
        stmt = (
            select(CalendarDay)
            .where(CalendarDay.public_event.is_not(None))
            .where(CalendarDay.public_event != "")
            .order_by(CalendarDay.gregorian_date)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_ramadan_day(self, ramadan_day: int) -> Optional[CalendarDay]:
        """Return the calendar day for a specific Ramadan day number."""
        stmt = select(CalendarDay).where(CalendarDay.ramadan_day == ramadan_day)
        return self.session.execute(stmt).scalars().first()

    # ------------------------------------------------------------------
    # Create / upsert
    # ------------------------------------------------------------------

    def upsert(self, data: dict[str, Any]) -> CalendarDay:
        """Insert or update a calendar day by ``gregorian_date``.

        If a row with the same ``gregorian_date`` already exists, it is
        updated in place; otherwise a new row is inserted.
        """
        gregorian_date = data.get("gregorian_date")
        if gregorian_date is None:
            raise ValueError("gregorian_date is required")

        existing = self.get_by_date(gregorian_date)
        if existing is not None:
            return self.update(existing, data)
        return self.create(data)

    def bulk_upsert(self, items: list[dict[str, Any]]) -> List[CalendarDay]:
        """Upsert multiple calendar days.

        More efficient than calling :meth:`upsert` in a loop because it
        pre-fetches existing dates in a single query.
        """
        if not items:
            return []

        dates = [item["gregorian_date"] for item in items if item.get("gregorian_date")]
        existing_map: dict[date, CalendarDay] = {}
        if dates:
            stmt = select(CalendarDay).where(
                CalendarDay.gregorian_date.in_(dates)
            )
            for row in self.session.execute(stmt).scalars().all():
                existing_map[row.gregorian_date] = row

        result: List[CalendarDay] = []
        for item in items:
            gregorian_date = item.get("gregorian_date")
            if gregorian_date is None:
                raise ValueError("gregorian_date is required")
            existing = existing_map.get(gregorian_date)
            if existing is not None:
                result.append(self.update(existing, item))
            else:
                result.append(self.create(item))
        return result

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_by_date(self, gregorian_date: date) -> bool:
        """Delete a calendar day by its Gregorian date."""
        entity = self.get_by_date(gregorian_date)
        if entity is None:
            return False
        return self.delete(entity)

    def delete_in_range(self, start_date: date, end_date: date) -> int:
        """Delete all calendar days in ``[start_date, end_date]``.

        Returns the number of deleted rows.
        """
        stmt = (
            select(CalendarDay)
            .where(CalendarDay.gregorian_date >= start_date)
            .where(CalendarDay.gregorian_date <= end_date)
        )
        rows = list(self.session.execute(stmt).scalars().all())
        for row in rows:
            self.session.delete(row)
        self.session.flush()
        return len(rows)