"""Conversation Memory Service - Phase 3.

Lightweight conversation memory for maintaining context across messages.
Maintains: Current Topic, Pending Draft, Conversation Summary, Last Edited Field, Recent Messages.

Memory is loaded before every Gemini request and updated after every response.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.platform_models import ConversationMemory
from services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

# Memory keys for the conversation memory system
MEMORY_KEY_CURRENT_TOPIC = "current_topic"
MEMORY_KEY_PENDING_DRAFT = "pending_draft"
MEMORY_KEY_CONVERSATION_SUMMARY = "conversation_summary"
MEMORY_KEY_LAST_EDITED_FIELD = "last_edited_field"
MEMORY_KEY_RECENT_MESSAGES = "recent_messages"

@dataclass
class ConversationMemoryData:
    """Structured conversation memory data."""

    current_topic: Optional[str] = None
    pending_draft: Optional[dict[str, Any]] = None
    conversation_summary: Optional[str] = None
    last_edited_field: Optional[str] = None
    recent_messages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "current_topic": self.current_topic,
            "pending_draft": self.pending_draft,
            "conversation_summary": self.conversation_summary,
            "last_edited_field": self.last_edited_field,
            "recent_messages": self.recent_messages,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConversationMemoryData":
        """Create from stored dictionary."""
        if not data:
            return cls()

        return cls(
            current_topic=data.get("current_topic"),
            pending_draft=data.get("pending_draft"),
            conversation_summary=data.get("conversation_summary"),
            last_edited_field=data.get("last_edited_field"),
            recent_messages=data.get("recent_messages", []) or [],
        )

class ConversationMemoryService:
    """Service for managing conversation memory.

    Provides lightweight conversation memory that maintains:
    - Current Topic: The main subject being discussed
    - Pending Draft: In-progress draft data
    - Conversation Summary: Brief summary of the conversation
    - Last Edited Field: Most recently modified field
    - Recent Messages: Last few messages for context

    Memory is automatically loaded before Gemini requests and updated after responses.
    """

    def __init__(self, session: Session):
        self.session = session
        self.conversation_service = ConversationService(session)

    def load_memory(self, conversation_id: int) -> ConversationMemoryData:
        """Load conversation memory for a given conversation.

        Args:
            conversation_id: The conversation ID to load memory for.

        Returns:
            ConversationMemoryData containing all memory fields.
        """
        memory_data = ConversationMemoryData()

        # Load each memory key individually
        for memory_key in [
            MEMORY_KEY_CURRENT_TOPIC,
            MEMORY_KEY_PENDING_DRAFT,
            MEMORY_KEY_CONVERSATION_SUMMARY,
            MEMORY_KEY_LAST_EDITED_FIELD,
            MEMORY_KEY_RECENT_MESSAGES,
        ]:
            memory_value = self._get_memory_value(conversation_id, memory_key)
            if memory_value:
                if memory_key == MEMORY_KEY_CURRENT_TOPIC:
                    memory_data.current_topic = memory_value.get("value")
                elif memory_key == MEMORY_KEY_PENDING_DRAFT:
                    memory_data.pending_draft = memory_value.get("value")
                elif memory_key == MEMORY_KEY_CONVERSATION_SUMMARY:
                    memory_data.conversation_summary = memory_value.get("value")
                elif memory_key == MEMORY_KEY_LAST_EDITED_FIELD:
                    memory_data.last_edited_field = memory_value.get("value")
                elif memory_key == MEMORY_KEY_RECENT_MESSAGES:
                    memory_data.recent_messages = memory_value.get("value", [])

        return memory_data

    def _get_memory_value(self, conversation_id: int, memory_key: str) -> Optional[dict[str, Any]]:
        """Get a single memory value by key."""
        memory = self.session.scalar(
            select(ConversationMemory).where(
                ConversationMemory.conversation_id == conversation_id,
                ConversationMemory.memory_key == memory_key,
                ConversationMemory.tombstoned_at == None,  # noqa: E711
            )
        )
        if memory:
            return {"value": memory.memory_value, "key": memory.memory_key}
        return None

    def save_memory(self, conversation_id: int, memory_data: ConversationMemoryData) -> None:
        """Save conversation memory for a given conversation.

        Args:
            conversation_id: The conversation ID to save memory for.
            memory_data: The memory data to save.
        """
        # Save each memory field individually
        self._save_memory_field(
            conversation_id,
            MEMORY_KEY_CURRENT_TOPIC,
            memory_data.current_topic
        )
        self._save_memory_field(
            conversation_id,
            MEMORY_KEY_PENDING_DRAFT,
            memory_data.pending_draft
        )
        self._save_memory_field(
            conversation_id,
            MEMORY_KEY_CONVERSATION_SUMMARY,
            memory_data.conversation_summary
        )
        self._save_memory_field(
            conversation_id,
            MEMORY_KEY_LAST_EDITED_FIELD,
            memory_data.last_edited_field
        )
        self._save_memory_field(
            conversation_id,
            MEMORY_KEY_RECENT_MESSAGES,
            memory_data.recent_messages
        )

    def _save_memory_field(
        self,
        conversation_id: int,
        memory_key: str,
        value: Any
    ) -> None:
        """Save a single memory field."""
        if value is None:
            # Don't save None values, they'll be treated as empty
            return

        self.conversation_service.upsert_memory(
            conversation_id=conversation_id,
            memory_key=memory_key,
            memory_value=value
        )

    def update_memory_from_message(
        self,
        conversation_id: int,
        message: str,
        direction: str = "inbound",
        sender_phone: Optional[str] = None,
        response: Optional[str] = None
    ) -> ConversationMemoryData:
        """Update conversation memory based on a new message and optional response.

        This method loads existing memory, updates it with the new message,
        and saves it back.

        Args:
            conversation_id: The conversation ID.
            message: The new message text.
            direction: Message direction ('inbound' or 'outbound').
            sender_phone: Optional sender phone number.
            response: Optional response text (for outbound messages).

        Returns:
            Updated ConversationMemoryData.
        """
        # Load existing memory
        memory_data = self.load_memory(conversation_id)

        # Update recent messages
        new_message = {
            "text": message,
            "direction": direction,
            "sender_phone": sender_phone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "response": response
        }

        # Keep only the last 10 messages for context
        recent_messages = memory_data.recent_messages or []
        recent_messages.append(new_message)
        memory_data.recent_messages = recent_messages[-10:]  # Keep last 10

        # Update conversation summary based on the new message
        self._update_conversation_summary(memory_data, message, response)

        # Update current topic if we can infer it
        self._update_current_topic(memory_data, message)

        # Update last edited field if this looks like a field edit
        self._update_last_edited_field(memory_data, message)

        # Save updated memory
        self.save_memory(conversation_id, memory_data)

        return memory_data

    def _update_conversation_summary(
        self,
        memory_data: ConversationMemoryData,
        message: str,
        response: Optional[str] = None
    ) -> None:
        """Update the conversation summary based on new message."""
        # Simple heuristic: if we have a summary, append new info
        # If not, create a basic summary from the first message
        if not memory_data.conversation_summary:
            # First message - use it as the initial summary
            memory_data.conversation_summary = message[:200]  # Limit length
        else:
            # Append new information to summary (with length limit)
            new_info = f" User: {message[:100]}"
            if response:
                new_info += f" Bot: {response[:100]}"
            current_summary = memory_data.conversation_summary or ""
            updated_summary = f"{current_summary}{new_info}"
            memory_data.conversation_summary = updated_summary[:500]  # Keep summary reasonable

    def _update_current_topic(self, memory_data: ConversationMemoryData, message: str) -> None:
        """Update current topic based on message content."""
        # Simple topic detection - look for keywords that indicate topic changes
        topic_keywords = [
            "حملة", "campaign", "وصف", "description", "تاريخ", "date",
            "موقع", "location", "حذف", "delete", "تحديث", "update",
            "إنشاء", "create", "اسم", "name"
        ]

        # If no current topic or message contains topic keywords, update topic
        if not memory_data.current_topic:
            # Use first few words as topic
            words = message.split()[:5]
            memory_data.current_topic = " ".join(words)[:100]
        else:
            # Check if message suggests a topic change
            message_lower = message.lower()
            for keyword in topic_keywords:
                if keyword in message_lower:
                    # Extract topic from message
                    words = message.split()[:5]
                    memory_data.current_topic = " ".join(words)[:100]
                    break

    def _update_last_edited_field(self, memory_data: ConversationMemoryData, message: str) -> None:
        """Update last edited field based on message content."""
        # Look for field-specific keywords
        field_patterns = {
            "description": ["وصف", "description", "نص", "text"],
            "start_date": ["تاريخ البداية", "start date", "بداية", "begin"],
            "end_date": ["تاريخ النهاية", "end date", "نهاية", "end"],
            "location": ["موقع", "location", "مكان", "place"],
            "campaign_name": ["اسم الحملة", "campaign name", "اسم", "name"],
            "deletion_reason": ["سبب الحذف", "delete reason", "سبب", "reason"]
        }

        message_lower = message.lower()
        for field_name, keywords in field_patterns.items():
            for keyword in keywords:
                if keyword in message_lower:
                    memory_data.last_edited_field = field_name
                    return

        # If no specific field detected and we have a pending draft,
        # try to infer from draft context
        if memory_data.pending_draft:
            draft_keys = list(memory_data.pending_draft.keys())
            if draft_keys:
                memory_data.last_edited_field = draft_keys[-1]

    def get_memory_for_prompt(self, conversation_id: int) -> dict[str, Any]:
        """Get conversation memory formatted for prompt injection.

        Returns a dictionary with memory fields suitable for including in prompts.
        """
        memory_data = self.load_memory(conversation_id)

        return {
            "current_topic": memory_data.current_topic,
            "pending_draft": memory_data.pending_draft,
            "conversation_summary": memory_data.conversation_summary,
            "last_edited_field": memory_data.last_edited_field,
            "recent_messages": memory_data.recent_messages,
        }

    def clear_memory(self, conversation_id: int) -> None:
        """Clear all conversation memory for a conversation."""
        self.session.execute(
            ConversationMemory.__table__.delete().where(
                ConversationMemory.conversation_id == conversation_id
            )
        )
        self.session.commit()

    def clear_memory_field(self, conversation_id: int, memory_key: str) -> None:
        """Clear a specific memory field for a conversation."""
        memory = self.session.scalar(
            select(ConversationMemory).where(
                ConversationMemory.conversation_id == conversation_id,
                ConversationMemory.memory_key == memory_key,
            )
        )
        if memory:
            self.session.delete(memory)
            self.session.commit()