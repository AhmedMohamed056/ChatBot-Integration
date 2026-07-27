"""Prompt Builder — Task 12.

This service is **purely a text assembler**.  It takes a static System
Prompt (stored in Settings) and an :class:`AIContext` (built by Task 9)
and combines them into a single final prompt string that will later be
sent to Gemini.

It deliberately does **NOT**:

- Call Gemini / any LLM
- Detect visitors
- Resolve dates
- Search the calendar
- Read the database
- Call any repository
- Call WhatsApp
- Duplicate any business logic that already lives in the engines

Everything it needs must already exist inside the supplied
:class:`AIContext`.  The builder only formats what it is given.

Validation rules
----------------

- Never crash.  Any malformed / missing input is silently ignored.
- Missing or empty sections are omitted entirely (no ``None`` / ``null``
  / ``[]`` / ``{}`` placeholders are ever printed).
- The User Message section is always included.
- Output is deterministic and stable for the same input.
- No duplicated blank lines.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from ai_context_builder import AIContext


# ---------------------------------------------------------------------------
# Internal helpers (formatting only — no business logic)
# ---------------------------------------------------------------------------

_SECTION_SEPARATOR = "------------------------"
_BLOCK_SEPARATOR = "========================"


def _is_blank(value: Any) -> bool:
    """Return True when *value* should be considered absent.

    Treats ``None``, empty strings, and empty collections as blank.
    Never raises.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _as_str(value: Any) -> str:
    """Safely coerce *value* to a stripped string.  Never raises."""
    try:
        if value is None:
            return ""
        text = str(value)
        return text.strip()
    except Exception:
        return ""


def _coerce_context(context: Any) -> AIContext:
    """Return an :class:`AIContext` from *context*.

    Accepts an :class:`AIContext` instance or a plain dict (the shape
    produced by ``AIContext.to_dict()``).  On any failure a fresh empty
    :class:`AIContext` is returned so the builder never crashes.
    """
    if isinstance(context, AIContext):
        return context
    if isinstance(context, dict):
        try:
            return AIContext(
                visitor=context.get("visitor"),
                campaign=context.get("campaign"),
                calendar=context.get("calendar") or [],
                today_prayers=context.get("today_prayers") or [],
                next_prayer=context.get("next_prayer"),
                current_date=context.get("current_date"),
                current_day=context.get("current_day"),
                language=context.get("language") or "ar",
                raw_message=context.get("raw_message") or "",
            )
        except Exception:
            return AIContext()
    return AIContext()


def _format_prayer(prayer: Any) -> str:
    """Format a single prayer dict as ``Name: time``.  Never raises."""
    if not isinstance(prayer, dict):
        return ""
    name = _as_str(prayer.get("prayer_name")) or _as_str(prayer.get("name"))
    time = _as_str(prayer.get("event_time")) or _as_str(prayer.get("time"))
    if name and time:
        return f"{name}: {time}"
    if name:
        return name
    if time:
        return time
    return ""


def _format_event(event: Any) -> str:
    """Format a single calendar event dict as ``title (time)``.  Never raises."""
    if not isinstance(event, dict):
        return ""
    title = _as_str(event.get("event_title")) or _as_str(event.get("title"))
    time = _as_str(event.get("event_time")) or _as_str(event.get("time"))
    if title and time:
        return f"{title} ({time})"
    if title:
        return title
    if time:
        return time
    return ""


def _join_lines(lines: list[str]) -> str:
    """Join non-empty *lines* with single newlines (no duplicated blanks)."""
    cleaned = [ln for ln in lines if ln is not None and ln != ""]
    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Section builders (each returns a list of lines, or [] when omitted)
# ---------------------------------------------------------------------------


def _date_section(ctx: AIContext) -> list[str]:
    current_date = _as_str(ctx.current_date)
    current_day = _as_str(ctx.current_day)
    if not current_date and not current_day:
        return []
    lines = ["CURRENT DATE / DAY"]
    if current_date:
        lines.append(f"Current Date: {current_date}")
    if current_day:
        lines.append(f"Current Day: {current_day}")
    return lines


def _language_section(ctx: AIContext) -> list[str]:
    language = _as_str(ctx.language)
    if not language:
        return []
    return ["LANGUAGE", f"Language: {language}"]


