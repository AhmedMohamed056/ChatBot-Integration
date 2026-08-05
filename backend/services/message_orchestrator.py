"""Inbound WhatsApp /message orchestration.

Private-chat authorization is the FIRST decision. Unknown numbers never
enter conversation, memory, Gemini, RAG, intent, or campaign pipelines.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.base import get_session
from db.platform_models import Supervisor
from db.repositories.platform_repository import IdempotencyRepository
from services.campaign_lifecycle_service import CampaignLifecycleService
from services.conversation_service import ConversationService
from services.intent_router import CAMPAIGN_MUTATION_INTENTS, detect_intent
from services.runtime_settings import get_runtime_setting
from services.supervisor_authorization_service import authorize_private_sender

logger = logging.getLogger(__name__)

GROUP_CAMPAIGN_REFUSAL = (
    "إدارة الحملات متاحة في المحادثة الخاصة فقط. "
    "في المجموعات يمكنني الإجابة عن أسئلة المعرفة."
)

PRIVATE_NON_SUPERVISOR = (
    "عذراً، أنت غير مسجل كمشرف حملة.\n"
    "Sorry, you are not registered as a campaign supervisor."
)


def _private_unauthorized_reply() -> str:
    """Return empty string (ignore) or the configured rejection text.

    Never triggers AI, conversation, or persistence side effects.
    """
    mode = (
        get_runtime_setting("private_unauthorized_mode", "ignore") or "ignore"
    ).strip().lower()
    if mode == "message":
        return PRIVATE_NON_SUPERVISOR
    return ""


@dataclass
class InboundMessage:
    phone: str
    message: str
    chat_type: str = "private"
    external_chat_id: Optional[str] = None
    external_message_id: Optional[str] = None


class MessageOrchestrator:
    def __init__(self) -> None:
        self._visitor_flow = None

    def _get_visitor_flow(self):
        if self._visitor_flow is None:
            from visitor_flow import VisitorFlow

            self._visitor_flow = VisitorFlow()
        return self._visitor_flow

    def handle(self, inbound: InboundMessage) -> str:
        chat_type = (inbound.chat_type or "private").strip().lower()

        # --- PRIVATE: authorization gate BEFORE any pipeline ---
        if chat_type == "private":
            supervisor = self._authorize_private_read_only(inbound.phone)
            if supervisor is None:
                logger.info(
                    "Private WhatsApp rejected (not an active imported supervisor).",
                    extra={"phone_suffix": (inbound.phone or "")[-4:]},
                )
                return _private_unauthorized_reply()
            return self._handle_supervisor_private(inbound, supervisor)

        # --- GROUP: knowledge only ---
        return self._handle_group(inbound)

    def _authorize_private_read_only(self, phone: str) -> Optional[Supervisor]:
        """Look up supervisors table only. No conversation / memory / audit writes."""
        with get_session() as session:
            return authorize_private_sender(session, phone)

    def _handle_group(self, inbound: InboundMessage) -> str:
        intent = detect_intent(inbound.message).intent
        if intent in CAMPAIGN_MUTATION_INTENTS:
            return GROUP_CAMPAIGN_REFUSAL
        # Knowledge question in a group: answer it via the visitor flow AND
        # record it into the same dashboard pipeline as website questions.
        result = self._get_visitor_flow().handle_message(
            phone=inbound.phone, message=inbound.message
        )
        from whatsapp_question_log import log_whatsapp_question

        log_whatsapp_question(inbound.message, result.reply, phone=inbound.phone)
        return result.reply

    def _handle_supervisor_private(
        self, inbound: InboundMessage, authorized: Supervisor
    ) -> str:
        external_chat_id = inbound.external_chat_id or inbound.phone
        scope = "whatsapp:message"
        idem_key = inbound.external_message_id or hashlib.sha256(
            f"{external_chat_id}:{inbound.phone}:{inbound.message}".encode()
        ).hexdigest()

        with get_session() as session:
            # Re-bind supervisor in this session (previous session closed).
            supervisor = authorize_private_sender(session, inbound.phone)
            if supervisor is None or supervisor.id != authorized.id:
                return _private_unauthorized_reply()

            idem_repo = IdempotencyRepository(session)
            now = datetime.now(timezone.utc)
            cached = idem_repo.get_valid(scope, idem_key, now)
            if cached and cached.response_body and "reply" in cached.response_body:
                return str(cached.response_body["reply"])

            conversations = ConversationService(session)
            conversation = conversations.get_or_create(
                channel="whatsapp",
                external_chat_id=external_chat_id,
                participant_phone=inbound.phone,
                chat_type="private",
                campaign_id=None,
            )
            if (
                conversations.record_message(
                    conversation,
                    direction="inbound",
                    body=inbound.message,
                    external_message_id=inbound.external_message_id,
                    sender_phone=inbound.phone,
                )
                is None
                and inbound.external_message_id
            ):
                if cached and cached.response_body:
                    return str(cached.response_body.get("reply", ""))

            # Check and send greeting if not already sent
            state = conversations.get_state(conversation.id)
            state_data = dict(state.state_data or {})
            greeting_text = ""
            if not state_data.get("greeting_sent"):
                from services.supervisor_context_service import build_supervisor_greeting
                greeting_text = build_supervisor_greeting(
                    session, supervisor, conversation.id
                )
                state_data["greeting_sent"] = True
                conversations.set_state(
                    state, state_name=state.state_name, state_data=state_data
                )

            lifecycle = CampaignLifecycleService(session)
            reply = lifecycle.handle(
                supervisor=supervisor,
                conversation_id=conversation.id,
                message=inbound.message,
                original_message=inbound.message,
            )

            # Prepend greeting to the first response only
            final_reply = greeting_text + reply if greeting_text else reply

            conversations.record_message(
                conversation,
                direction="outbound",
                body=final_reply,
                sender_phone=None,
            )
            idem_repo.create(
                {
                    "scope": scope,
                    "key": idem_key,
                    "request_hash": hashlib.sha256(
                        inbound.message.encode("utf-8")
                    ).hexdigest(),
                    "response_body": {"reply": final_reply},
                    "expires_at": now + timedelta(days=1),
                }
            )
            return final_reply
