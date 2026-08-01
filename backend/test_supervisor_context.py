#!/usr/bin/env python3
"""Test script for Supervisor Context Injection (Phase 2.1)"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_supervisor_context_structure():
    """Test that SupervisorContext has all required fields."""
    print("Testing SupervisorContext structure...")

    from services.supervisor_context_service import SupervisorContext

    # Create a test context
    context = SupervisorContext(
        supervisor_name="Ahmed Mohamed",
        phone="+201234567890",
        campaign_id=1,
        campaign_name="Test Campaign",
        campaign_status="active",
        current_campaign_version=3,
        conversation_state="IDLE",
        pending_draft={"operation": "update", "description": "Test"}
    )

    # Check all required fields exist
    required_fields = [
        'supervisor_name', 'phone', 'campaign_id', 'campaign_name',
        'campaign_status', 'current_campaign_version', 'conversation_state', 'pending_draft'
    ]

    for field in required_fields:
        assert hasattr(context, field), f"Missing field: {field}"
        assert field in context.to_dict(), f"Missing field in to_dict(): {field}"

    print("✓ SupervisorContext structure is correct")

def test_ai_context_supervisor_field():
    """Test that AIContext has supervisor field."""
    print("Testing AIContext supervisor field...")

    from ai_context_builder import AIContext

    # Create AIContext with supervisor
    context = AIContext(
        supervisor={"supervisor_name": "Test", "phone": "+123"}
    )

    assert hasattr(context, 'supervisor'), "AIContext missing supervisor field"
    assert context.supervisor == {"supervisor_name": "Test", "phone": "+123"}

    # Test to_dict includes supervisor
    context_dict = context.to_dict()
    assert 'supervisor' in context_dict, "AIContext.to_dict() missing supervisor"

    print("✓ AIContext has supervisor field")

def test_build_context_with_supervisor():
    """Test that build_context accepts supervisor parameter."""
    print("Testing build_context with supervisor...")

    from ai_context_builder import build_context
    from services.supervisor_context_service import SupervisorContext

    supervisor = SupervisorContext(
        supervisor_name="Test Supervisor",
        phone="+1234567890"
    )

    context = build_context(
        message="Hello",
        phone="+1234567890",
        supervisor=supervisor
    )

    assert context.supervisor is not None, "build_context didn't set supervisor"
    assert context.supervisor['supervisor_name'] == "Test Supervisor"

    print("✓ build_context accepts supervisor parameter")

def test_prompt_builder_supervisor_section():
    """Test that prompt builder includes supervisor section with identity message."""
    print("Testing prompt builder supervisor section...")

    from ai_context_builder import AIContext
    from prompt_builder import build_prompt

    context = AIContext(
        supervisor={
            "supervisor_name": "Ahmed",
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

    prompt = build_prompt(system_prompt="You are a helpful assistant.", context=context)

    # Check that supervisor section is in the prompt
    assert "SUPERVISOR" in prompt, "Prompt missing SUPERVISOR section"
    assert "You are speaking with an authorized campaign supervisor." in prompt, "Prompt missing supervisor identity message"
    assert "Supervisor Name: Ahmed" in prompt, "Prompt missing supervisor name"
    assert "Phone: +201234567890" in prompt, "Prompt missing supervisor phone"
    assert "Campaign Name: Test Campaign" in prompt, "Prompt missing campaign name"

    print("✓ Prompt builder includes supervisor section with identity message")

def test_visitor_flow_with_supervisor():
    """Test that VisitorFlow can handle supervisor context."""
    print("Testing VisitorFlow with supervisor context...")

    from visitor_flow import VisitorFlow, VisitorFlowResult
    from services.supervisor_context_service import SupervisorContext

    # Create a mock supervisor context
    supervisor = SupervisorContext(
        supervisor_name="Test Supervisor",
        phone="+1234567890",
        campaign_id=1,
        campaign_name="Test Campaign"
    )

    # Create VisitorFlow instance
    flow = VisitorFlow()

    # Check that the method exists
    assert hasattr(flow, 'handle_message_with_supervisor'), \
        "VisitorFlow missing handle_message_with_supervisor method"

    print("✓ VisitorFlow has supervisor handling method")

def main():
    """Run all tests."""
    print("=" * 60)
    print("Supervisor Context Injection - Validation Tests")
    print("=" * 60)

    try:
        test_supervisor_context_structure()
        test_ai_context_supervisor_field()
        test_build_context_with_supervisor()
        test_prompt_builder_supervisor_section()
        test_visitor_flow_with_supervisor()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())