"""Calendar Engine – load and query the uploaded Calendar Excel file.

Responsibilities
----------------
- Read the Calendar Excel file path from system settings
  (``calendar_file``) – never hardcode paths.
- Validate the file (existence, extension, required columns).
- Parse every row into a Calendar Event.
- Store the events in the ``calendar_events`` table.
- Provide search APIs (by date, by day, list all).

This engine is **independent** of FastAPI.  The API layer in
``main.py`` only calls the functions exposed here.  It does **not**
implement prayer times, relative-date logic, AI, Gemini, context
building, reports, campaign updates, WhatsApp logic, or visitor
questions.

The parser is built to be tolerant of the real Excel layout: column
matching is case-insensitive and whitespace-trimmed, the four expected
columns (``Date``, ``Day``, ``Event``, ``Time``) are required, and any
extra columns are safely ignored.
"""

from __future__ import annotations

from datetime import datetime, date as date_type
from pathlib import Path
from typing import Any, Optional

from openpyxl import load_workbook

from database import get_setting
from db.base import get_session
from db.repositories.calendar_event_repository import CalendarEventRepository


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Supported file extensions for the Calendar Excel file.
SUPPORTED_EXTENSIONS = {".xlsx", ".xls"}

#: Required columns (normalised to lower-case, trimmed).  Matching is
#: case-insensitive so the real Excel header names are honoured regardless
#: of capitalisation.
REQUIRED_COLUMNS = {"date", "day", "event", "time"}

#: Mapping from the normalised required-column name to the model field.
COLUMN_TO_FIELD = {
    "date": "event_date",
    "day": "day_name",
    "event": "event_title",
    "time": "event_time",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CalendarEngineError(Exception):
    """Base error for the Calendar Engine."""


class CalendarFileNotConfiguredError(CalendarEngineError):
    """Raised when no calendar file path is stored in settings."""


class CalendarFileNotFoundError(CalendarEngineError):
    """Raised when the configured calendar file does not exist on disk."""


class CalendarFileUnsupportedError(CalendarEngineError):
    """Raised when the calendar file has an unsupported extension."""


class CalendarMissingColumnsError(CalendarEngineError):
    """Raised when one or more required columns are missing."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_calendar_path() -> Path:
    """Return the configured Calendar Excel file path.

    Raises
    ------
    CalendarFileNotConfiguredError
        If no path is stored in settings.
    """
    file_path_str = get_setting("calendar_file", "")
    if not file_path_str:
        raise CalendarFileNotConfiguredError(
            "Calendar file not uploaded. Please upload it in Settings first."
        )
    return Path(file_path_str)


def _validate_file(path: Path) -> None:
    """Validate that *path* exists and has a supported extension.

    Raises
    ------
    CalendarFileNotFoundError
        If the file does not exist.
    CalendarFileUnsupportedError
        If the extension is not .xlsx / .xls.
    """
    if not path.exists():
        raise CalendarFileNotFoundError(f"Calendar Excel file not found at: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise CalendarFileUnsupportedError(
            f"Unsupported calendar file type '{suffix}'. Supported: XLSX, XLS."
        )


def _normalise_header(cell: Any) -> str:
    """Normalise a header cell to a lower-case trimmed string."""
    if cell is None:
        return ""
    return str(cell).strip().lower()


def _find_required_headers(header_row: list[Any]) -> dict[str, int]:
    """Map each required column name to its index in *header_row*.

    Returns
    -------
    dict[str, int]
        e.g. ``{"date": 0, "day": 1, "event": 2, "time": 3}``.

    Raises
    ------
    CalendarMissingColumnsError
        If any required column is missing.
    """
    normalised: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        col = _normalise_header(cell)
        if col and col not in normalised:
            normalised[col] = idx

    missing = REQUIRED_COLUMNS - set(normalised.keys())
    if missing:
        raise CalendarMissingColumnsError(
            "Missing required columns: " + ", ".join(sorted(missing))
        )

    return {col: normalised[col] for col in REQUIRED_COLUMNS}


def _cell_to_str(value: Any) -> str:
    """Convert an Excel cell value to a clean string.

    - ``None`` becomes ``""``.
    - ``datetime`` / ``date`` are formatted as ISO strings so the date
      and time columns keep a stable representation.
    - Everything else is stringified and stripped.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date_type):
        return value.isoformat()
    return str(value).strip()


