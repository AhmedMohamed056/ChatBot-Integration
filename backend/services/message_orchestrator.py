"""Inbound WhatsApp /message orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.base import get_session
from db.repositories.platform_repository import IdempotencyRepository
from services.campaign_lifecycle_service import CampaignLifecycleService
from services.conversation_service import ConversationService
from services.supervisor_authorization_service import get_active_supervisor


GROUP_CAMPAIGN_REFUSAL = (
    "إدارة الحملات متاحة في المحادثة الخاصة فقط. "
    "في المجموعات يمكنني الإجابة عن أسئلة المعرفة."
)


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
        chat_type = (inbound.chat_type or "private").lower()
        external_chat_id = inbound.external_chat_id or inbound.phone
        scope = "whatsapp:message"
        idem_key = inbound.external_message_id or hashlib.sha256(
            f"{external_chat_id}:{inbound.phone}:{inbound.message}".encode()
        ).hexdigest()

        with get_session() as session:
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
                chat_type=chat_type,
            )
            if conversations.record_message(
                conversation,
                direction="inbound",
                body=inbound.message,
                external_message_id=inbound.external_message_id,
                sender_phone=inbound.phone,
            ) is None and inbound.external_message_id:
                if cached and cached.response_body:
                    return str(cached.response_body.get("reply", ""))

            supervisor = get_active_supervisor(session, inbound.phone)
            if chat_type == "group":
                if supervisor:
                    reply = GROUP_CAMPAIGN_REFUSAL
                else:
                    reply = self._get_visitor_flow().handle_message(
                        phone=inbound.phone, message=inbound.message
                    ).reply
            elif supervisor:
                lifecycle = CampaignLifecycleService(session)
                reply = lifecycle.handle(
                    supervisor=supervisor,
                    conversation_id=conversation.id,
                    message=inbound.message,
                    original_message=inbound.message,
                )
            else:
                reply = self._get_visitor_flow().handle_message(
                    phone=inbound.phone, message=inbound.message
                ).reply

            conversations.record_message(
                conversation,
                direction="outbound",
                body=reply,
                sender_phone=None,
            )
            idem_repo.create(
                {
                    "scope": scope,
                    "key": idem_key,
                    "request_hash": hashlib.sha256(
                        inbound.message.encode("utf-8")
                    ).hexdigest(),
                    "response_body": {"reply": reply},
                    "expires_at": now + timedelta(days=1),
                }
            )
            return reply
