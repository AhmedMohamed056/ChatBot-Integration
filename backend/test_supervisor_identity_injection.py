#!/usr/bin/env python3
"""Test script for Supervisor Identity Injection - Phase 1"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_supervisor_identity_in_prompt():
    """Test that supervisor identity is injected into the prompt."""
    print("Testing supervisor identity injection in prompt...")

    from ai_context_builder import AIContext
    from prompt_builder import build_prompt

    # Create AIContext with supervisor info
    context = AIContext(
        supervisor={
            "supervisor_name": "Ahmed Mohamed",
            "phone": "+201234567890",
            "campaign_id": 1,
            "campaign_name": "Test Campaign",
            "campaign_status": "active",
            "current_campaign_version": 3,
            "conversation_state": "IDLE",
            "pending_draft": None
        },
        raw_message="من أنا؟"
    )

    # Build the prompt
    prompt = build_prompt(system_prompt="You are a helpful assistant.", context=context)

    # Verify supervisor identity message is present
    assert "You are speaking with an authorized campaign supervisor." in prompt, \
        "Prompt missing supervisor identity message"

    # Verify supervisor name is present
    assert "Supervisor Name: Ahmed Mohamed" in prompt, \
        "Prompt missing supervisor name"

    # Verify supervisor phone is present
    assert "Phone: +201234567890" in prompt, \
        "Prompt missing supervisor phone"

    # Verify campaign info is present
    assert "Campaign Name: Test Campaign" in prompt, \
        "Prompt missing campaign name"

    print("✓ Supervisor identity is correctly injected into prompt")
    print("\n--- Sample Prompt Output ---")
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    return True

def test_supervisor_identity_arabic_questions():
    """Test that the injected context allows Gemini to answer identity questions."""
    print("\nTesting Arabic identity questions with supervisor context...")

    from ai_context_builder import AIContext
    from prompt_builder import build_prompt

    # Test with Arabic questions
    test_messages = [
        "من أنا",
        "ما اسمي",
        "من أتحدث"
    ]

    for message in test_messages:
        context = AIContext(
            supervisor={
                "supervisor_name": "Ahmed Mohamed",
                "phone": "+201234567890",
            },
            raw_message=message
        )

        prompt = build_prompt(system_prompt="You are a helpful assistant.", context=context)

        # Verify the supervisor identity message is in the prompt
        assert "You are speaking with an authorized campaign supervisor." in prompt, \
            f"Prompt missing supervisor identity message for question: {message}"

        # Verify supervisor name is in the prompt
        assert "Supervisor Name: Ahmed Mohamed" in prompt, \
            f"Prompt missing supervisor name for question: {message}"

        print(f"  ✓ Question '{message}' has supervisor context in prompt")

    print("✓ All Arabic identity questions have supervisor context")
    return True

def test_no_supervisor_no_identity_message():
    """Test that when there's no supervisor, the identity message is not present."""
    print("\nTesting that non-supervisor prompts don't have identity message...")

    from ai_context_builder import AIContext
    from prompt_builder import build_prompt

    # Create AIContext without supervisor
    context = AIContext(
        raw_message="Hello"
    )

    prompt = build_prompt(system_prompt="You are a helpful assistant.", context=context)

    # Verify supervisor section is NOT present
    assert "You are speaking with an authorized campaign supervisor." not in prompt, \
        "Prompt should not have supervisor identity message when no supervisor"

    print("✓ Non-supervisor prompts correctly exclude identity message")
    return True

def main():
    """Run all tests."""
    print("=" * 70)
    print("Supervisor Identity Injection - Phase 1 Validation Tests")
    print("=" * 70)

    try:
        test_supervisor_identity_in_prompt()
        test_supervisor_identity_arabic_questions()
        test_no_supervisor_no_identity_message()

        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED!")
        print("=" * 70)
        print("\nSummary:")
        print("- Supervisor identity message is injected into prompts")
        print("- Supervisor name and phone are included in context")
        print("- Arabic identity questions (من أنا, ما اسمي, من أتحدث) have context")
        print("- Non-supervisor prompts don't have identity message")
        return 0

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())