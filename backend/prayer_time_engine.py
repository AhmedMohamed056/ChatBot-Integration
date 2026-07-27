"""Prayer Time Engine – expose prayer-time information.

Responsibilities
----------------
This engine is a **thin consumer** of the Calendar Engine.  It does **not**
read Excel, does **not** parse the calendar file, and does **not** duplicate
any repository or parsing code.  The Calendar Engine (``calendar_engine.py``)
remains the single source of truth for every calendar event.

Prayer times are simply calendar events whose title matches one of the
canonical prayers.  Because different uploads may use different naming styles
("الفجر", "صلاة الفجر", "Fajr", ...), a configurable mapping layer resolves
any of those variants to a single canonical prayer name without modifying the
Calendar Engine.

The engine exposes:

- :func:`get_today_prayers`  – all of today's prayers
- :func:`get_prayer`         – a single prayer by name
- :func:`get_next_prayer`    – the next upcoming prayer today
- :func:`get_current_prayer` – the current/active prayer today

Nothing more.  No AI, no Gemini, no context building, no WhatsApp logic, no
reports, no campaign logic, no relative dates, no calendar import / parsing.
"""

from __future__ import annotations

from datetime import datetime, time as dt_time
from typing import Any, Optional

import calendar_engine
from current_date_provider import CurrentDateProvider, default_provider


# ---------------------------------------------------------------------------
# Canonical prayer names + configurable mapping layer
# ---------------------------------------------------------------------------
#
# The canonical names are the Arabic names required by the task.  The mapping
# table lists, for each canonical prayer, every variant title (Arabic and
# English) that may appear in the Calendar event titles.  Matching is
# case-insensitive and whitespace-trimmed, so "fajr", "FAJR", "الفجر ",
# "صلاة الفجر" all resolve to the same canonical prayer.
#
# To support a new naming style, just add it to the appropriate list below –
# no change to the Calendar Engine is ever required.

PRAYER_FAJR = "الفجر"
PRAYER_SUNRISE = "الشروق"
PRAYER_DHUHR = "الظهر"
PRAYER_ASR = "العصر"
PRAYER_MAGHRIB = "المغرب"
PRAYER_ISHA = "العشاء"

#: Ordered canonical prayer names (the order is the daily chronological order
#: and is used for next/current prayer resolution).
CANONICAL_PRAYERS: list[str] = [
    PRAYER_FAJR,
    PRAYER_SUNRISE,
    PRAYER_DHUHR,
    PRAYER_ASR,
    PRAYER_MAGHRIB,
    PRAYER_ISHA,
]

#: Configurable mapping: canonical prayer -> list of variant titles that should
#: resolve to it.  Extend these lists to support additional naming styles.
PRAYER_NAME_ALIASES: dict[str, list[str]] = {
    PRAYER_FAJR: ["الفجر", "صلاة الفجر", "فجر", "fajr", "fajr prayer"],
    PRAYER_SUNRISE: ["الشروق", "شروق", "sunrise", "shuruq", "ishraq"],
    PRAYER_DHUHR: ["الظهر", "صلاة الظهر", "ظهر", "الظهر", "dhuhr", "zuhr", "noon"],
    PRAYER_ASR: ["العصر", "صلاة العصر", "عصر", "asr", "asr prayer"],
    PRAYER_MAGHRIB: ["المغرب", "صلاة المغرب", "مغرب", "maghrib", "maghrib prayer", "sunset"],
    PRAYER_ISHA: ["العشاء", "صلاة العشاء", "عشاء", "isha", "isha prayer"],
}


def _build_alias_lookup() -> dict[str, str]:
    """Build a reverse lookup: normalised alias -> canonical prayer name."""
    lookup: dict[str, str] = {}
    for canonical, aliases in PRAYER_NAME_ALIASES.items():
        # The canonical name itself is always a valid alias.
        for alias in [canonical, *aliases]:
            key = _normalise(alias)
            if key:
                lookup[key] = canonical
    return lookup


def _normalise(text: str) -> str:
    """Normalise a title/alias for case-insensitive comparison.

    Strips surrounding whitespace, lowercases (for English variants), and
    collapses internal whitespace.  Arabic letters are kept as-is; Arabic
    diacritics (tashkeel) are removed so "الفجرِ" still matches "الفجر".
    """
    if not text:
        return ""
    value = str(text).strip().lower()
    # Remove Arabic diacritics (harakat) if present.
    value = value.replace("\u064b", "").replace("\u064c", "").replace("\u064d", "")
    value = value.replace("\u064e", "").replace("\u064f", "").replace("\u0650", "")
    value = value.replace("\u0651", "").replace("\u0652", "")
    # Collapse whitespace.
    return " ".join(value.split())


#: Reverse lookup built once at import time.  Use :func:`reload_aliases` to
#: rebuild it if :data:`PRAYER_NAME_ALIASES` is modified at runtime.
_ALIAS_LOOKUP: dict[str, str] = _build_alias_lookup()


def reload_aliases() -> None:
    """Rebuild the alias lookup table.

    Call this after mutating :data:`PRAYER_NAME_ALIASES` at runtime so the
    change is picked up by subsequent resolutions.
    """
    global _ALIAS_LOOKUP
    _ALIAS_LOOKUP = _build_alias_lookup()


