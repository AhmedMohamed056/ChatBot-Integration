"""Persistent conversations, messages, state, and memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.platform_models import Conversation, ConversationMemory, ConversationState, Message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(
        self,
        *,
        channel: str,
        external_chat_id: str,
        participant_phone: Optional[str],
        chat_type: str,
        campaign_id: Optional[int] = None,
    ) -> Conversation:
        existing = self.session.scalar(
            select(Conversation).where(
                Conversation.channel == channel,
                Conversation.external_chat_id == external_chat_id,
            )
        )
        if existing:
            return existing
        row = Conversation(
            channel=channel,
            external_chat_id=external_chat_id,
            participant_phone=participant_phone,
            chat_type=chat_type,
            campaign_id=campaign_id,
            status="open",
        )
        self.session.add(row)
        self.session.flush()
        return row

    def record_message(
        self,
        conversation: Conversation,
        *,
        direction: str,
        body: str,
        external_message_id: Optional[str] = None,
        sender_phone: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> Optional[Message]:
        if external_message_id:
            dup = self.session.scalar(
                select(Message).where(
                    Message.conversation_id == conversation.id,
                    Message.external_message_id == external_message_id,
                )
            )
            if dup:
                return None
        msg = Message(
            conversation_id=conversation.id,
            direction=direction,
            body=body,
            external_message_id=external_message_id,
            sender_phone=sender_phone,
            payload=payload,
            occurred_at=_utcnow(),
        )
        self.session.add(msg)
        self.session.flush()
        return msg

    def get_state(self, conversation_id: int) -> ConversationState:
        state = self.session.scalar(
            select(ConversationState).where(
                ConversationState.conversation_id == conversation_id
            )
        )
        if state:
            return state
        state = ConversationState(
            conversation_id=conversation_id,
            state_name="IDLE",
            state_data={},
            expires_at=_utcnow() + timedelta(days=7),
        )
        self.session.add(state)
        self.session.flush()
        return state

    def set_state(
        self,
        state: ConversationState,
        *,
        state_name: str,
        state_data: dict[str, Any],
        ttl_days: int = 7,
    ) -> None:
        state.state_name = state_name
        state.state_data = state_data
        state.expires_at = _utcnow() + timedelta(days=ttl_days)
        self.session.flush()  # Persist immediately to avoid lost updates

    def upsert_memory(
        self,
        conversation_id: int,
        memory_key: str,
        memory_value: dict[str, Any],
    ) -> None:
        row = self.session.scalar(
            select(ConversationMemory).where(
                ConversationMemory.conversation_id == conversation_id,
                ConversationMemory.memory_key == memory_key,
            )
        )
        if row:
            row.memory_value = memory_value
            row.tombstoned_at = None
        else:
            self.session.add(
                ConversationMemory(
                    conversation_id=conversation_id,
                    memory_key=memory_key,
                    memory_value=memory_value,
                )
            )
        self.session.flush()
