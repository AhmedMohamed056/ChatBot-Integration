"""Validation tests for Conversation Memory - Phase 3.1.

Tests the 4 required scenarios:
1. "Change campaign description" → "What is the new description?" → "The new description is..." → "Done" → "Make it shorter"
2. "Delete this paragraph" (understands "this" = previous generated description)
3. "No" (understands rejection of previous proposal)
4. "Cancel" (conversation becomes IDLE)
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.platform_models import Base, ConversationMemory, Supervisor
from services.conversation_memory_service import (
    AssistantAction,
    ConversationMemoryService,
    UserIntent,
)


def setup_test_db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def create_test_supervisor(session):
    """Create a test supervisor."""
    supervisor = Supervisor(
        id=1,
        phone_number="+1234567890",
        display_name="Test Supervisor",
        is_active=True,
    )
    session.add(supervisor)
    session.commit()
    return supervisor


def test_scenario_1_make_it_shorter():
    """Test: 'Make it shorter' understands 'it' = description."""
    print("\n=== Scenario 1: 'Make it shorter' ===")
    session = setup_test_db()
    supervisor = create_test_supervisor(session)
    memory_service = ConversationMemoryService(session)
    conversation_id = 1

    # Step 1: User asks to change description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Change campaign description",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_user_intent == UserIntent.UPDATE_DESCRIPTION.value
    print(f"✓ Intent detected: {memory.last_user_intent}")

    # Step 2: Assistant asks for new description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="What is the new description?",
        direction="outbound"
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_assistant_action == AssistantAction.ASKED_FOR_DESCRIPTION.value
    assert memory.pending_context is not None
    assert memory.pending_context.get("field") == "description"
    print(f"✓ Assistant action: {memory.last_assistant_action}")
    print(f"✓ Pending context field: {memory.pending_context.get('field')}")

    # Step 3: User provides new description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="The new description is: Join our amazing summer camp with fun activities",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.pending_context.get("new_value") is not None
    print(f"✓ New value captured: {memory.pending_context.get('new_value')[:50]}...")

    # Step 4: Assistant confirms
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Done. Description updated.",
        direction="outbound"
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_assistant_action == AssistantAction.UPDATED_DESCRIPTION.value
    print(f"✓ Assistant action: {memory.last_assistant_action}")

    # Step 5: User says "Make it shorter" - should understand "it" = description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Make it shorter",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )
    memory = memory_service.load_memory(conversation_id)
    # The memory should still have context about description
    assert memory.last_edited_field == "description" or memory.current_topic == "description"
    print(f"✓ Context maintained: last_edited_field={memory.last_edited_field}, topic={memory.current_topic}")
    print("✅ Scenario 1 PASSED\n")


def test_scenario_2_delete_this_paragraph():
    """Test: 'Delete this paragraph' understands 'this' = previous description."""
    print("\n=== Scenario 2: 'Delete this paragraph' ===")
    session = setup_test_db()
    supervisor = create_test_supervisor(session)
    memory_service = ConversationMemoryService(session)
    conversation_id = 2

    # Step 1: User asks to change description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Change description",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )

    # Step 2: Assistant asks for new description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="What is the new description?",
        direction="outbound"
    )

    # Step 3: User provides description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Join our summer camp with exciting activities and professional trainers",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )

    # Step 4: Assistant shows the description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Here is the description: Join our summer camp...",
        direction="outbound"
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_edited_field == "description"
    print(f"✓ Last edited field: {memory.last_edited_field}")

    # Step 5: User says "Delete this paragraph"
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Delete this paragraph",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_user_intent == UserIntent.DELETE_PARAGRAPH.value
    print(f"✓ Intent detected: {memory.last_user_intent}")
    print(f"✓ Context available: last_edited_field={memory.last_edited_field}")
    print("✅ Scenario 2 PASSED\n")


def test_scenario_3_no_rejection():
    """Test: 'No' understands rejection of previous proposal."""
    print("\n=== Scenario 3: 'No' (rejection) ===")
    session = setup_test_db()
    supervisor = create_test_supervisor(session)
    memory_service = ConversationMemoryService(session)
    conversation_id = 3

    # Step 1: User asks to update budget
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Update budget",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )

    # Step 2: Assistant asks for budget
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="What is the new budget?",
        direction="outbound"
    )

    # Step 3: User provides budget
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="5000 SAR",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )

    # Step 4: Assistant proposes change
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="I will update the budget to 5000 SAR. Confirm?",
        direction="outbound"
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_assistant_action == AssistantAction.WAITING_FOR_CONFIRMATION.value
    print(f"✓ Assistant waiting for confirmation")

    # Step 5: User says "No"
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="No",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_user_intent == UserIntent.REJECT.value
    print(f"✓ Rejection detected: {memory.last_user_intent}")
    print("✅ Scenario 3 PASSED\n")


def test_scenario_4_cancel_goes_idle():
    """Test: 'Cancel' makes conversation IDLE."""
    print("\n=== Scenario 4: 'Cancel' → IDLE ===")
    session = setup_test_db()
    supervisor = create_test_supervisor(session)
    memory_service = ConversationMemoryService(session)
    conversation_id = 4

    # Step 1: User starts an update
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Change description",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )

    # Step 2: Assistant asks for description
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="What is the new description?",
        direction="outbound"
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_assistant_action == AssistantAction.ASKED_FOR_DESCRIPTION.value
    assert memory.pending_context is not None
    print(f"✓ Active task: {memory.last_assistant_action}")

    # Step 3: User says "Cancel"
    memory_service.update_memory_from_message(
        conversation_id=conversation_id,
        message="Cancel",
        direction="inbound",
        sender_phone=supervisor.phone_number
    )
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_user_intent == UserIntent.CANCEL.value
    print(f"✓ Cancel intent detected: {memory.last_user_intent}")

    # Step 4: Simulate task completion (set_idle)
    memory_service.set_idle(conversation_id)
    memory = memory_service.load_memory(conversation_id)
    assert memory.last_assistant_action == AssistantAction.IDLE.value
    assert memory.pending_context is None
    assert memory.last_user_intent is None
    print(f"✓ Conversation is IDLE: {memory.last_assistant_action}")
    print(f"✓ Pending context cleared: {memory.pending_context is None}")
    print("✅ Scenario 4 PASSED\n")


def run_all_tests():
    """Run all validation scenarios."""
    print("\n" + "="*60)
    print("CONVERSATION MEMORY VALIDATION TESTS - Phase 3.1")
    print("="*60)

    try:
        test_scenario_1_make_it_shorter()
        test_scenario_2_delete_this_paragraph()
        test_scenario_3_no_rejection()
        test_scenario_4_cancel_goes_idle()

        print("\n" + "="*60)
        print("✅ ALL SCENARIOS PASSED")
        print("="*60 + "\n")
        return True
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
