"""Campaign update extraction service.

This module ONLY extracts campaign update information from an admin
WhatsApp message. It does NOT:

- Update the database
- Call Gemini / any LLM
- Interpret dates (relative or absolute)
- Interpret prayer names
- Calculate weekdays
- Modify campaigns

It returns a :class:`CampaignUpdateExtraction` describing the detected
operation (create / update / cancel), the campaign name, and the raw
date/time text fragments exactly as written in the message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass
class CampaignUpdateExtraction:
    """Structured extraction result for a campaign update message."""

    campaign_name: str
    operation: str  # one of: create | update | cancel
    date_text: Optional[str] = None
    time_text: Optional[str] = None
    raw_message: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        # Keep response clean: drop empty optional fields
        if not data.get("date_text"):
            data.pop("date_text", None)
        if not data.get("time_text"):
            data.pop("time_text", None)
        return data


# ---------------------------------------------------------------------------
# Operation detection
# ---------------------------------------------------------------------------

# Cancel operation keywords
_CANCEL_PATTERNS = [
    r"\bإلغاء\b",
    r"\bإلغاء\s+حملة\b",
    r"\bالغاء\b",
    r"\bألغ\b",
    r"\bإلغ\b",
    r"\bcancel\b",
]

# Create operation keywords
_CREATE_PATTERNS = [
    r"\bأضف\s+حملة\b",
    r"\bاضافة\s+حملة\b",
    r"\bإضافة\s+حملة\b",
    r"\bحملة\s+جديدة\b",
    r"\bأنشئ\s+حملة\b",
    r"\bانشئ\s+حملة\b",
    r"\bcreate\b",
]

# Update operation keywords (default when a campaign + date/time present)
_UPDATE_PATTERNS = [
    r"\bتعديل\b",
    r"\bتحديث\b",
    r"\bتغيير\b",
    r"\bupdate\b",
]


def _match_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _detect_operation(text: str) -> Optional[str]:
    """Detect the intended operation from the message text.

    Order matters: cancel and create are explicit keywords, while update
    is the implicit fallback when a campaign name and date/time are
    present but no explicit keyword is found.
    """
    if _match_any(_CANCEL_PATTERNS, text):
        return "cancel"
    if _match_any(_CREATE_PATTERNS, text):
        return "create"
    if _match_any(_UPDATE_PATTERNS, text):
        return "update"
    return None


# ---------------------------------------------------------------------------
# Campaign name extraction
# ---------------------------------------------------------------------------

# The phrase "حملة <name>" — capture the name following the word حملة.
# Stop at common operation / date / time keywords.
_CAMPAIGN_PREFIX = r"حملة\s+(?P<name>.+?)"

# Trailing tokens that mark the end of a campaign name.
_NAME_STOPPERS = (
    "الجمعة|السبت|الأحد|الاثنين|الإثنين|الثلاثاء|الأربعاء|الخميس|"
    "القادمة|القادم|القادمة|"
    "غدا|غداً|بعد\s+غد|بعدغد|اليوم|الليلة|هذا|هذه|الأسبوع|الشهر|"
    "الساعة|ساعة|صباحا|صباحاً|مساء|مساءً|فجرا|ظهرا|عصرا|مغرب|عشاء|"
    "بعد|قبل|عند|تقريبا|تقريباً|"
    "إلغاء|الغاء|تعديل|تحديث|تغيير|أضف|اضافة|إضافة|جديدة"
)

_NAME_STOPPER_RE = re.compile(
    rf"{_CAMPAIGN_PREFIX}(?:\s+(?:{_NAME_STOPPERS})(?:\s|$|،|,|:|؛|;))",
    re.IGNORECASE,
)


def _extract_campaign_name(text: str) -> Optional[str]:
    """Extract the campaign name following the word 'حملة'.

    The name extends until a date/time/operation keyword is encountered.
    Returns None if no 'حملة' token is present.
    """
    if "حملة" not in text:
        return None

    # Try to capture name up to a stopper keyword.
    m = _NAME_STOPPER_RE.search(text)
    if m:
        name = m.group("name").strip()
        # Strip trailing punctuation
        name = re.sub(r"[،,؛;:\s]+$", "", name).strip()
        if name:
            return f"حملة {name}"

    # Fallback: take everything after the last 'حملة' occurrence.
    idx = text.rfind("حملة")
    if idx == -1:
        return None
    rest = text[idx + len("حملة"):].strip()
    rest = re.sub(r"[،,؛;:\s]+$", "", rest).strip()
    if not rest:
        return None
    return f"حملة {rest}"


# ---------------------------------------------------------------------------
# Date / time text extraction (raw, no interpretation)
# ---------------------------------------------------------------------------

# Relative / weekday date expressions — captured verbatim.
_DATE_EXPRESSIONS = [
    r"الجمعة\s+القادمة",
    r"الخميس\s+القادم",
    r"السبت\s+القادم",
    r"الأحد\s+القادم",
    r"الاثنين\s+القادم",
    r"الإثنين\s+القادم",
    r"الثلاثاء\s+القادمة",
    r"الأربعاء\s+القادمة",
    r"الأسبوع\s+القادم",
    r"الأسبوع\s+القادمة",
    r"بعد\s+غد",
    r"بعدغد",
    r"غداً",
    r"غدا",
    r"اليوم",
    r"الليلة",
    r"الجمعة",
    r"السبت",
    r"الأحد",
    r"الاثنين",
    r"الإثنين",
    r"الثلاثاء",
    r"الأربعاء",
    r"الخميس",
]

_DATE_RE = re.compile("|".join(_DATE_EXPRESSIONS))


def _extract_date_text(text: str) -> Optional[str]:
    """Return the first matching date expression verbatim, or None."""
    m = _DATE_RE.search(text)
    return m.group(0) if m else None


# Time expressions — captured verbatim. Includes prayer-based times.
_TIME_EXPRESSIONS = [
    r"\d{1,2}(?::\d{2})?\s*(?:صباحاً|صباحا|مساءً|مساء|فجراً|فجرا|ظهراً|ظهرا|عصراً|عصرا|م)",
    r"بعد\s+المغرب",
    r"بعد\s+العصر",
    r"بعد\s+الفجر",
    r"بعد\s+الظهر",
    r"بعد\s+العشاء",
    r"قبل\s+المغرب",
    r"قبل\s+العصر",
    r"قبل\s+الفجر",
    r"قبل\s+الظهر",
    r"قبل\s+العشاء",
    r"وقت\s+المغرب",
    r"وقت\s+العصر",
    r"وقت\s+الفجر",
    r"وقت\s+الظهر",
    r"وقت\s+العشاء",
    r"المغرب",
    r"العصر",
    r"الفجر",
    r"الظهر",
    r"العشاء",
]

_TIME_RE = re.compile("|".join(_TIME_EXPRESSIONS))


def _extract_time_text(text: str) -> Optional[str]:
    """Return the first matching time expression verbatim, or None."""
    m = _TIME_RE.search(text)
    return m.group(0) if m else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_campaign_update(message: str) -> Optional[CampaignUpdateExtraction]:
    """Extract campaign update information from an admin WhatsApp message.

    Returns a :class:`CampaignUpdateExtraction` instance, or ``None`` when:
    - the message is empty
    - no campaign name can be found
    - no operation can be determined

    This function performs extraction only. It never interprets dates,
    times, or prayer names, and never touches the database or any LLM.
    """
    if not message or not isinstance(message, str):
        return None

    text = message.strip()
    if not text:
        return None

    try:
        campaign_name = _extract_campaign_name(text)
        if not campaign_name:
            return None

        operation = _detect_operation(text)

        # Implicit update: if a campaign + date/time are present but no
        # explicit operation keyword was matched, treat it as an update.
        date_text = _extract_date_text(text)
        time_text = _extract_time_text(text)
        if operation is None and (date_text or time_text):
            operation = "update"

        if operation is None:
            return None

        return CampaignUpdateExtraction(
            campaign_name=campaign_name,
            operation=operation,
            date_text=date_text,
            time_text=time_text,
            raw_message=message,
        )
    except Exception:
        # Never crash — extraction is best-effort.
        return None