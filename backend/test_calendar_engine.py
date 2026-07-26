"""Example tests for the Calendar Engine (Task 7).

Run with:

    cd backend
    python test_calendar_engine.py

These tests build a temporary in-memory database and a temporary Excel
file so they exercise the real parser + repository without touching the
production database or requiring a manually-uploaded file.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Make the backend directory importable when running this file directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openpyxl import Workbook

import db.base as db_base
from db import init_engine, init_db, get_session
from db.repositories.calendar_event_repository import CalendarEventRepository

import calendar_engine as engine


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _setup_temp_db() -> None:
    """Point the SQLAlchemy layer at a fresh in-memory database."""
    init_engine(":memory:")
    init_db()


def _make_excel(path: Path, rows: list[list], headers: list[str]) -> None:
    """Write a small .xlsx file with *headers* then *rows*."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(str(path))


def _set_calendar_setting(file_path: str) -> None:
    """Patch the settings getter used by the engine to return *file_path*."""
    original = engine.get_setting

    def fake_get_setting(key, default=""):
        if key == "calendar_file":
            return file_path
        return original(key, default)

    engine.get_setting = fake_get_setting  # type: ignore[assignment]


def _restore_calendar_setting() -> None:
    """Restore the real settings getter."""
    from database import get_setting as real_get_setting

    engine.get_setting = real_get_setting  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_and_search() -> None:
    print("== Load + search ==")
    _setup_temp_db()

    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "calendar.xlsx"
        _make_excel(
            xlsx,
            [
                ["2026-08-01", "Saturday", "Opening Ceremony", "18:00"],
                ["2026-08-02", "Sunday", "Workshop", "10:00"],
                ["2026-08-02", "Sunday", "Lecture", "After Maghrib"],
            ],
            headers=["Date", "Day", "Event", "Time"],
        )
        _set_calendar_setting(str(xlsx))

        result = engine.load_calendar()
        assert result["ok"] is True
        assert result["events"] == 3, result
        print(f"OK  loaded {result['events']} events")

        # search by date
        by_date = engine.search_by_date("2026-08-02")
        assert len(by_date) == 2, by_date
        print(f"OK  search_by_date('2026-08-02') -> {len(by_date)} events")

        # search by day (case-insensitive)
        by_day = engine.search_by_day("sunday")
        assert len(by_day) == 2, by_day
        print(f"OK  search_by_day('sunday') -> {len(by_day)} events")

        # list all
        all_events = engine.list_all_events()
        assert len(all_events) == 3, all_events
        print(f"OK  list_all_events() -> {len(all_events)} events")

        _restore_calendar_setting()


def test_case_insensitive_headers_and_extra_columns() -> None:
    print("\n== Case-insensitive headers + extra columns ignored ==")
    _setup_temp_db()

    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "calendar.xlsx"
        # Headers with mixed case + an extra "Notes" column that must be ignored.
        _make_excel(
            xlsx,
            [["2026-08-03", "Monday", "Team Meeting", "09:00", "Bring notes"]],
            headers=["DATE", " Day ", "EVENT", "TIME", "Notes"],
        )
        _set_calendar_setting(str(xlsx))

        result = engine.load_calendar()
        assert result["events"] == 1, result

        events = engine.list_all_events()
        assert events[0]["event_title"] == "Team Meeting"
        assert events[0]["day_name"] == "Day".strip() or events[0]["day_name"] == "Monday"
        print("OK  extra column ignored, headers matched case-insensitively")

        _restore_calendar_setting()


def test_skip_invalid_rows() -> None:
    print("\n== Skip invalid / empty rows ==")
    _setup_temp_db()

    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "calendar.xlsx"
        _make_excel(
            xlsx,
            [
                ["2026-08-04", "Tuesday", "Valid Event", "12:00"],
                ["", "", "", ""],                 # empty row -> skip
                ["2026-08-05", "Wednesday", "", "13:00"],  # no title -> skip
                ["2026-08-06", "Thursday", "Another Valid", "14:00"],
            ],
            headers=["Date", "Day", "Event", "Time"],
        )
        _set_calendar_setting(str(xlsx))

        result = engine.load_calendar()
        assert result["events"] == 2, result
        assert result["skipped"] == 2, result
        print(f"OK  stored {result['events']}, skipped {result['skipped']}")

        _restore_calendar_setting()


def test_missing_columns_rejected() -> None:
    print("\n== Missing columns rejected ==")
    _setup_temp_db()

    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "calendar.xlsx"
        _make_excel(
            xlsx,
            [["2026-08-01", "Saturday", "18:00"]],
            headers=["Date", "Day", "Time"],  # missing "Event"
        )
        _set_calendar_setting(str(xlsx))

        try:
            engine.load_calendar()
            raised = False
        except engine.CalendarMissingColumnsError:
            raised = True

        assert raised is True, "Expected CalendarMissingColumnsError"
        print("OK  missing 'Event' column -> CalendarMissingColumnsError")

        _restore_calendar_setting()


def test_missing_file_rejected() -> None:
    print("\n== Missing file rejected ==")
    _setup_temp_db()
    _set_calendar_setting("/nonexistent/path/calendar.xlsx")

    try:
        engine.load_calendar()
        raised = False
    except engine.CalendarFileNotFoundError:
        raised = True

    assert raised is True, "Expected CalendarFileNotFoundError"
    print("OK  nonexistent file -> CalendarFileNotFoundError")

    _restore_calendar_setting()


def test_not_configured_rejected() -> None:
    print("\n== Not configured rejected ==")
    _setup_temp_db()
    _set_calendar_setting("")

    try:
        engine.load_calendar()
        raised = False
    except engine.CalendarFileNotConfiguredError:
        raised = True

    assert raised is True, "Expected CalendarFileNotConfiguredError"
    print("OK  empty setting -> CalendarFileNotConfiguredError")

    _restore_calendar_setting()


def test_search_never_crashes() -> None:
    print("\n== Search APIs never crash ==")
    _setup_temp_db()

    # Empty table -> empty lists, no exceptions.
    assert engine.search_by_date("2026-08-01") == []
    assert engine.search_by_day("Saturday") == []
    assert engine.list_all_events() == []
    print("OK  empty table -> empty lists")


def main() -> None:
    test_load_and_search()
    test_case_insensitive_headers_and_extra_columns()
    test_skip_invalid_rows()
    test_missing_columns_rejected()
    test_missing_file_rejected()
    test_not_configured_rejected()
    test_search_never_crashes()
    print("\nAll calendar engine tests passed.")


if __name__ == "__main__":
    main()