"""Supervisor Conversation State Machine.

This module implements ONLY the reusable Supervisor conversation state
machine. It depends on:

- The in-memory `ConversationStateManager` from Task 16.
- The standalone `detect_advertisement_type` /
  `AdvertisementType` from Task 17.2.

It intentionally has NO integration with:

- Archive
- Gemini
- Prompt Builder
- Visitor Flow
- WhatsApp
- Any API or database
- Advertisement Merge Logic
- Approval Persistence

The flow is a strict linear state machine:

    NORMAL_CHAT
        ↓  (state set externally to enter the flow)
    SUPERVISOR_WAITING_ANNOUNCEMENT
        ↓  (handle_message)
    SUPERVISOR_WAITING_TYPE_CONFIRMATION
        ↓  (handle_message)
    SUPERVISOR_WAITING_APPROVAL
        ↓  (handle_message)
    NORMAL_CHAT

Public API
----------
The only public method is `handle_message(phone, message)`. Callers do
NOT need to call any "start" method on the flow. To enter the flow, the
caller simply sets the phone number's state to
`SUPERVISOR_WAITING_ANNOUNCEMENT` via the `ConversationStateManager`
(e.g. when a supervisor command is detected upstream). From that point
on, `handle_message` drives the entire flow.

Usage:
    from backend.conversation_state_manager import (
        ConversationStateManager,
        ConversationState,
    )
    from backend.supervisor_flow import SupervisorFlow

    manager = ConversationStateManager()
    flow = SupervisorFlow(manager)

    # Enter the flow (done by upstream routing logic, not by the flow):
    manager.set_state(phone, ConversationState.SUPERVISOR_WAITING_ANNOUNCEMENT)

    result = flow.handle_message(phone, "تم تعديل موعد التجمع")
    # result.reply -> "فهمت أن هذا الإعلان (UPDATE). هل هذا صحيح؟"
"""

from dataclasses import dataclass

from backend.advertisement_type_detector import (
    AdvertisementType,
    detect_advertisement_type,
)
from backend.conversation_state_manager import (
    ConversationStateManager,
    ConversationState,
)


# ----------------------------------------------------------------------
# Result object
# ----------------------------------------------------------------------
@dataclass
class SupervisorFlowResult:
    """Result returned by the Supervisor flow for a single message.

    Attributes:
        reply: The text reply that should be sent back to the user.
            May be an empty string when the flow did not handle the
            message (handled == False).
        next_state: The conversation state the phone number is in after
            processing this message.
        handled: True if the Supervisor flow handled this message. When
            False, the caller is free to handle the message using the
            normal chat flow.
    """

    reply: str = ""
    next_state: ConversationState = ConversationState.NORMAL_CHAT
    handled: bool = False


# ----------------------------------------------------------------------
# Arabic reply templates
# ----------------------------------------------------------------------
# Reply when the announcement text has been received. The detected type
# is interpolated dynamically from the detector — never hardcoded.
TYPE_CONFIRMATION_REPLY_TEMPLATE = "فهمت أن هذا الإعلان ({type}). هل هذا صحيح؟"

# Reply after type confirmation, asking for final approval.
APPROVAL_REQUEST_REPLY = "تم تسجيل نوع الإعلان. هل تعتمد نشر هذا الإعلان؟"

# Reply after final approval, when returning to NORMAL_CHAT.
APPROVAL_SUCCESS_REPLY = "تم اعتماد الإعلان بنجاح."