def _row_to_event(row: tuple[Any, ...], col_map: dict[str, int]) -> Optional[dict[str, Any]]:
    """Convert a single data row into an event dict.

    Returns ``None`` for empty / invalid rows (so the caller can skip
    them without crashing).
    """
    try:
        event = {
            COLUMN_TO_FIELD[col]: _cell_to_str(row[col_map[col]])
            for col in REQUIRED_COLUMNS
        }
    except (IndexError, Exception):
        return None

    # Reject empty rows – every field blank means the row is empty.
    if not any(event.values()):
        return None

    # An event must at least have a title; otherwise it is meaningless.
    if not event["event_title"]:
        return None

    return event


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_calendar() -> dict[str, Any]:
    """Load the uploaded Calendar Excel file into the database.

    The table is fully replaced on every import so it always mirrors the
    latest uploaded file.  Invalid rows are skipped; the engine never
    crashes.

    Returns
    -------
    dict
        ``{"ok": True, "events": <int>, "skipped": <int>}``

    Raises
    ------
    CalendarFileNotConfiguredError
        If no calendar file is configured.
    CalendarFileNotFoundError
        If the file does not exist.
    CalendarFileUnsupportedError
        If the extension is unsupported.
    CalendarMissingColumnsError
        If required columns are missing.
    """
    print("Calendar import started...")

    path = _get_calendar_path()
    _validate_file(path)

    print(f"Reading Excel: {path.name}")

    # openpyxl handles .xlsx natively.  For .xls it will raise a clear
    # error; we surface it as an unsupported-type error.
    try:
        wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise CalendarFileUnsupportedError(
            f"Could not read calendar file '{path.name}': {exc}"
        ) from exc

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    # Close the workbook now so the file handle is released (important on
    # Windows where open handles block deletion of the uploaded file).
    wb.close()

    if not rows:
        raise CalendarMissingColumnsError("Calendar Excel file is empty.")

    header_row = list(rows[0])
    col_map = _find_required_headers(header_row)

    events: list[dict[str, Any]] = []
    skipped = 0

    for row in rows[1:]:
        event = _row_to_event(row, col_map)
        if event is None:
            skipped += 1
            continue
        events.append(event)

    # Persist – replace the whole table inside a single transaction.
    with get_session() as session:
        repo = CalendarEventRepository(session)
        repo.replace_all(events)

    print("Calendar import completed.")
    print(f"Events stored: {len(events)}")
    print(f"Skipped rows: {skipped}")

    return {"ok": True, "events": len(events), "skipped": skipped}


def search_by_date(event_date: str) -> list[dict[str, Any]]:
    """Return all calendar events matching *event_date* (case-insensitive).

    Returns an empty list if no events match or the table is empty.
    Never raises.
    """
    if not event_date:
        return []
    try:
        with get_session() as session:
            repo = CalendarEventRepository(session)
            rows = repo.list_by_date(event_date)
            return [repo.to_dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        print(f"search_by_date failed: {exc}")
        return []


def search_by_day(day_name: str) -> list[dict[str, Any]]:
    """Return all calendar events whose day name matches (case-insensitive).

    Returns an empty list if no events match or the table is empty.
    Never raises.
    """
    if not day_name:
        return []
    try:
        with get_session() as session:
            repo = CalendarEventRepository(session)
            rows = repo.list_by_day(day_name)
            return [repo.to_dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        print(f"search_by_day failed: {exc}")
        return []


def list_all_events() -> list[dict[str, Any]]:
    """Return every stored calendar event, ordered by date then id.

    Returns an empty list if the table is empty.  Never raises.
    """
    try:
        with get_session() as session:
            repo = CalendarEventRepository(session)
            rows = repo.list_all_ordered()
            return [repo.to_dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        print(f"list_all_events failed: {exc}")
        return []