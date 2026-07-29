"""Conversation Router — delegates to the platform message orchestrator."""

from __future__ import annotations

from services.message_orchestrator import InboundMessage, MessageOrchestrator


class ConversationRouter:
    def __init__(self) -> None:
        self._orchestrator = MessageOrchestrator()

    def route_message(
        self,
        phone: str,
        message: str,
        *,
        chat_type: str = "private",
        external_chat_id: str | None = None,
        external_message_id: str | None = None,
    ) -> str:
        return self._orchestrator.handle(
            InboundMessage(
                phone=phone,
                message=message,
                chat_type=chat_type,
                external_chat_id=external_chat_id,
                external_message_id=external_message_id,
            )
        )
