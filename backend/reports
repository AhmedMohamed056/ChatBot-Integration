"""Reports Backend service (Task 11).

This module is an **internal aggregation layer only**.  It collects
data that is already stored in the database and returns it as plain
dicts/lists for the Admin Dashboard API.

Rules (enforced by design):
- No AI / Gemini / LLM calls.
- No analytics, trending, or "most common" computations.
- No charts, graphs, dashboard widgets, or UI.
- No exports (Excel / PDF / CSV).
- No search, filters, pagination options, or sorting options.
- No new database tables.
- No duplicated SQL – every read goes through an existing repository
  or an existing helper in :mod:`database`.
- Never raises.  When no data exists, returns ``0`` or ``[]``.

The FastAPI endpoints in :mod:`main` are thin wrappers around the
functions defined here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

from db.base import get_session as get_campaign_session
from db.repositories.calendar_event_repository import CalendarEventRepository
from db.repositories.campaign_repository import CampaignRepository
from db.repositories.campaign_visitor_repository import CampaignVisitorRepository
from db.repositories.visitor_question_repository import VisitorQuestionRepository
from database import get_setting, get_uploaded_file_record
from prayer_time_engine import get_today_prayers


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_count(repo) -> int:
    """Return ``repo.count()`` or ``0`` on any failure."""
    try:
        return int(repo.count())
    except Exception:
        return 0


def _today_prayer_count() -> int:
    """Return the number of prayers scheduled for today (never raises)."""
    try:
        prayers = get_today_prayers()
        return len(prayers) if prayers else 0
    except Exception:
        return 0


def _question_to_dict(question) -> dict[str, Any]:
    """Serialise a :class:`VisitorQuestion` for the questions report."""
    return {
        "visitor_name": question.visitor_name,
        "campaign_name": question.campaign_name,
        "phone_number": question.phone_number,
        "question": question.question,
        "detected_language": question.detected_language,
        "message_timestamp": (
            question.message_timestamp.isoformat()
            if question.message_timestamp is not None
            else None
        ),
    }


def _import_timestamp_for_setting(setting_key: str) -> str:
    """Return the upload timestamp for the file referenced by a setting.

    Reads the configured file path from ``system_settings`` (e.g.
    ``campaign_file`` / ``calendar_file``), extracts the filename, and
    looks up its ``uploaded_at`` value in the existing ``uploaded_files``
    table.  Returns an empty string when nothing is configured or found.
    """
    try:
        file_path = get_setting(setting_key, "")
        if not file_path:
            return ""
        filename = Path(file_path).name
        record = get_uploaded_file_record(filename)
        if not record:
            return ""
        return record.get("uploaded_at", "") or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Public report methods
# ---------------------------------------------------------------------------


def get_summary_report() -> dict[str, Any]:
    """Return the aggregate summary report.

    Shape::

        {
            "campaigns": {"total_campaigns": int, "total_visitors": int},
            "calendar":  {"total_events": int},
            "questions": {"total_questions": int},
            "prayers":   {"today_count": int},
        }

    Never raises; missing data resolves to ``0``.
    """
    total_campaigns = 0
    total_visitors = 0
    total_events = 0
    total_questions = 0

    try:
        with get_campaign_session() as session:
            total_campaigns = _safe_count(CampaignRepository(session))
            total_visitors = _safe_count(CampaignVisitorRepository(session))
            total_events = _safe_count(CalendarEventRepository(session))
            total_questions = _safe_count(VisitorQuestionRepository(session))
    except Exception:
        # Keep whatever counts were collected; default to 0.
        pass

    return {
        "campaigns": {
            "total_campaigns": total_campaigns,
            "total_visitors": total_visitors,
        },
        "calendar": {
            "total_events": total_events,
        },
        "questions": {
            "total_questions": total_questions,
        },
        "prayers": {
            "today_count": _today_prayer_count(),
        },
    }


def get_campaign_report() -> List[dict[str, Any]]:
    """Return every campaign with its visitor count.

    Shape: ``[{"campaign_name": str, "visitor_count": int}, ...]``.
    Returns ``[]`` when there is no data.
    """
    try:
        with get_campaign_session() as session:
            repo = CampaignVisitorRepository(session)
            return repo.count_by_campaign()
    except Exception:
        return []


def get_questions_report(limit: int = 50) -> List[dict[str, Any]]:
    """Return the latest visitor questions, newest first.

    Each item contains: ``visitor_name``, ``campaign_name``,
    ``phone_number``, ``question``, ``detected_language`` and
    ``message_timestamp``.  Maximum *limit* records (default 50).
    Returns ``[]`` when there are no questions.
    """
    try:
        with get_campaign_session() as session:
            repo = VisitorQuestionRepository(session)
            questions = repo.list_latest_questions(limit=limit)
            return [_question_to_dict(q) for q in questions]
    except Exception:
        return []


def get_calendar_report() -> dict[str, Any]:
    """Return the total number of calendar events.

    Shape: ``{"total_events": int}``.  Returns ``0`` when empty.
    """
    try:
        with get_campaign_session() as session:
            repo = CalendarEventRepository(session)
            return {"total_events": _safe_count(repo)}
    except Exception:
        return {"total_events": 0}


def get_imports_report() -> dict[str, Any]:
    """Return the last import timestamps for campaign & calendar files.

    The timestamps are read from the existing ``uploaded_files``
    information, keyed by the configured ``campaign_file`` /
    ``calendar_file`` settings.  No new import-history table is used.

    Shape: ``{"campaign_import": str, "calendar_import": str}`` where
    each value is an ISO timestamp string or ``""`` when unknown.
    """
    return {
        "campaign_import": _import_timestamp_for_setting("campaign_file"),
        "calendar_import": _import_timestamp_for_setting("calendar_file"),
    }