"""Reusable current-date provider.

This module centralises access to "the current date/time" so that the
project never calls ``datetime.now()`` directly in business logic. Using
a single provider makes date-dependent behaviour deterministic and easy
to test (the reference date can be injected or overridden).

Task 6 — Relative Date Understanding — uses this provider so the engine
can resolve relative Arabic date expressions against a configurable
reference date instead of the wall clock.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional


class CurrentDateProvider:
    """Provides the current date (and optionally time).

    The provider can be constructed with:

    - a fixed ``reference_date`` (``datetime.date``) — useful for tests
    - a fixed ``reference_datetime`` (``datetime.datetime``)
    - nothing — in which case it falls back to ``datetime.now()``

    Business code should depend on an instance of this class rather than
    calling ``datetime.now()`` directly, so behaviour stays deterministic.
    """

    def __init__(
        self,
        reference_date: Optional[date] = None,
        reference_datetime: Optional[datetime] = None,
    ) -> None:
        self._reference_date = reference_date
        self._reference_datetime = reference_datetime

    def today(self) -> date:
        """Return the configured reference date, or today's date."""
        if self._reference_date is not None:
            return self._reference_date
        if self._reference_datetime is not None:
            return self._reference_datetime.date()
        return datetime.now().date()

    def now(self) -> datetime:
        """Return the configured reference datetime, or now."""
        if self._reference_datetime is not None:
            return self._reference_datetime
        if self._reference_date is not None:
            # Promote a bare date to midnight datetime.
            return datetime.combine(self._reference_date, datetime.min.time())
        return datetime.now()

    def offset_days(self, days: int) -> date:
        """Return the reference date shifted by ``days``."""
        return self.today() + timedelta(days=days)


# A module-level default provider that reads the real wall clock.
# Tests can construct their own ``CurrentDateProvider`` with a fixed
# reference date and pass it explicitly to services.
default_provider = CurrentDateProvider()