class SupervisorFlow:
    """Reusable Supervisor conversation state machine.

    The flow is driven by `handle_message`, which inspects the current
    conversation state for a phone number and advances the state machine
    one step. The flow only handles messages when the phone number is in
    one of the SUPERVISOR_* states.

    The flow contains NO announcement classification logic of its own.
    It delegates type detection to `detect_advertisement_type` and uses
    the returned value both for storage and for the confirmation reply.
    """

    def __init__(self, state_manager):
        """Initialize the flow.

        Args:
            state_manager: A ConversationStateManager instance (from
                Task 16) used to read/write per-phone state and
                temporary data.
        """
        if state_manager is None:
            raise ValueError("state_manager must not be None")
        if not isinstance(state_manager, ConversationStateManager):
            raise TypeError(
                "state_manager must be a ConversationStateManager, got %r"
                % (type(state_manager),)
            )

        self._state_manager = state_manager

    # ------------------------------------------------------------------
    # Public API (single entry point)
    # ------------------------------------------------------------------
    def handle_message(self, phone, message):
        """Process one incoming message for the given phone number.

        The behavior depends on the current conversation state:

        - SUPERVISOR_WAITING_ANNOUNCEMENT:
              Save the message as the announcement text, ask the
              detector for the announcement type, store the detected
              type, and ask the supervisor to confirm it.
        - SUPERVISOR_WAITING_TYPE_CONFIRMATION:
              Advance to waiting for approval.
        - SUPERVISOR_WAITING_APPROVAL:
              Return to NORMAL_CHAT and confirm success.
        - NORMAL_CHAT (or anything else):
              The Supervisor flow does not handle the message; returns
              handled=False so the caller can route it elsewhere.

        Args:
            phone: The phone number string.
            message: The incoming message text (str).

        Returns:
            SupervisorFlowResult describing the reply, next state, and
            whether the flow handled the message.
        """
        if message is None:
            message = ""
        message = str(message)

        state = self._state_manager.get_state(phone)

        if state == ConversationState.SUPERVISOR_WAITING_ANNOUNCEMENT:
            return self._handle_waiting_announcement(phone, message)

        if state == ConversationState.SUPERVISOR_WAITING_TYPE_CONFIRMATION:
            return self._handle_waiting_type_confirmation(phone, message)

        if state == ConversationState.SUPERVISOR_WAITING_APPROVAL:
            return self._handle_waiting_approval(phone, message)

        # NORMAL_CHAT or any non-supervisor state: not handled here.
        return SupervisorFlowResult(
            reply="",
            next_state=state,
            handled=False,
        )

    # ------------------------------------------------------------------
    # Internal state handlers
    # ------------------------------------------------------------------
    def _handle_waiting_announcement(self, phone, message):
        """SUPERVISOR_WAITING_ANNOUNCEMENT -> SUPERVISOR_WAITING_TYPE_CONFIRMATION.

        Saves the announcement text into temporary data, asks the
        detector for the type, stores the detected type, and asks the
        supervisor to confirm it. The type is NEVER hardcoded here —
        it always comes from `detect_advertisement_type`.
        """
        # Ask the detector for the announcement type. The flow itself
        # contains no classification logic.
        detected_type = detect_advertisement_type(message)

        # Save the announcement text and the detected type into the
        # temporary conversation data.
        self._state_manager.update_data(
            phone,
            {
                "announcement_text": message,
                "announcement_type": detected_type,
            },
        )

        self._state_manager.set_state(
            phone, ConversationState.SUPERVISOR_WAITING_TYPE_CONFIRMATION
        )

        reply = TYPE_CONFIRMATION_REPLY_TEMPLATE.format(type=detected_type.value)

        return SupervisorFlowResult(
            reply=reply,
            next_state=ConversationState.SUPERVISOR_WAITING_TYPE_CONFIRMATION,
            handled=True,
        )

    def _handle_waiting_type_confirmation(self, phone, message):
        """SUPERVISOR_WAITING_TYPE_CONFIRMATION -> SUPERVISOR_WAITING_APPROVAL.

        Records the supervisor's confirmation response and asks for the
        final approval.
        """
        self._state_manager.update_data(
            phone,
            {"type_confirmation_response": message},
        )

        self._state_manager.set_state(
            phone, ConversationState.SUPERVISOR_WAITING_APPROVAL
        )

        return SupervisorFlowResult(
            reply=APPROVAL_REQUEST_REPLY,
            next_state=ConversationState.SUPERVISOR_WAITING_APPROVAL,
            handled=True,
        )

    def _handle_waiting_approval(self, phone, message):
        """SUPERVISOR_WAITING_APPROVAL -> NORMAL_CHAT.

        Records the approval response, returns to NORMAL_CHAT, and
        replies with the success message.
        """
        self._state_manager.update_data(
            phone,
            {"approval_response": message, "approved": True},
        )

        self._state_manager.set_state(phone, ConversationState.NORMAL_CHAT)

        return SupervisorFlowResult(
            reply=APPROVAL_SUCCESS_REPLY,
            next_state=ConversationState.NORMAL_CHAT,
            handled=True,
        )


# ----------------------------------------------------------------------
# Standalone demo / verification (Task 17.2 scenarios)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    manager = ConversationStateManager()
    flow = SupervisorFlow(manager)
    phone = "201001111111"

    # ------------------------------------------------------------------
    # Scenario 1: NORMAL_CHAT -> enter flow -> WAITING_ANNOUNCEMENT
    # ------------------------------------------------------------------
    print("=== Scenario 1: enter supervisor flow ===")
    print("before state:", manager.get_state(phone).name)
    manager.set_state(phone, ConversationState.SUPERVISOR_WAITING_ANNOUNCEMENT)
    print("after  state:", manager.get_state(phone).name)

    # ------------------------------------------------------------------
    # Scenario 2: send "تم تعديل موعد التجمع" -> UPDATE
    # ------------------------------------------------------------------
    print("\n=== Scenario 2: send announcement (UPDATE) ===")
    r = flow.handle_message(phone, "تم تعديل موعد التجمع")
    print("state:", r.next_state.name, "| handled:", r.handled)
    print("reply:", r.reply)
    data = manager.get_data(phone)
    print(
        "data.announcement_type:",
        data.get("announcement_type"),
        "(value:",
        data.get("announcement_type").value if data.get("announcement_type") else None,
        ")",
    )
    assert r.next_state == ConversationState.SUPERVISOR_WAITING_TYPE_CONFIRMATION
    assert data.get("announcement_type") == AdvertisementType.UPDATE
    assert "(UPDATE)" in r.reply

    # ------------------------------------------------------------------
    # Scenario 3: confirm type -> WAITING_APPROVAL
    # ------------------------------------------------------------------
    print("\n=== Scenario 3: confirm type ===")
    r = flow.handle_message(phone, "نعم")
    print("state:", r.next_state.name, "| reply:", r.reply, "| handled:", r.handled)
    assert r.next_state == ConversationState.SUPERVISOR_WAITING_APPROVAL

    # ------------------------------------------------------------------
    # Scenario 4: approve -> NORMAL_CHAT
    # ------------------------------------------------------------------
    print("\n=== Scenario 4: approve ===")
    r = flow.handle_message(phone, "نعم اعتمد")
    print("state:", r.next_state.name, "| reply:", r.reply, "| handled:", r.handled)
    assert r.next_state == ConversationState.NORMAL_CHAT
    assert r.reply == APPROVAL_SUCCESS_REPLY

    # ------------------------------------------------------------------
    # After completion: NORMAL_CHAT is not handled by the supervisor flow
    # ------------------------------------------------------------------
    print("\n=== After completion: normal chat not handled ===")
    r = flow.handle_message(phone, "مرحبا")
    print("state:", r.next_state.name, "| handled:", r.handled)
    assert r.handled is False

    print("\nALL SCENARIOS PASSED")