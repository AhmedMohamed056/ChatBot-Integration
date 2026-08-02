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
                supervisor=context.get("supervisor"),
                campaign_knowledge=context.get("campaign_knowledge"),
                calendar=context.get("calendar") or [],
                today_prayers=context.get("today_prayers") or [],
                next_prayer=context.get("next_prayer"),
                current_date=context.get("current_date"),
                current_day=context.get("current_day"),
                language=context.get("language") or "ar",
                raw_message=context.get("raw_message") or "",
                conversation_memory=context.get("conversation_memory"),
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


def _campaign_knowledge_section(ctx: AIContext) -> list[str]:
    """Build the CAMPAIGN KNOWLEDGE section for supervisor-taught facts."""
    knowledge = ctx.campaign_knowledge
    if not isinstance(knowledge, list) or not knowledge:
        return []

    lines = ["CAMPAIGN KNOWLEDGE"]
    lines.append("Stable facts taught by the campaign supervisor. Use these with highest priority.")
    lines.append("These are authoritative facts about the campaign that should override any other information.")

    for i, fact in enumerate(knowledge, 1):
        if isinstance(fact, str) and fact.strip():
            lines.append(f"Fact {i}: {fact.strip()}")

    return lines

def _supervisor_section(ctx: AIContext) -> list[str]:
    """Build the SUPERVISOR section for authorized WhatsApp supervisors."""
    supervisor = ctx.supervisor
    if not isinstance(supervisor, dict):
        return []

    # Extract supervisor fields
    name = _as_str(supervisor.get("supervisor_name"))
    phone = _as_str(supervisor.get("phone"))
    campaign_id = _as_str(supervisor.get("campaign_id"))
    campaign_name = _as_str(supervisor.get("campaign_name"))
    campaign_status = _as_str(supervisor.get("campaign_status"))
    version = supervisor.get("current_campaign_version")
    conversation_state = _as_str(supervisor.get("conversation_state"))
    pending_draft = supervisor.get("pending_draft")

    # Only include section if we have meaningful supervisor info
    if not name and not phone:
        return []

    lines = ["SUPERVISOR"]
    lines.append("You are speaking with an authorized campaign supervisor.")
    if name:
        lines.append(f"Supervisor Name: {name}")
    if phone:
        lines.append(f"Phone: {phone}")
    if campaign_id:
        lines.append(f"Campaign ID: {campaign_id}")
    if campaign_name:
        lines.append(f"Campaign Name: {campaign_name}")
    if campaign_status:
        lines.append(f"Campaign Status: {campaign_status}")
    if version is not None:
        lines.append(f"Current Campaign Version: {version}")
    if conversation_state:
        lines.append(f"Conversation State: {conversation_state}")
    if pending_draft:
        lines.append(f"Pending Draft: {pending_draft}")

    return lines


def _campaign_section(ctx: AIContext) -> list[str]:
    """Build the CURRENT CAMPAIGN section with full campaign details.
    
    This section is only included when a supervisor is present and has
    an associated campaign. It provides complete campaign information
    including the full description without any truncation.
    """
    # Only show current campaign section for supervisors
    if not ctx.supervisor:
        return []
    
    campaign = ctx.campaign
    if not isinstance(campaign, dict):
        return []
    
    # Extract campaign fields
    name = _as_str(campaign.get("campaign_name")) or _as_str(campaign.get("name"))
    description = _as_str(campaign.get("description"))
    notes = _as_str(campaign.get("notes"))
    operation = _as_str(campaign.get("operation"))
    location = _as_str(campaign.get("location")) or _as_str(campaign.get("notes"))
    campaign_type = _as_str(campaign.get("campaign_type"))
    status = _as_str(campaign.get("status"))
    start_date = _as_str(campaign.get("start_date"))
    end_date = _as_str(campaign.get("end_date"))
    
    # Only include section if we have at least a campaign name
    if not name:
        return []
    
    lines = ["CURRENT CAMPAIGN"]
    lines.append(f"Campaign Name: {name}")
    
    # Description is included in full without any truncation
    if description:
        lines.append(f"Description: {description}")
        lines.append("(كامل بدون أي Truncation)")
    
    if notes:
        lines.append(f"Notes: {notes}")
    
    if operation:
        lines.append(f"Operation: {operation}")
    
    if location:
        lines.append(f"Location: {location}")
    
    if campaign_type:
        lines.append(f"Campaign Type: {campaign_type}")
    
    if status:
        lines.append(f"Status: {status}")
    
    if start_date:
        lines.append(f"Start Date: {start_date}")
    
    if end_date:
        lines.append(f"End Date: {end_date}")
    
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