def _visitor_section(ctx: AIContext) -> list[str]:
    visitor = ctx.visitor
    if not isinstance(visitor, dict):
        return []
    name = _as_str(visitor.get("visitor_name")) or _as_str(visitor.get("name"))
    phone = _as_str(visitor.get("phone_number")) or _as_str(visitor.get("phone"))
    campaign = _as_str(visitor.get("campaign_name")) or _as_str(visitor.get("campaign"))
    if not name and not phone and not campaign:
        return []
    lines = ["VISITOR"]
    if name:
        lines.append(f"Name: {name}")
    if phone:
        lines.append(f"Phone: {phone}")
    if campaign:
        lines.append(f"Campaign: {campaign}")
    return lines


def _calendar_section(ctx: AIContext) -> list[str]:
    events = ctx.calendar
    if not isinstance(events, list) or not events:
        return []
    formatted = []
    for event in events:
        line = _format_event(event)
        if line:
            formatted.append(f"- {line}")
    if not formatted:
        return []
    return ["TODAY'S CALENDAR", *formatted]


def _prayer_section(ctx: AIContext) -> list[str]:
    today = ctx.today_prayers
    next_prayer = ctx.next_prayer

    prayer_lines: list[str] = []
    if isinstance(today, list) and today:
        for prayer in today:
            line = _format_prayer(prayer)
            if line:
                prayer_lines.append(f"- {line}")

    next_line = ""
    if isinstance(next_prayer, dict):
        next_line = _format_prayer(next_prayer)

    if not prayer_lines and not next_line:
        return []

    lines = ["TODAY'S PRAYERS"]
    lines.extend(prayer_lines)
    if next_line:
        lines.append(f"Next Prayer: {next_line}")
    return lines


def _user_message_section(ctx: AIContext) -> list[str]:
    """The user message section is always included (even if empty)."""
    message = _as_str(ctx.raw_message)
    return ["VISITOR MESSAGE", message]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_prompt(system_prompt: str, context: Union[AIContext, dict, None]) -> str:
    """Combine a static System Prompt with an :class:`AIContext`.

    Parameters
    ----------
    system_prompt:
        The static system prompt text (stored in Settings).  May be empty.
    context:
        An :class:`AIContext` instance or a dict with the same shape as
        ``AIContext.to_dict()``.  May be ``None``.

    Returns
    -------
    str
        A single, deterministic, human-readable prompt string.  Never
        raises.  Missing sections are omitted entirely.
    """
    try:
        ctx = _coerce_context(context)
    except Exception:
        ctx = AIContext()

    # --- Build the ordered list of context sections ----------------------
    sections: list[list[str]] = []

    date_lines = _date_section(ctx)
    if date_lines:
        sections.append(date_lines)

    lang_lines = _language_section(ctx)
    if lang_lines:
        sections.append(lang_lines)

    visitor_lines = _visitor_section(ctx)
    if visitor_lines:
        sections.append(visitor_lines)

    calendar_lines = _calendar_section(ctx)
    if calendar_lines:
        sections.append(calendar_lines)

    prayer_lines = _prayer_section(ctx)
    if prayer_lines:
        sections.append(prayer_lines)

    # The user message section is always included.
    sections.append(_user_message_section(ctx))

    # --- Assemble the context block --------------------------------------
    context_block_parts: list[str] = []
    if sections:
        context_block_parts.append("CURRENT CONTEXT")
        for section in sections:
            context_block_parts.append(_join_lines(section))
            context_block_parts.append(_SECTION_SEPARATOR)
        # Drop the trailing separator line for a cleaner ending.
        if context_block_parts and context_block_parts[-1] == _SECTION_SEPARATOR:
            context_block_parts.pop()

    # --- Assemble the final prompt ---------------------------------------
    parts: list[str] = []

    sys_text = _as_str(system_prompt)
    if sys_text:
        parts.append(sys_text)
        parts.append(_BLOCK_SEPARATOR)

    if context_block_parts:
        parts.append(_join_lines(context_block_parts))
        parts.append(_BLOCK_SEPARATOR)

    parts.append("Answer the user according to the System Prompt above.")

    return _join_lines(parts)