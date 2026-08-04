"""Conversation Memory Service - Phase 3.1.

Lightweight conversation memory for maintaining context across messages.
Maintains: Current Topic, Last User Intent, Last Assistant Action, Pending Context,
Conversation Summary, Last Edited Field, Recent Messages.

Memory is loaded before every Gemini request and updated after every response.
Memory is cleared when conversation becomes IDLE (task completion or cancel).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.platform_models import ConversationMemory
from services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

# Memory keys for the conversation memory system
MEMORY_KEY_CURRENT_TOPIC = "current_topic"
MEMORY_KEY_LAST_USER_INTENT = "last_user_intent"
MEMORY_KEY_LAST_ASSISTANT_ACTION = "last_assistant_action"
MEMORY_KEY_PENDING_CONTEXT = "pending_context"
MEMORY_KEY_PENDING_DRAFT = "pending_draft"
MEMORY_KEY_CONVERSATION_SUMMARY = "conversation_summary"
MEMORY_KEY_LAST_EDITED_FIELD = "last_edited_field"
MEMORY_KEY_RECENT_MESSAGES = "recent_messages"


class UserIntent(str, Enum):
    """User intent classification for conversation memory."""
    UPDATE_DESCRIPTION = "UPDATE_DESCRIPTION"
    UPDATE_BUDGET = "UPDATE_BUDGET"
    UPDATE_SERVICES = "UPDATE_SERVICES"
    UPDATE_CHANNELS = "UPDATE_CHANNELS"
    UPDATE_FIELD = "UPDATE_FIELD"
    DELETE_SERVICE = "DELETE_SERVICE"
    DELETE_PARAGRAPH = "DELETE_PARAGRAPH"
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    UNKNOWN = "UNKNOWN"


class AssistantAction(str, Enum):
    """Assistant action classification for conversation memory."""
    ASKED_FOR_DESCRIPTION = "AskedForDescription"
    ASKED_FOR_BUDGET = "AskedForBudget"
    ASKED_FOR_SERVICES = "AskedForServices"
    ASKED_FOR_CHANNELS = "AskedForChannels"
    ASKED_FOR_FIELD = "AskedForField"
    WAITING_FOR_CONFIRMATION = "WaitingForConfirmation"
    UPDATED_DESCRIPTION = "UpdatedDescription"
    UPDATED_BUDGET = "UpdatedBudget"
    UPDATED_SERVICES = "UpdatedServices"
    UPDATED_CHANNELS = "UpdatedChannels"
    UPDATED_FIELD = "UpdatedField"
    DELETED_SERVICE = "DeletedService"
    DELETED_PARAGRAPH = "DeletedParagraph"
    PROPOSED_CHANGE = "ProposedChange"
    IDLE = "Idle"


@dataclass
class PendingContext:
    """Structured pending context for field edits."""
    field: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PendingContext":
        if not data:
            return cls()
        return cls(
            field=data.get("field"),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
        )


@dataclass
class ConversationMemoryData:
    """Structured conversation memory data."""

    current_topic: Optional[str] = None
    last_user_intent: Optional[str] = None
    last_assistant_action: Optional[str] = None
    pending_context: Optional[dict[str, Any]] = None
    pending_draft: Optional[dict[str, Any]] = None
    conversation_summary: Optional[str] = None
    last_edited_field: Optional[str] = None
    recent_messages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "current_topic": self.current_topic,
            "last_user_intent": self.last_user_intent,
            "last_assistant_action": self.last_assistant_action,
            "pending_context": self.pending_context,
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
            last_user_intent=data.get("last_user_intent"),
            last_assistant_action=data.get("last_assistant_action"),
            pending_context=data.get("pending_context"),
            pending_draft=data.get("pending_draft"),
            conversation_summary=data.get("conversation_summary"),
            last_edited_field=data.get("last_edited_field"),
            recent_messages=data.get("recent_messages", []) or [],
        )

    def is_idle(self) -> bool:
        """Check if conversation is in IDLE state (no active task)."""
        return (
            self.last_assistant_action is None
            or self.last_assistant_action == AssistantAction.IDLE.value
        )

    def clear_task_state(self) -> None:
        """Clear task-specific state while preserving conversation history."""
        self.last_user_intent = None
        self.last_assistant_action = AssistantAction.IDLE.value
        self.pending_context = None
        self.pending_draft = None
        # Keep current_topic, conversation_summary, last_edited_field, recent_messages
        # for context continuity


class ConversationMemoryService:
    """Service for managing conversation memory.

    Provides lightweight conversation memory that maintains:
    - Current Topic: The main subject being discussed (description, budget, services, channels)
    - Last User Intent: The user's last intent (UPDATE_DESCRIPTION, DELETE_SERVICE, etc.)
    - Last Assistant Action: The assistant's last action (AskedForDescription, WaitingForConfirmation, etc.)
    - Pending Context: Structured context for pending edits (field, old_value, new_value)
    - Pending Draft: In-progress draft data
    - Conversation Summary: Brief summary of the conversation
    - Last Edited Field: Most recently modified field
    - Recent Messages: Last few messages for context

    Memory is automatically loaded before Gemini requests and updated after responses.
    Memory is cleared when conversation becomes IDLE.
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
            MEMORY_KEY_LAST_USER_INTENT,
            MEMORY_KEY_LAST_ASSISTANT_ACTION,
            MEMORY_KEY_PENDING_CONTEXT,
            MEMORY_KEY_PENDING_DRAFT,
            MEMORY_KEY_CONVERSATION_SUMMARY,
            MEMORY_KEY_LAST_EDITED_FIELD,
            MEMORY_KEY_RECENT_MESSAGES,
        ]:
            memory_value = self._get_memory_value(conversation_id, memory_key)
            if memory_value:
                if memory_key == MEMORY_KEY_CURRENT_TOPIC:
                    memory_data.current_topic = memory_value.get("value")
                elif memory_key == MEMORY_KEY_LAST_USER_INTENT:
                    memory_data.last_user_intent = memory_value.get("value")
                elif memory_key == MEMORY_KEY_LAST_ASSISTANT_ACTION:
                    memory_data.last_assistant_action = memory_value.get("value")
                elif memory_key == MEMORY_KEY_PENDING_CONTEXT:
                    memory_data.pending_context = memory_value.get("value")
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
            MEMORY_KEY_LAST_USER_INTENT,
            memory_data.last_user_intent
        )
        self._save_memory_field(
            conversation_id,
            MEMORY_KEY_LAST_ASSISTANT_ACTION,
            memory_data.last_assistant_action
        )
        self._save_memory_field(
            conversation_id,
            MEMORY_KEY_PENDING_CONTEXT,
            memory_data.pending_context
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
        """Save a single memory field.

        When value is None, the field is explicitly cleared (tombstoned) so
        that stale values do not persist after a task is completed/cancelled.
        """
        if value is None:
            # Explicitly clear the field so old values don't linger.
            self.clear_memory_field(conversation_id, memory_key)
            return

        self.conversation_service.upsert_memory(
            conversation_id=conversation_id,
            memory_key=memory_key,
            memory_value=value
        )
        # NOTE: Do NOT commit here. The session is managed by the outer
        # get_session() context manager in message_orchestrator.py.
        # Committing here would prevent CampaignLifecycleService from persisting
        # CampaignUpdate, CampaignVersion, and OutboxEvent objects.

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

        # Update user intent and assistant action based on message content
        if direction == "inbound":
            self._update_user_intent(memory_data, message)
        elif direction == "outbound":
            self._update_assistant_action(memory_data, message, response)

        # Update pending context if we have an active edit session
        self._update_pending_context(memory_data, message, direction)

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
        # Topic keywords for campaign fields
        topic_keywords = {
            "description": ["وصف", "description", "نص", "text", "الوصف"],
            "budget": ["ميزانية", "budget", "تكلفة", "cost", "سعر", "price"],
            "services": ["خدمات", "services", "خدمة", "service"],
            "channels": ["قنوات", "channels", "قناة", "channel", "وسائل", "media"],
            "location": ["موقع", "location", "مكان", "place"],
            "date": ["تاريخ", "date", "موعد", "time", "وقت"],
            "name": ["اسم", "name", "عنوان", "title"],
        }

        message_lower = message.lower()

        # Check for topic keywords
        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    memory_data.current_topic = topic
                    return

        # If no topic detected and no current topic, use first few words
        if not memory_data.current_topic:
            words = message.split()[:5]
            memory_data.current_topic = " ".join(words)[:100]

    def _update_last_edited_field(self, memory_data: ConversationMemoryData, message: str) -> None:
        """Update last edited field based on message content."""
        # Look for field-specific keywords
        field_patterns = {
            "description": ["وصف", "description", "نص", "text", "الوصف"],
            "budget": ["ميزانية", "budget", "تكلفة", "cost"],
            "services": ["خدمات", "services", "خدمة", "service"],
            "channels": ["قنوات", "channels", "قناة", "channel"],
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

    def _update_user_intent(self, memory_data: ConversationMemoryData, message: str) -> None:
        """Update user intent based on message content."""
        message_lower = message.lower().strip()

        # Context-aware negative response: REJECT when the assistant is waiting
        # for confirmation or has proposed a change; CANCEL otherwise.
        waiting_for_confirmation = memory_data.last_assistant_action in {
            AssistantAction.WAITING_FOR_CONFIRMATION.value,
            AssistantAction.PROPOSED_CHANGE.value,
        }
        if message_lower in {"no", "لا", "لاء", "reject", "رفض"}:
            memory_data.last_user_intent = (
                UserIntent.REJECT.value if waiting_for_confirmation else UserIntent.CANCEL.value
            )
            return

        # Explicit cancel intent
        if message_lower in {"cancel", "إلغاء", "الغاء"}:
            memory_data.last_user_intent = UserIntent.CANCEL.value
            return

        # Confirm intent
        confirm_tokens = {"ok", "okay", "approve", "approved", "confirm", "confirmed",
                         "yes", "نعم", "موافق", "موافقة", "تأكيد", "تاكيد", "تم", "done"}
        if message_lower in confirm_tokens or message_lower.upper() == "OK":
            memory_data.last_user_intent = UserIntent.CONFIRM.value
            return

        # Delete intents
        if any(kw in message_lower for kw in ["احذف", "delete", "remove", "امسح"]):
            if any(kw in message_lower for kw in ["فقرة", "paragraph", "جملة", "sentence"]):
                memory_data.last_user_intent = UserIntent.DELETE_PARAGRAPH.value
            elif any(kw in message_lower for kw in ["خدمة", "service"]):
                memory_data.last_user_intent = UserIntent.DELETE_SERVICE.value
            else:
                memory_data.last_user_intent = UserIntent.DELETE_PARAGRAPH.value
            return

        # Update intents based on field
        if any(kw in message_lower for kw in ["وصف", "description", "نص", "text"]):
            if any(kw in message_lower for kw in ["غير", "change", "عدل", "update", "modify", "edit"]):
                memory_data.last_user_intent = UserIntent.UPDATE_DESCRIPTION.value
                return

        if any(kw in message_lower for kw in ["ميزانية", "budget", "تكلفة", "cost"]):
            if any(kw in message_lower for kw in ["غير", "change", "عدل", "update", "modify", "edit"]):
                memory_data.last_user_intent = UserIntent.UPDATE_BUDGET.value
                return

        if any(kw in message_lower for kw in ["خدمات", "services", "خدمة", "service"]):
            if any(kw in message_lower for kw in ["غير", "change", "عدل", "update", "modify", "edit", "أضف", "add"]):
                memory_data.last_user_intent = UserIntent.UPDATE_SERVICES.value
                return

        if any(kw in message_lower for kw in ["قنوات", "channels", "قناة", "channel"]):
            if any(kw in message_lower for kw in ["غير", "change", "عدل", "update", "modify", "edit", "أضف", "add"]):
                memory_data.last_user_intent = UserIntent.UPDATE_CHANNELS.value
                return

        # Generic update intent
        if any(kw in message_lower for kw in ["غير", "change", "عدل", "update", "modify", "edit"]):
            memory_data.last_user_intent = UserIntent.UPDATE_FIELD.value
            return

        # If we have a pending context and user provides a value, maintain the intent
        if memory_data.pending_context and memory_data.last_user_intent:
            # User is providing the requested value
            return

        # Default to UNKNOWN if no pattern matched
        if not memory_data.last_user_intent:
            memory_data.last_user_intent = UserIntent.UNKNOWN.value

    def _update_assistant_action(
        self,
        memory_data: ConversationMemoryData,
        message: str,
        response: Optional[str] = None
    ) -> None:
        """Update assistant action based on response content."""
        message_lower = message.lower()

        # Check for asking patterns
        if any(kw in message_lower for kw in ["ما هو", "what is", "أرسل", "send", "من فضلك أرسل"]):
            if any(kw in message_lower for kw in ["وصف", "description", "نص"]):
                memory_data.last_assistant_action = AssistantAction.ASKED_FOR_DESCRIPTION.value
                return
            if any(kw in message_lower for kw in ["ميزانية", "budget"]):
                memory_data.last_assistant_action = AssistantAction.ASKED_FOR_BUDGET.value
                return
            if any(kw in message_lower for kw in ["خدمات", "services"]):
                memory_data.last_assistant_action = AssistantAction.ASKED_FOR_SERVICES.value
                return
            if any(kw in message_lower for kw in ["قنوات", "channels"]):
                memory_data.last_assistant_action = AssistantAction.ASKED_FOR_CHANNELS.value
                return
            memory_data.last_assistant_action = AssistantAction.ASKED_FOR_FIELD.value
            return

        # Check for confirmation waiting
        if any(kw in message_lower for kw in ["راجع", "review", "هل تعتمد", "confirm", "موافق"]):
            memory_data.last_assistant_action = AssistantAction.WAITING_FOR_CONFIRMATION.value
            return

        # Check for update completion
        if any(kw in message_lower for kw in ["تم حفظ", "saved", "تم تحديث", "updated", "تم بنجاح"]):
            if memory_data.last_edited_field == "description":
                memory_data.last_assistant_action = AssistantAction.UPDATED_DESCRIPTION.value
            elif memory_data.last_edited_field == "budget":
                memory_data.last_assistant_action = AssistantAction.UPDATED_BUDGET.value
            elif memory_data.last_edited_field == "services":
                memory_data.last_assistant_action = AssistantAction.UPDATED_SERVICES.value
            elif memory_data.last_edited_field == "channels":
                memory_data.last_assistant_action = AssistantAction.UPDATED_CHANNELS.value
            else:
                memory_data.last_assistant_action = AssistantAction.UPDATED_FIELD.value
            return

        # Check for delete completion
        if any(kw in message_lower for kw in ["تم حذف", "deleted", "تم إزالة", "removed"]):
            if memory_data.last_edited_field == "services":
                memory_data.last_assistant_action = AssistantAction.DELETED_SERVICE.value
            else:
                memory_data.last_assistant_action = AssistantAction.DELETED_PARAGRAPH.value
            return

        # Check for proposal
        if any(kw in message_lower for kw in ["اقترح", "propose", "suggest", "هل تريد"]):
            memory_data.last_assistant_action = AssistantAction.PROPOSED_CHANGE.value
            return

        # Default: if we have a pending context, we're waiting for something
        if memory_data.pending_context:
            memory_data.last_assistant_action = AssistantAction.WAITING_FOR_CONFIRMATION.value
        elif not memory_data.last_assistant_action:
            memory_data.last_assistant_action = AssistantAction.IDLE.value

    def _update_pending_context(
        self,
        memory_data: ConversationMemoryData,
        message: str,
        direction: str
    ) -> None:
        """Update pending context based on conversation flow."""
        # If user is providing a value for a pending field
        if direction == "inbound" and memory_data.pending_context:
            pending = PendingContext.from_dict(memory_data.pending_context)
            if pending.field and not pending.new_value:
                # User is providing the new value
                pending.new_value = message
                memory_data.pending_context = pending.to_dict()
                return

        # If assistant asked for a field, set up pending context
        if direction == "outbound":
            action = memory_data.last_assistant_action
            if action and action.startswith("AskedFor"):
                # Extract field name from action
                field_name = action.replace("AskedFor", "").lower()
                if field_name:
                    pending = PendingContext(field=field_name)
                    memory_data.pending_context = pending.to_dict()
                    return

        # If we have a draft being built, update pending context from it
        if memory_data.pending_draft:
            draft = memory_data.pending_draft
            if isinstance(draft, dict):
                # Find the field being edited
                for key in ["description", "budget", "services", "channels"]:
                    if key in draft:
                        pending = PendingContext(
                            field=key,
                            old_value=draft.get(f"old_{key}"),
                            new_value=draft.get(key)
                        )
                        memory_data.pending_context = pending.to_dict()
                        return

    def get_memory_for_prompt(self, conversation_id: int) -> dict[str, Any]:
        """Get conversation memory formatted for prompt injection.

        Returns a dictionary with memory fields suitable for including in prompts.
        """
        memory_data = self.load_memory(conversation_id)

        return {
            "current_topic": memory_data.current_topic,
            "last_user_intent": memory_data.last_user_intent,
            "last_assistant_action": memory_data.last_assistant_action,
            "pending_context": memory_data.pending_context,
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
        # NOTE: Do NOT commit here. The session is managed by the outer
        # get_session() context manager.

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
            # NOTE: Do NOT commit here. The session is managed by the outer
            # get_session() context manager.

    def clear_task_state(self, conversation_id: int) -> None:
        """Clear task-specific state while preserving conversation history.

        This is called when a task is completed or cancelled, transitioning
        the conversation to IDLE state.
        """
        memory_data = self.load_memory(conversation_id)
        memory_data.clear_task_state()
        self.save_memory(conversation_id, memory_data)

    def set_idle(self, conversation_id: int) -> None:
        """Set conversation to IDLE state.

        This clears task-specific state but preserves conversation history
        for context continuity.
        """
        self.clear_task_state(conversation_id)
