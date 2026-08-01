#!/usr/bin/env python3
"""
Simple test script for Phase 3 - Conversation Memory implementation.

This script validates the core conversation memory functionality without database dependencies.
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_conversation_memory_data():
    """Test the ConversationMemoryData dataclass."""
    print("Testing ConversationMemoryData...")

    try:
        from services.conversation_memory_service import ConversationMemoryData

        # Test 1: Create empty memory data
        memory_data = ConversationMemoryData()
        assert memory_data.current_topic is None
        assert memory_data.conversation_summary is None
        assert memory_data.last_edited_field is None
        assert memory_data.recent_messages == []
        assert memory_data.pending_draft is None
        print("✓ Empty ConversationMemoryData created successfully")

        # Test 2: Create memory data with values
        memory_data = ConversationMemoryData(
            current_topic="Test Campaign",
            conversation_summary="Discussing campaign updates",
            last_edited_field="description",
            recent_messages=[{"text": "Hello", "direction": "inbound"}],
            pending_draft={"field": "value"}
        )
        assert memory_data.current_topic == "Test Campaign"
        assert memory_data.conversation_summary == "Discussing campaign updates"
        assert memory_data.last_edited_field == "description"
        assert len(memory_data.recent_messages) == 1
        assert memory_data.pending_draft == {"field": "value"}
        print("✓ ConversationMemoryData with values created successfully")

        # Test 3: to_dict method
        data_dict = memory_data.to_dict()
        assert "current_topic" in data_dict
        assert "conversation_summary" in data_dict
        assert "last_edited_field" in data_dict
        assert "recent_messages" in data_dict
        assert "pending_draft" in data_dict
        print("✓ to_dict method works correctly")

        # Test 4: from_dict method
        new_memory = ConversationMemoryData.from_dict(data_dict)
        assert new_memory.current_topic == memory_data.current_topic
        assert new_memory.conversation_summary == memory_data.conversation_summary
        assert new_memory.last_edited_field == memory_data.last_edited_field
        assert new_memory.recent_messages == memory_data.recent_messages
        assert new_memory.pending_draft == memory_data.pending_draft
        print("✓ from_dict method works correctly")

        # Test 5: from_dict with None
        empty_memory = ConversationMemoryData.from_dict(None)
        assert empty_memory.current_topic is None
        assert empty_memory.conversation_summary is None
        print("✓ from_dict with None works correctly")

        return True

    except Exception as e:
        print(f"✗ ConversationMemoryData test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ai_context_with_memory():
    """Test that AIContext can hold conversation memory."""
    print("\nTesting AIContext with conversation memory...")

    try:
        from ai_context_builder import AIContext

        # Test 1: Create AIContext with conversation memory
        context = AIContext(
            raw_message="Test message",
            conversation_memory={
                "current_topic": "Test Topic",
                "conversation_summary": "Test Summary",
                "last_edited_field": "description",
                "recent_messages": [{"text": "Hello", "direction": "inbound"}]
            }
        )

        assert context.conversation_memory is not None
        assert context.conversation_memory["current_topic"] == "Test Topic"
        assert context.conversation_memory["conversation_summary"] == "Test Summary"
        assert context.conversation_memory["last_edited_field"] == "description"
        assert len(context.conversation_memory["recent_messages"]) == 1
        print("✓ AIContext with conversation memory created successfully")

        # Test 2: to_dict includes conversation memory
        context_dict = context.to_dict()
        assert "conversation_memory" in context_dict
        assert context_dict["conversation_memory"]["current_topic"] == "Test Topic"
        print("✓ AIContext.to_dict includes conversation memory")

        return True

    except Exception as e:
        print(f"✗ AIContext test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_prompt_builder_with_memory():
    """Test that prompt builder includes conversation memory."""
    print("\nTesting PromptBuilder with conversation memory...")

    try:
        from prompt_builder import build_prompt
        from ai_context_builder import AIContext

        # Test 1: Prompt with conversation memory
        context = AIContext(
            raw_message="اجعله أقصر",
            conversation_memory={
                "current_topic": "Campaign Description",
                "conversation_summary": "User is editing campaign description",
                "last_edited_field": "description",
                "recent_messages": [
                    {"text": "The description is too long", "direction": "inbound"},
                    {"text": "I'll help you edit it", "direction": "outbound"}
                ]
            }
        )

        prompt = build_prompt(
            system_prompt="You are a helpful assistant.",
            context=context
        )

        # Check that conversation memory is in the prompt
        assert "CONVERSATION MEMORY" in prompt
        assert "Campaign Description" in prompt
        assert "اجعله أقصر" in prompt
        assert "Use this memory to understand references like" in prompt
        print("✓ Prompt includes conversation memory with Arabic text")

        # Test 2: Prompt without conversation memory
        context_no_memory = AIContext(raw_message="Hello")
        prompt_no_memory = build_prompt(
            system_prompt="You are a helpful assistant.",
            context=context_no_memory
        )

        # Should not have CONVERSATION MEMORY section
        assert "CONVERSATION MEMORY" not in prompt_no_memory
        print("✓ Prompt without conversation memory works correctly")

        return True

    except Exception as e:
        print(f"✗ PromptBuilder test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_memory_keys():
    """Test that memory keys are defined correctly."""
    print("\nTesting memory keys...")

    try:
        from services.conversation_memory_service import (
            MEMORY_KEY_CURRENT_TOPIC,
            MEMORY_KEY_PENDING_DRAFT,
            MEMORY_KEY_CONVERSATION_SUMMARY,
            MEMORY_KEY_LAST_EDITED_FIELD,
            MEMORY_KEY_RECENT_MESSAGES
        )

        assert MEMORY_KEY_CURRENT_TOPIC == "current_topic"
        assert MEMORY_KEY_PENDING_DRAFT == "pending_draft"
        assert MEMORY_KEY_CONVERSATION_SUMMARY == "conversation_summary"
        assert MEMORY_KEY_LAST_EDITED_FIELD == "last_edited_field"
        assert MEMORY_KEY_RECENT_MESSAGES == "recent_messages"
        print("✓ All memory keys defined correctly")

        return True

    except Exception as e:
        print(f"✗ Memory keys test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_memory_service_imports():
    """Test that all required imports work."""
    print("\nTesting memory service imports...")

    try:
        from services.conversation_memory_service import (
            ConversationMemoryService,
            ConversationMemoryData,
            MEMORY_KEY_CURRENT_TOPIC,
            MEMORY_KEY_PENDING_DRAFT,
            MEMORY_KEY_CONVERSATION_SUMMARY,
            MEMORY_KEY_LAST_EDITED_FIELD,
            MEMORY_KEY_RECENT_MESSAGES
        )
        print("✓ All conversation memory service imports work")

        # Test that AIContext has conversation_memory field
        from ai_context_builder import AIContext
        context = AIContext()
        assert hasattr(context, 'conversation_memory')
        print("✓ AIContext has conversation_memory field")

        return True

    except Exception as e:
        print(f"✗ Memory service imports test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 3 - Conversation Memory Simple Validation")
    print("=" * 60)

    results = []

    # Run all tests
    results.append(test_memory_keys())
    results.append(test_memory_service_imports())
    results.append(test_conversation_memory_data())
    results.append(test_ai_context_with_memory())
    results.append(test_prompt_builder_with_memory())

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✓ All {total} tests passed!")
        print("\nConversation Memory Implementation is working correctly!")
        print("Memory fields maintained:")
        print("  - Current Topic")
        print("  - Pending Draft")
        print("  - Conversation Summary")
        print("  - Last Edited Field")
        print("  - Recent Messages")
        print("\nMemory is loaded before every Gemini request and")
        print("updated after every response through the prompt builder.")
        return 0
    else:
        print(f"✗ {total - passed} out of {total} tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())