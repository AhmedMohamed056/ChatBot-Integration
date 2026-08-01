"""AI Context Builder — Task 9.

This service is **only an orchestrator**.  It collects structured
information from the existing engines and returns it as a single,
model-agnostic :class:`AIContext` object.

It deliberately does **NOT**:

- Call Gemini / any LLM
- Generate any prompt or answer text
- Log visitors / questions
- Produce reports
- Send WhatsApp replies
- Update any database
- Import or parse the calendar file
- Duplicate any business logic that already lives in the engines

Every section of :class:`AIContext` is optional.  When an engine returns
nothing (or raises), the corresponding field is set to a safe empty
value (``None`` / ``[]``) so the builder **never crashes**.

The :class:`AIContext` contract is intentionally stable and decoupled
from any specific LLM.  Future Prompt Engineering, Gemini integration,
Reports, and WhatsApp Reply generation must all consume this same
object.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from campaign_detection_service import detect_visitor
from campaign_update_extraction_service import extract_campaign_update
from calendar_engine import search_by_date as search_calendar_by_date
from current_date_provider import CurrentDateProvider
from database import get_campaign_by_phone
from date_utils import get_current_datetime_context
from prayer_time_engine import (
    get_next_prayer as get_next_prayer_engine,
    get_today_prayers as get_today_prayers_engine,
)
from relative_date_service import resolve_relative_date
from services.supervisor_context_service import SupervisorContext
from services.conversation_memory_service import ConversationMemoryService, ConversationMemoryData
from services.campaign_knowledge_service import CampaignKnowledgeService


# ---------------------------------------------------------------------------
# Stable internal contract
# ---------------------------------------------------------------------------


@dataclass
class AIContext:
    """Structured, model-agnostic context built from the existing engines.

    Every field is optional and defaults to an empty value.  Consumers
    (future Prompt Engineering / Gemini / Reports / WhatsApp Reply) must
    treat every field as potentially empty.

    Fields
    ------
    visitor:
        The detected campaign visitor (``campaign_name``, ``visitor_name``,
        ``phone_number``) or ``None`` when the sender is unknown.
    campaign:
        The active campaign row for the sender's phone, or ``None``.
    supervisor:
        The supervisor context for authorized WhatsApp supervisors, or ``None``.
        Contains supervisor_name, phone, campaign_id, campaign_name, campaign_status,
        current_campaign_version, conversation_state, and pending_draft.
    campaign_knowledge:
        Campaign knowledge (supervisor-taught facts) for the campaign, or ``None``.
        Contains a list of stable facts that should be used with highest priority.
    calendar:
        Calendar events relevant to the message (resolved date / day),
        or ``[]`` when nothing matches.
    today_prayers:
        All of today's prayers (canonicalised), or ``[]``.
    next_prayer:
        The next upcoming prayer today, or ``None``.
    current_date:
        ISO ``YYYY-MM-DD`` of "now", or ``None``.
    current_day:
        Arabic day name for "now", or ``None``.
    language:
        Detected language of the raw message (``"ar"`` / ``"en"``), best
        effort.  Never ``None`` (defaults to ``"ar"``).
    raw_message:
        The original incoming message, verbatim.
    conversation_memory:
        Conversation memory containing current topic, pending draft, summary,
        last edited field, and recent messages. Or ``None`` when not available.
    """

    visitor: Optional[dict[str, Any]] = None
    campaign: Optional[dict[str, Any]] = None
    supervisor: Optional[dict[str, Any]] = None
    campaign_knowledge: Optional[list[str]] = None
    calendar: list[dict[str, Any]] = field(default_factory=list)
    today_prayers: list[dict[str, Any]] = field(default_factory=list)
    next_prayer: Optional[dict[str, Any]] = None
    current_date: Optional[str] = None
    current_day: Optional[str] = None
    language: str = "ar"
    raw_message: str = ""
    conversation_memory: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (stable, JSON-friendly contract)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers (no business logic — only orchestration glue)
# ---------------------------------------------------------------------------


def _detect_language(message: str) -> str:
    """Best-effort language detection: ``"ar"`` if Arabic letters are
    present, otherwise ``"en"``.  Never raises."""
    try:
        if not message:
            return "ar"
        for ch in message:
            if "\u0600" <= ch <= "\u06FF":
                return "ar"
        return "en"
    except Exception:
        return "ar"


def _safe_call(func, *args, **kwargs):
    """Invoke ``func`` and return its result, swallowing any exception.

    The context builder must never crash; on failure ``None`` is returned
    so the caller can fall back to an empty section.
    """
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        print(f"ai_context_builder: {getattr(func, '__name__', func)} failed: {exc}")
        return None


def _resolve_calendar_events(message: str, provider: CurrentDateProvider) -> list[dict[str, Any]]:
    """Return calendar events relevant to the message.

    Strategy (reuses existing engines only):

    1. If the message contains a relative date expression, resolve it via
       the Relative Date Engine and look the calendar up by that date.
    2. Otherwise fall back to today's events.

    Never raises — returns ``[]`` on any failure.
    """
    extraction = _safe_call(extract_campaign_update, message)
    date_text = None
    if extraction is not None:
        date_text = getattr(extraction, "date_text", None)

    resolved_date: Optional[str] = None
    if date_text:
        result = _safe_call(resolve_relative_date, date_text, provider=provider)
        if result is not None and getattr(result, "success", False):
            resolved_date = result.resolved_date

    if not resolved_date:
        resolved_date = provider.today().isoformat()

    events = _safe_call(search_calendar_by_date, resolved_date)
    return events if isinstance(events, list) else []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_context(
    message: str,
    phone: Optional[str] = None,
    provider: Optional[CurrentDateProvider] = None,
    supervisor: Optional[SupervisorContext] = None,
    conversation_id: Optional[int] = None,
) -> AIContext:
    """Build an :class:`AIContext` for an incoming WhatsApp message.

    Parameters
    ----------
    message:
        The incoming WhatsApp message text (verbatim).
    phone:
        Optional sender phone number.  When provided, the visitor and
        campaign sections are populated; when omitted they are ``None``.
    provider:
        Optional :class:`CurrentDateProvider` for deterministic dates
        (mainly useful in tests).  Defaults to the wall-clock provider.
    supervisor:
        Optional :class:`SupervisorContext` for authorized WhatsApp supervisors.
        When provided, the supervisor section is populated; when omitted it is ``None``.
    conversation_id:
        Optional conversation ID. When provided, conversation memory is loaded
        and included in the context.

    Returns
    -------
    AIContext
        A stable, model-agnostic context object.  Never raises.
    """
    raw_message = message if isinstance(message, str) else ""
    date_provider = provider or CurrentDateProvider()

    # --- Visitor + Campaign (only when a phone is available) ---------------
    visitor: Optional[dict[str, Any]] = None
    campaign: Optional[dict[str, Any]] = None
    campaign_knowledge: Optional[list[str]] = None
    if phone:
        visitor = _safe_call(detect_visitor, phone)
        campaign = _safe_call(get_campaign_by_phone, phone)
        # Load campaign knowledge for this campaign
        if campaign:
            campaign_knowledge = _load_campaign_knowledge(campaign.get("id"))
    elif supervisor is not None:
        # For supervisors, load knowledge for their campaign
        campaign_id = getattr(supervisor, 'campaign_id', None)
        if campaign_id:
            campaign_knowledge = _load_campaign_knowledge(campaign_id)

    # --- Supervisor context (for authorized supervisors) -------------------
    supervisor_dict: Optional[dict[str, Any]] = None
    if supervisor is not None:
        supervisor_dict = _safe_call(lambda: supervisor.to_dict())

    # --- Calendar (relative-date aware) ------------------------------------
    calendar_events = _resolve_calendar_events(raw_message, date_provider)

    # --- Prayer times ------------------------------------------------------
    today_prayers = _safe_call(get_today_prayers_engine, date_provider)
    if not isinstance(today_prayers, list):
        today_prayers = []

    next_prayer = _safe_call(get_next_prayer_engine, date_provider)

    # --- Current date / day ------------------------------------------------
    now_ctx = _safe_call(get_current_datetime_context) or {}
    current_date = now_ctx.get("iso_date") or date_provider.today().isoformat()
    current_day = now_ctx.get("day_name_ar")

    # --- Language ----------------------------------------------------------
    language = _detect_language(raw_message)

    # --- Conversation Memory ------------------------------------------------
    conversation_memory: Optional[dict[str, Any]] = None
    if conversation_id:
        conversation_memory = _load_conversation_memory(conversation_id)

    return AIContext(
        visitor=visitor,
        campaign=campaign,
        supervisor=supervisor_dict,
        campaign_knowledge=campaign_knowledge,
        calendar=calendar_events,
        today_prayers=today_prayers,
        next_prayer=next_prayer,
        current_date=current_date,
        current_day=current_day,
        language=language,
        raw_message=raw_message,
        conversation_memory=conversation_memory,
    )

def _load_conversation_memory(conversation_id: int) -> Optional[dict[str, Any]]:
    """Load conversation memory for a given conversation ID."""
    try:
        from db.base import get_session
        from services.conversation_memory_service import ConversationMemoryService

        with get_session() as session:
            memory_service = ConversationMemoryService(session)
            return memory_service.get_memory_for_prompt(conversation_id)
    except Exception as exc:
        print(f"ai_context_builder: Failed to load conversation memory: {exc}")
        return None

def _load_campaign_knowledge(campaign_id: int) -> Optional[list[str]]:
    """Load campaign knowledge for a given campaign ID."""
    try:
        from db.base import get_session
        from services.campaign_knowledge_service import CampaignKnowledgeService

        with get_session() as session:
            knowledge_service = CampaignKnowledgeService(session)
            return knowledge_service.get_knowledge_for_prompt(campaign_id)
    except Exception as exc:
        print(f"ai_context_builder: Failed to load campaign knowledge: {exc}")
        return None
