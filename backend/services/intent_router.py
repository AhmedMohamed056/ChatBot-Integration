"""Deterministic intent classification (LLM is not the router)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    GREETING = "greeting"
    GENERAL_QUESTION = "general_question"
    CREATE_CAMPAIGN = "create_campaign"
    UPDATE_CAMPAIGN = "update_campaign"
    DELETE_CAMPAIGN = "delete_campaign"
    CAMPAIGN_INQUIRY = "campaign_inquiry"
    CONFIRM_OK = "confirm_ok"
    CANCEL = "cancel"
    KNOWLEDGE_QUESTION = "knowledge_question"
    UNKNOWN = "unknown"


_GREETING = re.compile(
    r"^(?:مرحب|السلام|أهلا|اهلا|hello|hi)\b", re.IGNORECASE | re.UNICODE
)
_CREATE = re.compile(
    r"(?:حملة\s+جديد|إنشاء\s+حملة|create\s+campaign|new\s+campaign)",
    re.IGNORECASE | re.UNICODE,
)
_UPDATE = re.compile(
    r"(?:تحديث|تعديل|update\s+campaign|change\s+campaign)",
    re.IGNORECASE | re.UNICODE,
)
_DELETE = re.compile(
    r"(?:حذف\s+الحملة|delete\s+campaign|remove\s+campaign)",
    re.IGNORECASE | re.UNICODE,
)
_INQUIRY = re.compile(
    r"(?:حملتي|حملة\s+|my\s+campaign|campaign\s+status)",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    confidence: float


def detect_intent(message: str, *, pending_confirmation: bool = False) -> IntentResult:
    text = (message or "").strip()
    if not text:
        return IntentResult(Intent.UNKNOWN, 0.0)

    if pending_confirmation:
        if text.upper() == "OK":
            return IntentResult(Intent.CONFIRM_OK, 1.0)
        if text.lower() in {"cancel", "إلغاء", "الغاء", "no", "لا"}:
            return IntentResult(Intent.CANCEL, 0.9)
        return IntentResult(Intent.UPDATE_CAMPAIGN, 0.6)

    if _GREETING.search(text):
        return IntentResult(Intent.GREETING, 0.8)
    if _DELETE.search(text):
        return IntentResult(Intent.DELETE_CAMPAIGN, 0.85)
    if _CREATE.search(text):
        return IntentResult(Intent.CREATE_CAMPAIGN, 0.85)
    if _UPDATE.search(text):
        return IntentResult(Intent.UPDATE_CAMPAIGN, 0.8)
    if _INQUIRY.search(text):
        return IntentResult(Intent.CAMPAIGN_INQUIRY, 0.75)
    if "?" in text or text.endswith("؟"):
        return IntentResult(Intent.KNOWLEDGE_QUESTION, 0.55)
    return IntentResult(Intent.GENERAL_QUESTION, 0.4)
