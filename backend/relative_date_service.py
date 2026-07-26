"""Relative Date Engine — Task 6.

This module converts relative Arabic date expressions into actual
calendar dates. It is intentionally narrow and self-contained:

- Input  : ``date_text`` (a relative Arabic date expression)
- Output : :class:`RelativeDateResult` (original text + resolved date)

It does NOT:

- Implement a Calendar Engine
- Implement a Prayer Time Engine
- Call any AI / Gemini / LLM
- Build any context
- Update any database
- Touch WhatsApp, reports, or visitor questions

The engine resolves against a *reference date* (provided by
:class:`current_date_provider.CurrentDateProvider`) so behaviour is
deterministic and testable. It never calls ``datetime.now()`` directly.

Supported expressions (and only these):

    اليوم
    غدا / غداً / بكرة
    بعد غد / بعدغد
    أول الأسبوع
    نهاية الأسبوع
    هذا الأسبوع
    الأسبوع القادم / الأسبوع المقبل
    الأحد / الإثنين / الثلاثاء / الأربعاء / الخميس / الجمعة / السبت
    <weekday> القادم / القادمة  (e.g. الجمعة القادمة)

Week start is Saturday (common in the Arabic/Islamic calendar context).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from current_date_provider import CurrentDateProvider


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass
class RelativeDateResult:
    """Result of resolving a relative date expression."""

    original_text: str
    resolved_date: Optional[str]  # ISO YYYY-MM-DD when success=True
    success: bool

    def to_dict(self) -> dict:
        return {
            "original_text": self.original_text,
            "resolved_date": self.resolved_date,
            "success": self.success,
        }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Python weekday numbers: Monday=0 ... Sunday=6
# Arabic week starts on Saturday (weekday 5).
WEEK_START_WEEKDAY = 5  # Saturday

# Arabic weekday name -> Python weekday number
ARABIC_WEEKDAYS = {
    "الأحد": 6,
    "الاحد": 6,
    "الإثنين": 0,
    "الاثنين": 0,
    "الثلاثاء": 1,
    "الثلاثه": 1,
    "الأربعاء": 2,
    "الاربعاء": 2,
    "الخميس": 3,
    "الجمعة": 4,
    "الجمعه": 4,
    "السبت": 5,
}

# "Next" qualifiers that may follow a weekday name.
NEXT_QUALIFIERS = ("القادم", "القادمة", "القادمه", "المقبل", "المقبلة", "المقادمة")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Light normalisation: strip, collapse spaces."""
    text = text.strip()
    # Collapse internal whitespace (e.g. "بعد  غد" -> "بعد غد")
    text = re.sub(r"\s+", " ", text)
    return text


def _start_of_week(ref: date) -> date:
    """Return the Saturday that starts the week containing ``ref``."""
    days_back = (ref.weekday() - WEEK_START_WEEKDAY) % 7
    return ref - timedelta(days=days_back)


def _next_weekday(ref: date, weekday: int) -> date:
    """Next occurrence of ``weekday`` strictly after ``ref`` (>=1 day)."""
    days_ahead = (weekday - ref.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return ref + timedelta(days=days_ahead)


def _this_weekday(ref: date, weekday: int) -> date:
    """The occurrence of ``weekday`` in the current week (Sat..Fri).

    If that day has already passed this week, return the same weekday
    next week (so a bare weekday name always points forward).
    """
    week_start = _start_of_week(ref)
    target = week_start + timedelta(days=(weekday - WEEK_START_WEEKDAY) % 7)
    if target < ref:
        target += timedelta(days=7)
    return target


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_relative_date(
    date_text: str,
    reference_date: Optional[date] = None,
    provider: Optional[CurrentDateProvider] = None,
) -> RelativeDateResult:
    """Resolve a relative Arabic date expression to a calendar date.

    Parameters
    ----------
    date_text:
        The relative date expression (e.g. ``"الجمعة القادمة"``).
    reference_date:
        Optional explicit reference date (``datetime.date``). When
        provided this takes priority over ``provider``.
    provider:
        Optional :class:`CurrentDateProvider`. Ignored when
        ``reference_date`` is given. Defaults to the wall-clock provider.

    Returns
    -------
    RelativeDateResult
        ``success=False`` (never an exception) for unknown expressions.
    """
    original = date_text
    if not date_text or not isinstance(date_text, str):
        return RelativeDateResult(original_text=original, resolved_date=None, success=False)

    text = _normalize(date_text)
    if not text:
        return RelativeDateResult(original_text=original, resolved_date=None, success=False)

    # Determine the reference date.
    if reference_date is not None:
        ref = reference_date
    elif provider is not None:
        ref = provider.today()
    else:
        ref = CurrentDateProvider().today()

    try:
        resolved = _resolve(text, ref)
    except Exception:
        # Never raise — unknown/invalid expressions yield success=False.
        resolved = None

    if resolved is None:
        return RelativeDateResult(original_text=original, resolved_date=None, success=False)

    return RelativeDateResult(
        original_text=original,
        resolved_date=resolved.isoformat(),
        success=True,
    )


def _resolve(text: str, ref: date) -> Optional[date]:
    """Internal resolver. Returns a ``date`` or ``None`` if unsupported."""

    # --- Simple day offsets -----------------------------------------------
    if text == "اليوم":
        return ref
    if text in ("غدا", "غداً", "بكرة", "بكره"):
        return ref + timedelta(days=1)
    if text in ("بعد غد", "بعدغد"):
        return ref + timedelta(days=2)

    # --- Week-relative expressions ----------------------------------------
    if text in ("أول الأسبوع", "اول الاسبوع", "بداية الأسبوع", "بدايه الاسبوع"):
        # Start of the *next* week (next Saturday).
        return _start_of_week(ref) + timedelta(days=7)

    if text in ("نهاية الأسبوع", "نهايه الاسبوع"):
        # End of the current week = Friday of this week.
        week_start = _start_of_week(ref)
        return week_start + timedelta(days=6)

    if text in ("هذا الأسبوع", "هذا الاسبوع"):
        # Start of the current week.
        return _start_of_week(ref)

    if text in ("الأسبوع القادم", "الاسبوع القادم", "الأسبوع المقبل", "الاسبوع المقبل"):
        # Start of next week (next Saturday).
        return _start_of_week(ref) + timedelta(days=7)

    # --- Weekday expressions ----------------------------------------------
    # "الجمعة القادمة" / "الجمعة القادم" etc.
    next_match = re.match(
        r"^(?P<day>" + "|".join(re.escape(d) for d in ARABIC_WEEKDAYS) + r")"
        r"\s+(?P<qualifier>" + "|".join(NEXT_QUALIFIERS) + r")$",
        text,
    )
    if next_match:
        weekday = ARABIC_WEEKDAYS[next_match.group("day")]
        return _next_weekday(ref, weekday)

    # Bare weekday name -> this week's occurrence (forward-looking).
    if text in ARABIC_WEEKDAYS:
        return _this_weekday(ref, ARABIC_WEEKDAYS[text])

    # Unsupported expression.
    return None