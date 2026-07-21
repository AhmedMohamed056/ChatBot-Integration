"""Campaign update extraction and context building."""

from __future__ import annotations

import json
import os
import re

from langchain_google_genai import ChatGoogleGenerativeAI

from database import (
    add_campaign_message,
    get_active_campaign_messages,
    get_campaign_by_phone,
)
from date_utils import get_current_datetime_context, is_expired, resolve_relative_expression

GREETING_PATTERNS = [
    r"^\s*(hi|hello|hey|salam|السلام|مرحبا|مرحباً|صباح|مساء)\b",
    r"^\s*(thanks|thank you|شكرا|شكراً)\b",
]


def _looks_like_greeting(message: str) -> bool:
    text = message.strip().lower()
    if len(text) < 8:
        return True
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in GREETING_PATTERNS)


def _build_extractor_llm(google_api_key: str):
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.0,
        google_api_key=google_api_key,
        max_retries=1,
        timeout=30,
    )


def extract_useful_campaign_info(message: str, google_api_key: str) -> dict | None:
    if _looks_like_greeting(message):
        return None

    llm = _build_extractor_llm(google_api_key)
    now_ctx = get_current_datetime_context()
    prompt = f"""
You extract only visitor-useful campaign information from WhatsApp admin messages.

Ignore greetings, small talk, unrelated chatter, and conversational filler.

Extract only useful visitor information such as:
- campaign announcements
- offers and discounts
- hotels and transportation
- meeting points
- schedules and programs
- instructions and contact numbers
- temporary notices

Current date context:
Gregorian: {now_ctx['gregorian_date']}
Hijri: {now_ctx['hijri_date']}
Day: {now_ctx['day_name_ar']}
Time: {now_ctx['time']}
Timezone: {now_ctx['timezone']}

Rules:
- If the message contains relative date expressions (today, tomorrow, after tomorrow, yesterday, this week, next week, tonight, tomorrow morning, this evening, next Friday, beginning of Muharram, end of Safar, etc.), convert them to absolute Gregorian dates using the current date context above.
- event_date and expires_at MUST be in Gregorian ISO format (YYYY-MM-DD).
- If no date is mentioned, set event_date and expires_at to null.
- If only an event date is mentioned without an expiry, set expires_at equal to event_date.
- extracted_info should be a concise structured Arabic summary that includes the resolved date when relevant.

Message:
{message}

Return strict JSON only:
{{
  "is_useful": true or false,
  "extracted_info": "short structured summary in Arabic",
  "event_date": "YYYY-MM-DD or null",
  "expires_at": "YYYY-MM-DD or null"
}}
"""
    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(0))
        if not data.get("is_useful"):
            return None
        if not str(data.get("extracted_info", "")).strip():
            return None
        return data
    except Exception:
        return None


def process_campaign_update(phone: str, message: str, google_api_key: str) -> dict:
    campaign = get_campaign_by_phone(phone)
    if not campaign:
        return {"ok": False, "reason": "campaign_not_found"}

    extracted = extract_useful_campaign_info(message, google_api_key)
    if not extracted:
        return {"ok": True, "stored": False, "reason": "no_useful_information"}

    event_date = extracted.get("event_date")
    if not event_date:
        event_date = resolve_relative_expression(message)

    expires_at = extracted.get("expires_at") or event_date
    if expires_at and is_expired(expires_at):
        return {"ok": True, "stored": False, "reason": "expired_information"}

    record = add_campaign_message(
        campaign_id=campaign["id"],
        campaign_name=campaign["name"],
        original_message=message,
        extracted_info=str(extracted["extracted_info"]).strip(),
        event_date=event_date,
        expires_at=expires_at,
    )
    return {"ok": True, "stored": True, "record": record}


def build_active_campaign_context() -> str:
    messages = get_active_campaign_messages()
    if not messages:
        return "No active campaign updates."

    lines = []
    for item in messages:
        if item.get("expires_at") and is_expired(item["expires_at"]):
            continue
        date_part = item.get("event_date") or "بدون تاريخ محدد"
        lines.append(
            f"- [{item['campaign_name']}] {item['extracted_info']} (Date: {date_part})"
        )
    return "\n".join(lines) if lines else "No active campaign updates."