def _conversation_memory_section(ctx: AIContext) -> list[str]:
    """Build the CONVERSATION MEMORY section for maintaining context."""
    memory = ctx.conversation_memory
    if not isinstance(memory, dict):
        return []

    # Extract memory fields
    current_topic = _as_str(memory.get("current_topic"))
    last_user_intent = _as_str(memory.get("last_user_intent"))
    last_assistant_action = _as_str(memory.get("last_assistant_action"))
    pending_context = memory.get("pending_context")
    conversation_summary = _as_str(memory.get("conversation_summary"))
    last_edited_field = _as_str(memory.get("last_edited_field"))
    recent_messages = memory.get("recent_messages")
    pending_draft = memory.get("pending_draft")

    # Only include section if we have meaningful memory
    if not any([current_topic, last_user_intent, last_assistant_action, pending_context,
                conversation_summary, last_edited_field, recent_messages, pending_draft]):
        return []

    lines = ["CONVERSATION MEMORY"]
    lines.append("Use this memory to understand references like 'اجعله أقصر', 'غيرها', 'احذف الفقرة الثانية', 'it', 'this', 'No', 'Cancel'")

    if current_topic:
        lines.append(f"Current Topic: {current_topic}")
    if last_user_intent:
        lines.append(f"Last User Intent: {last_user_intent}")
    if last_assistant_action:
        lines.append(f"Last Assistant Action: {last_assistant_action}")
    if pending_context and isinstance(pending_context, dict):
        field = _as_str(pending_context.get("field"))
        old_value = _as_str(pending_context.get("old_value"))
        new_value = _as_str(pending_context.get("new_value"))
        if field:
            lines.append(f"Pending Context - Field: {field}")
            if old_value:
                lines.append(f"Pending Context - Old Value: {old_value[:100]}")
            if new_value:
                lines.append(f"Pending Context - New Value: {new_value[:100]}")
    if conversation_summary:
        lines.append(f"Conversation Summary: {conversation_summary}")
    if last_edited_field:
        lines.append(f"Last Edited Field: {last_edited_field}")
    if pending_draft:
        lines.append(f"Pending Draft: {pending_draft}")

    # Format recent messages
    if isinstance(recent_messages, list) and recent_messages:
        lines.append("Recent Messages:")
        for msg in recent_messages[-5:]:  # Last 5 messages
            if isinstance(msg, dict):
                direction = msg.get("direction", "unknown")
                text = _as_str(msg.get("text", ""))
                if text:
                    lines.append(f"  [{direction}] {text[:100]}")  # Limit message length

    return lines


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

    # Campaign Knowledge section has HIGHEST priority - supervisor-taught facts
    knowledge_lines = _campaign_knowledge_section(ctx)
    if knowledge_lines:
        sections.append(knowledge_lines)

    # Supervisor section takes priority over visitor for supervisors
    supervisor_lines = _supervisor_section(ctx)
    if supervisor_lines:
        sections.append(supervisor_lines)

    # Current Campaign section - full campaign details
    campaign_lines = _campaign_section(ctx)
    if campaign_lines:
        sections.append(campaign_lines)

    visitor_lines = _visitor_section(ctx)
    if visitor_lines:
        sections.append(visitor_lines)

    calendar_lines = _calendar_section(ctx)
    if calendar_lines:
        sections.append(calendar_lines)

    prayer_lines = _prayer_section(ctx)
    if prayer_lines:
        sections.append(prayer_lines)

    # Conversation memory section for maintaining context across messages
    memory_lines = _conversation_memory_section(ctx)
    if memory_lines:
        sections.append(memory_lines)

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