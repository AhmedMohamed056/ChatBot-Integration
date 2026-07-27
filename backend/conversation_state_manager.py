"""In-memory Conversation State Manager.

This module provides a standalone, in-memory state manager for tracking
per-phone-number conversation state and temporary conversation data.

It intentionally has NO dependencies on databases, Redis, files, or any
other persistence layer. It is meant to be reused by later tasks that
implement the actual conversation flows (Supervisor Flow, Visitor Flow, etc.).

Usage:
    from backend.conversation_state_manager import (
        ConversationStateManager,
        ConversationState,
    )

    manager = ConversationStateManager()
    manager.set_state("201001111111", ConversationState.NORMAL_CHAT)
    state = manager.get_state("201001111111")
"""

from enum import Enum


class ConversationState(Enum):
    """Possible conversation states for a phone number."""

    NORMAL_CHAT = "normal_chat"
    SUPERVISOR_WAITING_ANNOUNCEMENT = "supervisor_waiting_announcement"
    SUPERVISOR_WAITING_TYPE_CONFIRMATION = "supervisor_waiting_type_confirmation"
    SUPERVISOR_WAITING_APPROVAL = "supervisor_waiting_approval"


class ConversationStateManager:
    """Manages conversation state and temporary data in memory only.

    Each phone number maps to a record of the form:

        {
            "state": ConversationState,
            "data": dict,
        }

    All data is stored in plain Python dictionaries and is lost when the
    process exits. This class is not thread-safe; callers operating across
    threads should add their own synchronization.
    """

    def __init__(self):
        # Internal in-memory store. Keyed by phone number (str).
        # Structure:
        #   {
        #       "<phone>": {
        #           "state": ConversationState,
        #           "data": {},
        #       },
        #       ...
        #   }
        self._store = {}

    # ------------------------------------------------------------------
    # State operations
    # ------------------------------------------------------------------
    def set_state(self, phone, state):
        """Set the current conversation state for a phone number.

        If no record exists yet, one is created with an empty data dict.
        """
        if not isinstance(state, ConversationState):
            raise TypeError(
                "state must be an instance of ConversationState, got %r" % (state,)
            )

        record = self._store.get(phone)
        if record is None:
            record = {"state": ConversationState.NORMAL_CHAT, "data": {}}
            self._store[phone] = record

        record["state"] = state

    def get_state(self, phone):
        """Return the current conversation state for a phone number.

        Returns ConversationState.NORMAL_CHAT if the phone number has no
        record yet (sensible default for normal chat flow).
        """
        record = self._store.get(phone)
        if record is None:
            return ConversationState.NORMAL_CHAT
        return record["state"]

    def has_state(self, phone):
        """Return True if a record (state/data) exists for this phone number."""
        return phone in self._store

    def clear_state(self, phone):
        """Reset the conversation state for a phone number to NORMAL_CHAT.

        The data dict is left untouched. If no record exists, this is a no-op.
        """
        record = self._store.get(phone)
        if record is None:
            return
        record["state"] = ConversationState.NORMAL_CHAT

    # ------------------------------------------------------------------
    # Data operations
    # ------------------------------------------------------------------
    def update_data(self, phone, data):
        """Merge `data` (a dict) into the phone number's temporary data.

        Existing keys are overwritten by keys present in `data`. If no record
        exists yet, one is created with NORMAL_CHAT state and an empty data
        dict before merging.
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dict, got %r" % (data,))

        record = self._store.get(phone)
        if record is None:
            record = {"state": ConversationState.NORMAL_CHAT, "data": {}}
            self._store[phone] = record

        record["data"].update(data)

    def get_data(self, phone):
        """Return the temporary conversation data dict for a phone number.

        Returns an empty dict if the phone number has no record yet.
        """
        record = self._store.get(phone)
        if record is None:
            return {}
        return record["data"]

    def clear_data(self, phone):
        """Remove all temporary conversation data for a phone number.

        The state is left untouched. If no record exists, this is a no-op.
        """
        record = self._store.get(phone)
        if record is None:
            return
        record["data"] = {}


# ----------------------------------------------------------------------
# Standalone test / demo
# ----------------------------------------------------------------------
if __name__ == "__main__":
    manager = ConversationStateManager()
    phone = "201001111111"

    # 1. set_state
    manager.set_state(phone, ConversationState.SUPERVISOR_WAITING_ANNOUNCEMENT)
    print("After set_state -> SUPERVISOR_WAITING_ANNOUNCEMENT")

    # 2. get_state
    print("get_state:", manager.get_state(phone).name)

    # 3. update_data
    manager.update_data(phone, {"announcement_text": "Hello everyone"})
    manager.update_data(phone, {"type": "info"})
    print("After update_data ->", manager.get_data(phone))

    # 4. get_data
    print("get_data:", manager.get_data(phone))

    # 5. clear_state
    manager.clear_state(phone)
    print("After clear_state, get_state:", manager.get_state(phone).name)

    # 6. clear_data
    manager.clear_data(phone)
    print("After clear_data, get_data:", manager.get_data(phone))

    # Sanity: has_state
    print("has_state:", manager.has_state(phone))