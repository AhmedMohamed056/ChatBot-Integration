"""Visitor Question Logging service (Task 10).

Responsibilities (and **only** these):

1. Normalise the phone number (reuses :mod:`phone_utils`).
2. Detect the language using a simple heuristic (Arabic / English / Unknown).
3. Store everything via :class:`VisitorQuestionRepository`.
4. Return a success result.

Visitor-to-campaign detection has been removed from the system, so
``visitor_name`` / ``campaign_name`` are always stored as ``NULL``.

This service intentionally contains **no** reporting, analytics, AI,
prompt-engineering, or Gemini logic.  It never fails because detection
failed - if the visitor is not found, the question is still saved with
``NULL`` visitor/campaign values.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from db.base import get_session, utc_now
from db.repositories.visitor_question_repository import VisitorQuestionRepository
from phone_utils import normalize_phone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Language detection (simple heuristic - NO AI)
# ---------------------------------------------------------------------------


def detect_language(message: str) -> str:
    """Return ``"ar"``, ``"en"`` or ``"unknown"`` using a simple heuristic.

    Rules
    -----
    - If the message contains any Arabic Unicode character -> ``"ar"``.
    - Else if it contains any ASCII letter            -> ``"en"``.
    - Else                                            -> ``"unknown"``.

    No AI model is used.
    """
    if not message:
        return "unknown"

    # Arabic Unicode blocks: Arabic, Arabic Supplement, Arabic Extended-A/B,
    # Arabic Presentation Forms-A/B.
    for ch in message:
        code = ord(ch)
        if (
            0x0600 <= code <= 0x06FF
            or 0x0750 <= code <= 0x077F
            or 0x08A0 <= code <= 0x08FF
            or 0xFB50 <= code <= 0xFDFF
            or 0xFE70 <= code <= 0xFEFF
        ):
            return "ar"

    # ASCII letters -> English.
    if any(ch.isascii() and ch.isalpha() for ch in message):
        return "en"

    return "unknown"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def log_visitor_question(
    phone_number: Optional[str],
    message: str,
) -> dict:
    """Log a single visitor question.

    Parameters
    ----------
    phone_number:
        Raw sender phone number (may be ``None`` / empty).
    message:
        The visitor's question text.  Must be non-empty.

    Returns
    -------
    dict
        ``{"ok": True, "id": <int>}`` on success.

    Raises
    ------
    ValueError
        If ``message`` is empty / whitespace-only.
    """
    # --- Validation -------------------------------------------------------
    if message is None or not str(message).strip():
        raise ValueError("Question cannot be empty.")
    question_text = str(message).strip()

    # --- Normalise phone --------------------------------------------------
    normalized_phone: Optional[str] = None
    if phone_number:
        normalized = normalize_phone(phone_number)
        normalized_phone = normalized or None

    # --- Visitor detection removed ----------------------------------------
    # Visitor-to-campaign detection is no longer part of the system. Questions
    # are still logged, but always with NULL visitor/campaign values.
    visitor_name: Optional[str] = None
    campaign_name: Optional[str] = None

    # --- Detect language (simple heuristic) -------------------------------
    language = detect_language(question_text)

    # --- Store ------------------------------------------------------------
    message_timestamp: datetime = utc_now()
    question_id: Optional[int] = None

    with get_session() as session:
        repo = VisitorQuestionRepository(session)
        record = repo.log_question(
            question=question_text,
            phone_number=normalized_phone,
            visitor_name=visitor_name,
            campaign_name=campaign_name,
            detected_language=language,
            message_timestamp=message_timestamp,
        )
        question_id = record.id

    logger.info(
        "Logged visitor question id=%s phone=%s campaign=%s language=%s",
        question_id,
        normalized_phone,
        campaign_name,
        language,
    )

    return {"ok": True, "id": question_id}