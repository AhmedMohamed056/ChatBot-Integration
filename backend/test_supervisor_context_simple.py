#!/usr/bin/env python3
"""Simple test script for Supervisor Context Injection (Phase 2.1) - No DB dependencies"""

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

    # Verify the values
    assert context.supervisor_name == "Ahmed Mohamed"
    assert context.phone == "+201234567890"
    assert context.campaign_id == 1
    assert context.campaign_name == "Test Campaign"
    assert context.campaign_status == "active"
    assert context.current_campaign_version == 3
    assert context.conversation_state == "IDLE"
    assert context.pending_draft == {"operation": "update", "description": "Test"}

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
    assert context_dict['supervisor'] == {"supervisor_name": "Test", "phone": "+123"}

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

    # Call build_context with supervisor but no phone to avoid DB calls
    context = build_context(
        message="Hello",
        phone=None,  # No phone to avoid DB calls
        supervisor=supervisor
    )

    assert context.supervisor is not None, "build_context didn't set supervisor"
    assert context.supervisor['supervisor_name'] == "Test Supervisor"
    assert context.supervisor['phone'] == "+1234567890"

    print("✓ build_context accepts supervisor parameter")

def test_prompt_builder_supervisor_section():
    """Test that prompt builder includes supervisor section."""
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
    assert "Supervisor Name: Ahmed" in prompt, "Prompt missing supervisor name"
    assert "Campaign Name: Test Campaign" in prompt, "Prompt missing campaign name"
    assert "Campaign Status: active" in prompt, "Prompt missing campaign status"
    assert "Current Campaign Version: 3" in prompt, "Prompt missing campaign version"

    print("✓ Prompt builder includes supervisor section")

def test_supervisor_section_priority():
    """Test that supervisor section takes priority over visitor section."""
    print("Testing supervisor section priority...")

    from ai_context_builder import AIContext
    from prompt_builder import build_prompt

    context = AIContext(
        supervisor={
            "supervisor_name": "Supervisor Ahmed",
            "phone": "+201234567890",
            "campaign_name": "Supervisor Campaign"
        },
        visitor={
            "visitor_name": "Visitor Ali",
            "phone": "+201234567891",
            "campaign_name": "Visitor Campaign"
        },
        raw_message="Test message"
    )

    prompt = build_prompt(system_prompt="Test", context=context)

    # Both sections should be present
    assert "SUPERVISOR" in prompt, "Prompt missing SUPERVISOR section"
    assert "VISITOR" in prompt, "Prompt missing VISITOR section"

    # Supervisor should appear before visitor
    supervisor_pos = prompt.find("SUPERVISOR")
    visitor_pos = prompt.find("VISITOR")
    assert supervisor_pos < visitor_pos, "SUPERVISOR section should appear before VISITOR section"

    print("✓ Supervisor section has correct priority")

def test_supervisor_context_serialization():
    """Test SupervisorContext serialization."""
    print("Testing SupervisorContext serialization...")

    from services.supervisor_context_service import SupervisorContext

    context = SupervisorContext(
        supervisor_name="Test",
        phone="+123",
        campaign_id=1,
        campaign_name="Test Campaign",
        campaign_status="active",
        current_campaign_version=2,
        conversation_state="COLLECTING",
        pending_draft={"field": "value"}
    )

    # Test to_dict
    context_dict = context.to_dict()
    assert isinstance(context_dict, dict)
    assert len(context_dict) == 8  # All 8 fields

    # Test that all values are correctly serialized
    assert context_dict['supervisor_name'] == "Test"
    assert context_dict['phone'] == "+123"
    assert context_dict['campaign_id'] == 1
    assert context_dict['campaign_name'] == "Test Campaign"
    assert context_dict['campaign_status'] == "active"
    assert context_dict['current_campaign_version'] == 2
    assert context_dict['conversation_state'] == "COLLECTING"
    assert context_dict['pending_draft'] == {"field": "value"}

    print("✓ SupervisorContext serialization works correctly")

def main():
    """Run all tests."""
    print("=" * 60)
    print("Supervisor Context Injection - Simple Validation Tests")
    print("=" * 60)

    try:
        test_supervisor_context_structure()
        test_ai_context_supervisor_field()
        test_build_context_with_supervisor()
        test_prompt_builder_supervisor_section()
        test_supervisor_section_priority()
        test_supervisor_context_serialization()

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