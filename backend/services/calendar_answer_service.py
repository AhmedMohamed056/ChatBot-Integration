"""Deterministic calendar/prayer answers before generic RAG."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional

from calendar_engine import search_by_date as search_calendar_by_date
from calendar_engine import search_by_day as search_calendar_by_day
from current_date_provider import CurrentDateProvider
from prayer_time_engine import (
    get_next_prayer as get_next_prayer_engine,
    get_prayer as get_prayer_engine,
    get_today_prayers as get_today_prayers_engine,
)
from relative_date_service import resolve_relative_date


_HOLIDAY = re.compile(
    r"(?:holiday|إجاز|عطلة|عطله|is\s+.*holiday|عطلة\s+غدا|عطلة\s+اليوم|عطلة\s+بكرا)",
    re.IGNORECASE | re.UNICODE,
)
_FRIDAY = re.compile(
    r"(?:when\s+is\s+friday|يوم\s+الجمعة|متى\s+الجمعة|Friday\s*\?)",
    re.IGNORECASE | re.UNICODE,
)
_PRAYER = re.compile(
    r"(?:maghrib|fajr|dhuhr|asr|isha|المغرب|الفجر|الظهر|العصر|العشاء|صلاة|prayer|what\s+time)",
    re.IGNORECASE | re.UNICODE,
)
_TOMORROW = re.compile(r"(?:غدا|غداً|بكرا|بكرة|tomorrow|next\s+day)", re.IGNORECASE | re.UNICODE)


def try_calendar_answer(message: str, provider: Optional[CurrentDateProvider] = None) -> Optional[str]:
    """Return a direct answer from calendar/prayer data, or ``None`` to fall back to RAG."""
    text = (message or "").strip()
    if not text:
        return None
    prov = provider or CurrentDateProvider()

    if _PRAYER.search(text):
        for alias in ("maghrib", "المغرب", "fajr", "الفجر", "dhuhr", "الظهر", "asr", "العصر", "isha", "العشاء"):
            if alias.lower() in text.lower() or alias in text:
                prayer = get_prayer_engine(alias, prov)
                if prayer:
                    return (
                        f"وقت {prayer.get('name', alias)}: {prayer.get('time', '—')} "
                        f"({prov.today().isoformat()})"
                    )
        nxt = get_next_prayer_engine(prov)
        if nxt and ("next" in text.lower() or "التالي" in text):
            return f"الصلاة التالية: {nxt.get('name')} الساعة {nxt.get('time')}"
        today = get_today_prayers_engine(prov)
        if today and len(today) >= 1:
            lines = [f"{p.get('name')}: {p.get('time')}" for p in today[:6]]
            return "مواقيت الصلاة اليوم:\n" + "\n".join(lines)

    target_date = prov.today().isoformat()
    if _TOMORROW.search(text):
        target_date = (prov.today() + timedelta(days=1)).isoformat()

    rel = resolve_relative_date(text, provider=prov)
    if rel and getattr(rel, "success", False) and rel.resolved_date:
        target_date = rel.resolved_date

    if _FRIDAY.search(text):
        events = search_calendar_by_day("Friday") or search_calendar_by_day("الجمعة")
        if events:
            first = events[0]
            return f"Friday / الجمعة: {first.get('event_date', '')} — {first.get('event_title', '')}"

    if _HOLIDAY.search(text):
        events = search_calendar_by_date(target_date)
        for ev in events or []:
            title = str(ev.get("event_title") or ev.get("event") or "").lower()
            if any(k in title for k in ("holiday", "عطلة", "إجاز", "off")):
                return f"{target_date}: {ev.get('event_title', 'Holiday')}"
        return f"No holiday recorded in the calendar for {target_date}."

    if "?" in text or text.endswith("؟"):
        events = search_calendar_by_date(target_date)
        if events:
            lines = [
                f"- {e.get('event_title', e.get('event', ''))} "
                f"({e.get('event_time', e.get('time', ''))})"
                for e in events[:8]
            ]
            return f"Calendar for {target_date}:\n" + "\n".join(lines)

    return None
