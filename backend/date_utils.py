"""Date, time, Hijri calendar, and relative date resolution."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from database import get_setting

ARABIC_DAYS = {
    "السبت": 5,
    "الأحد": 6,
    "الاحد": 6,
    "الاثنين": 0,
    "الإثنين": 0,
    "الثلاثاء": 1,
    "الاربعاء": 2,
    "الأربعاء": 2,
    "الخميس": 3,
    "الجمعة": 4,
    "saturday": 5,
    "sunday": 6,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
}

HIJRI_MONTHS = {
    "muharram": 1,
    "safar": 2,
    "rabi al-awwal": 3,
    "rabi al-thani": 4,
    "jumada al-awwal": 5,
    "jumada al-thani": 6,
    "rajab": 7,
    "shaaban": 8,
    "ramadan": 9,
    "shawwal": 10,
    "dhu al-qaadah": 11,
    "dhu al-hijjah": 12,
    "محرم": 1,
    "صفر": 2,
    "ربيع الأول": 3,
    "ربيع الآخر": 4,
    "ربيع الثاني": 4,
    "جمادى الأولى": 5,
    "جمادى الآخرة": 6,
    "جمادى الثانية": 6,
    "رجب": 7,
    "شعبان": 8,
    "رمضان": 9,
    "شوال": 10,
    "ذو القعدة": 11,
    "ذو الحجة": 12,
}


def get_timezone() -> ZoneInfo:
    tz_name = get_setting("timezone", "Asia/Riyadh")
    for candidate in (tz_name, "Asia/Riyadh", "UTC"):
        try:
            return ZoneInfo(candidate)
        except Exception:
            continue
    return ZoneInfo("UTC")


def gregorian_to_hijri(dt: datetime) -> tuple[int, int, int]:
    try:
        from hijri_converter import Gregorian

        hijri = Gregorian(dt.year, dt.month, dt.day).to_hijri()
        return hijri.year, hijri.month, hijri.day
    except Exception:
        return 0, 0, 0


def hijri_to_gregorian(year: int, month: int, day: int) -> str | None:
    """Convert a Hijri date to a Gregorian ISO date string (YYYY-MM-DD)."""
    try:
        from hijri_converter import Hijri

        gregorian = Hijri(year, month, day).to_gregorian()
        return gregorian.isoformat()
    except Exception:
        return None


def load_calendar_file() -> dict:
    calendar_path = get_setting("calendar_file", "")
    if not calendar_path:
        return {}

    path = Path(calendar_path)
    if not path.exists():
        return {}

    try:
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        return {"raw_text": path.read_text(encoding="utf-8")}
    except Exception:
        return {}


def get_calendar_context() -> str:
    calendar = load_calendar_file()
    if not calendar:
        return "No custom Islamic calendar file uploaded."

    if "raw_text" in calendar:
        return calendar["raw_text"][:8000]

    return json.dumps(calendar, ensure_ascii=False)[:8000]


def get_current_datetime_context() -> dict[str, str]:
    tz = get_timezone()
    now = datetime.now(tz)
    hy, hm, hd = gregorian_to_hijri(now)
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    arabic_days = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

    return {
        "gregorian_date": now.strftime("%d %B %Y"),
        "hijri_date": f"{hd} / {hm} / {hy}" if hy else "Unavailable",
        "day_name_en": day_names[now.weekday()],
        "day_name_ar": arabic_days[now.weekday()],
        "time": now.strftime("%H:%M"),
        "timezone": str(tz),
        "iso_date": now.date().isoformat(),
    }


def format_datetime_context_block() -> str:
    ctx = get_current_datetime_context()
    calendar = get_calendar_context()
    return (
        f"Current Gregorian Date: {ctx['gregorian_date']}\n"
        f"Current Hijri Date: {ctx['hijri_date']}\n"
        f"Current Day: {ctx['day_name_ar']} ({ctx['day_name_en']})\n"
        f"Current Time: {ctx['time']}\n"
        f"Timezone: {ctx['timezone']}\n\n"
        f"Custom Islamic Calendar (authoritative for Hijri dates, prayer times, visits, and religious events):\n"
        f"{calendar}"
    )


def _next_weekday(from_date: datetime.date, weekday: int) -> datetime.date:
    days_ahead = (weekday - from_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return from_date + timedelta(days=days_ahead)


def resolve_relative_expression(text: str, base: datetime | None = None) -> str | None:
    """Best-effort relative date resolution for campaign updates."""
    tz = get_timezone()
    now = base or datetime.now(tz)
    today = now.date()
    lowered = text.lower()

    direct_map = {
        "today": today,
        "اليوم": today,
        "tomorrow": today + timedelta(days=1),
        "غدا": today + timedelta(days=1),
        "غداً": today + timedelta(days=1),
        "after tomorrow": today + timedelta(days=2),
        "بعد غد": today + timedelta(days=2),
        "بعد غداً": today + timedelta(days=2),
        "yesterday": today - timedelta(days=1),
        "أمس": today - timedelta(days=1),
        "tonight": today,
        "الليلة": today,
        "this evening": today,
        "هذا المساء": today,
        "tomorrow morning": today + timedelta(days=1),
        "صباح الغد": today + timedelta(days=1),
        "صباح غد": today + timedelta(days=1),
    }

    for phrase, resolved in direct_map.items():
        if phrase in lowered:
            return resolved.isoformat()

    for day_name, weekday in ARABIC_DAYS.items():
        if day_name in lowered:
            if "next" in lowered or "القادم" in lowered or "القادمة" in lowered:
                target = _next_weekday(today, weekday)
                if target <= today:
                    target += timedelta(days=7)
                return target.isoformat()
            target = _next_weekday(today - timedelta(days=1), weekday)
            if "this week" in lowered or "هذا الأسبوع" in lowered:
                return target.isoformat()
            return target.isoformat()

    if "this week" in lowered or "هذا الأسبوع" in lowered:
        return today.isoformat()
    if "next week" in lowered or "الأسبوع القادم" in lowered:
        return (today + timedelta(days=7)).isoformat()

    month_match = re.search(
        r"(beginning|start|بداية|بدايه|start of)\s+(.+)",
        lowered,
    )
    if month_match:
        month_key = month_match.group(2).strip()
        for name, month_num in HIJRI_MONTHS.items():
            if name in month_key:
                hy, _, _ = gregorian_to_hijri(now)
                gregorian = hijri_to_gregorian(hy, month_num, 1)
                if gregorian:
                    return gregorian

    month_match = re.search(
        r"(end|نهاية|نهايه|end of)\s+(.+)",
        lowered,
    )
    if month_match:
        month_key = month_match.group(2).strip()
        for name, month_num in HIJRI_MONTHS.items():
            if name in month_key:
                hy, _, _ = gregorian_to_hijri(now)
                gregorian = hijri_to_gregorian(hy, month_num, 29)
                if gregorian:
                    return gregorian

    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso_match:
        return iso_match.group(1)

    return None


def is_expired(expires_at: str | None, reference: datetime | None = None) -> bool:
    if not expires_at:
        return False
    tz = get_timezone()
    ref = (reference or datetime.now(tz)).date()
    try:
        expiry = datetime.fromisoformat(expires_at).date()
    except ValueError:
        try:
            expiry = datetime.strptime(expires_at, "%Y-%m-%d").date()
        except ValueError:
            return False
    return expiry < ref