def resolve_canonical_name(title: str) -> Optional[str]:
    """Resolve a Calendar event title to a canonical prayer name.

    Returns ``None`` if the title does not match any known prayer.  The
    comparison is case-insensitive, whitespace-trimmed, and diacritic-agnostic
    so multiple naming styles resolve to the same canonical prayer.
    """
    if not title:
        return None
    key = _normalise(title)
    if not key:
        return None
    return _ALIAS_LOOKUP.get(key)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _parse_time(value: str) -> Optional[dt_time]:
    """Best-effort parse of a prayer time string into a ``datetime.time``.

    Accepts common formats: "HH:MM", "HH:MM:SS", "H:MM AM/PM".  Returns
    ``None`` for free-form text like "After Maghrib" (those prayers are kept
    but excluded from next/current chronological resolution).
    """
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p", "%I:%M%p"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def _today_iso(provider: CurrentDateProvider) -> str:
    """Return today's date as an ISO ``YYYY-MM-DD`` string."""
    return provider.today().isoformat()


# ---------------------------------------------------------------------------
# Internal: fetch + classify today's events
# ---------------------------------------------------------------------------


def _classify_event(event: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Classify a raw calendar event dict as a prayer (or ``None``).

    Adds the canonical ``prayer_name`` field while preserving every original
    field from the Calendar Engine.
    """
    canonical = resolve_canonical_name(event.get("event_title", ""))
    if canonical is None:
        return None
    enriched = dict(event)
    enriched["prayer_name"] = canonical
    enriched["time_obj"] = _parse_time(event.get("event_time", ""))
    return enriched


def _today_prayers_internal(provider: CurrentDateProvider) -> list[dict[str, Any]]:
    """Return today's classified prayers (internal helper).

    Never raises – on any error it returns an empty list.
    """
    try:
        today = _today_iso(provider)
        events = calendar_engine.search_by_date(today)
    except Exception as exc:  # noqa: BLE001
        print(f"prayer_time_engine: failed to load today's events: {exc}")
        return []

    prayers: list[dict[str, Any]] = []
    for event in events:
        classified = _classify_event(event)
        if classified is not None:
            prayers.append(classified)

    # Sort by canonical daily order, then by parsed time when available.
    order_index = {name: idx for idx, name in enumerate(CANONICAL_PRAYERS)}

    def sort_key(p: dict[str, Any]) -> tuple[int, int]:
        canonical = p.get("prayer_name", "")
        canonical_order = order_index.get(canonical, len(CANONICAL_PRAYERS))
        time_obj = p.get("time_obj")
        # Events with a parseable time sort by minutes-since-midnight; events
        # without a parseable time are pushed after, preserving insertion order
        # via a stable secondary key of 0.
        minutes = time_obj.hour * 60 + time_obj.minute if time_obj else 24 * 60
        return (canonical_order, minutes)

    prayers.sort(key=sort_key)
    return prayers


def _strip_internal_fields(prayer: dict[str, Any]) -> dict[str, Any]:
    """Remove internal helper fields before returning to callers/API."""
    return {k: v for k, v in prayer.items() if k not in {"time_obj"}}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_today_prayers(provider: CurrentDateProvider = default_provider) -> list[dict[str, Any]]:
    """Return all of today's prayers.

    Each item contains the original Calendar event fields plus a
    ``prayer_name`` field holding the canonical prayer name.  Returns an empty
    list if today's calendar has no prayers.  Never raises.
    """
    return [_strip_internal_fields(p) for p in _today_prayers_internal(provider)]


def get_prayer(
    prayer_name: str,
    provider: CurrentDateProvider = default_provider,
) -> Optional[dict[str, Any]]:
    """Return today's prayer matching *prayer_name* (case-insensitive).

    The name may be any alias registered in :data:`PRAYER_NAME_ALIASES`
    (e.g. "الفجر", "صلاة الفجر", "Fajr").  Returns ``None`` if the name does
    not resolve to a canonical prayer or if today has no such prayer.
    """
    canonical = resolve_canonical_name(prayer_name)
    if canonical is None:
        return None
    for prayer in _today_prayers_internal(provider):
        if prayer.get("prayer_name") == canonical:
            return _strip_internal_fields(prayer)
    return None


def get_next_prayer(
    provider: CurrentDateProvider = default_provider,
) -> Optional[dict[str, Any]]:
    """Return the next upcoming prayer today.

    "Next" is the first prayer whose time is strictly after the current time.
    Prayers without a parseable time are ignored for this computation.  If no
    prayer remains today, returns ``None``.  Never raises.
    """
    prayers = _today_prayers_internal(provider)
    now = provider.now().time()
    for prayer in prayers:
        time_obj = prayer.get("time_obj")
        if time_obj is not None and time_obj > now:
            return _strip_internal_fields(prayer)
    return None


def get_current_prayer(
    provider: CurrentDateProvider = default_provider,
) -> Optional[dict[str, Any]]:
    """Return the current/active prayer.

    The "current" prayer is the most recent prayer whose time is at or before
    the current time.  Prayers without a parseable time are ignored.  Returns
    ``None`` if no prayer has started yet today.  Never raises.
    """
    prayers = _today_prayers_internal(provider)
    now = provider.now().time()
    current: Optional[dict[str, Any]] = None
    for prayer in prayers:
        time_obj = prayer.get("time_obj")
        if time_obj is not None and time_obj <= now:
            current = prayer
        else:
            break
    return _strip_internal_fields(current) if current else None