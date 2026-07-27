"""Tests for VisitorFlow orchestrator.

This module contains tests for the VisitorFlow class to verify:
- The complete flow: phone -> message -> AIContextBuilder -> PromptBuilder -> GeminiClient -> reply
- Error handling when components fail
- Proper return of VisitorFlowResult
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from visitor_flow import VisitorFlow, VisitorFlowResult
from gemini_client import GeminiClient, GeminiClientError

class TestVisitorFlow(unittest.TestCase):
    """Test cases for VisitorFlow orchestrator."""

    def setUp(self):
        """Set up test fixtures."""
        # Ensure no API key is set to test error handling
        os.environ.pop('GOOGLE_API_KEY', None)

    def test_visitor_flow_result_dataclass(self):
        """Test VisitorFlowResult dataclass creation."""
        result = VisitorFlowResult(reply="Test reply", handled=True)
        self.assertEqual(result.reply, "Test reply")
        self.assertTrue(result.handled)

        result2 = VisitorFlowResult(reply="Error", handled=False)
        self.assertEqual(result2.reply, "Error")
        self.assertFalse(result2.handled)

    def test_handle_message_gemini_unavailable(self):
        """Test that handle_message returns fallback when Gemini is unavailable."""
        flow = VisitorFlow()

        result = flow.handle_message(
            phone="+201234567890",
            message="مرحبا"
        )

        self.assertIsInstance(result, VisitorFlowResult)
        self.assertFalse(result.handled)
        self.assertEqual(result.reply, "أعتذر، حدث خطأ أثناء معالجة الطلب.")

    @patch('visitor_flow.GeminiClient')
    def test_handle_message_with_mock_gemini(self, mock_gemini_class):
        """Test handle_message with a mocked GeminiClient."""
        # Setup mock
        mock_client = MagicMock(spec=GeminiClient)
        mock_client.generate.return_value = "Mock response"
        mock_gemini_class.return_value = mock_client

        flow = VisitorFlow(gemini_client=mock_client)

        result = flow.handle_message(
            phone="+201234567890",
            message="مرحبا"
        )

        self.assertIsInstance(result, VisitorFlowResult)
        self.assertTrue(result.handled)
        self.assertEqual(result.reply, "Mock response")
        mock_client.generate.assert_called_once()

    @patch('visitor_flow.GeminiClient')
    def test_handle_message_gemini_error(self, mock_gemini_class):
        """Test handle_message when GeminiClient raises an error."""
        # Setup mock to raise error
        mock_client = MagicMock(spec=GeminiClient)
        mock_client.generate.side_effect = GeminiClientError("API Error")
        mock_gemini_class.return_value = mock_client

        flow = VisitorFlow(gemini_client=mock_client)

        result = flow.handle_message(
            phone="+201234567890",
            message="مرحبا"
        )

        self.assertIsInstance(result, VisitorFlowResult)
        self.assertFalse(result.handled)
        self.assertEqual(result.reply, "أعتذر، حدث خطأ أثناء معالجة الطلب.")

    @patch('visitor_flow.build_visitor_system_prompt')
    @patch('visitor_flow.GeminiClient')
    def test_handle_message_prompt_file_not_found(self, mock_gemini_class, mock_prompt):
        """Test handle_message when system prompt file is not found."""
        # Setup mocks
        mock_prompt.side_effect = FileNotFoundError("Prompt file not found")
        mock_client = MagicMock(spec=GeminiClient)
        mock_gemini_class.return_value = mock_client

        flow = VisitorFlow(gemini_client=mock_client)

        result = flow.handle_message(
            phone="+201234567890",
            message="مرحبا"
        )

        self.assertIsInstance(result, VisitorFlowResult)
        self.assertFalse(result.handled)
        self.assertEqual(result.reply, "أعتذر، حدث خطأ أثناء معالجة الطلب.")

    @patch('visitor_flow.build_ai_context')
    @patch('visitor_flow.build_visitor_system_prompt')
    @patch('visitor_flow.build_prompt')
    @patch('visitor_flow.GeminiClient')
    def test_complete_flow_integration(self, mock_gemini_class, mock_build_prompt,
                                       mock_system_prompt, mock_build_context):
        """Test the complete flow with all components mocked."""
        # Setup mocks
        mock_context = MagicMock()
        mock_build_context.return_value = mock_context

        mock_system_prompt.return_value = "System prompt text"

        mock_build_prompt.return_value = "Full prompt with system + context + message"

        mock_client = MagicMock(spec=GeminiClient)
        mock_client.generate.return_value = "Test response"
        mock_gemini_class.return_value = mock_client

        flow = VisitorFlow(gemini_client=mock_client)

        result = flow.handle_message(
            phone="+201234567890",
            message="مرحبا"
        )

        # Verify all components were called
        mock_build_context.assert_called_once_with(
            message="مرحبا",
            phone="+201234567890"
        )
        mock_system_prompt.assert_called_once()
        mock_build_prompt.assert_called_once_with(
            system_prompt="System prompt text",
            context=mock_context
        )
        mock_client.generate.assert_called_once_with(
            system_prompt="",
            user_prompt="Full prompt with system + context + message"
        )

        # Verify result
        self.assertIsInstance(result, VisitorFlowResult)
        self.assertTrue(result.handled)
        self.assertEqual(result.reply, "Test response")

def demo():
    """Standalone demo for VisitorFlow.

    Demonstrates the complete flow:
    phone -> message -> AIContextBuilder -> PromptBuilder -> GeminiClient -> reply

    Prints the returned VisitorFlowResult.
    If Gemini is unavailable, gracefully returns the fallback error message.
    """
    import logging

    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("VisitorFlow Demo")
    print("=" * 60)

    # Create the flow orchestrator
    flow = VisitorFlow()

    # Test with a sample message
    test_phone = "+201234567890"
    test_message = "مرحبا، كيف حالك؟"

    print(f"\nPhone: {test_phone}")
    print(f"Message: {test_message}")
    print("\n" + "-" * 60)

    # Process the message
    result = flow.handle_message(
        phone=test_phone,
        message=test_message
    )

    # Print the result
    print("\nVisitorFlowResult:")
    print(f"  handled: {result.handled}")
    print(f"  reply: {result.reply}")
    print("\n" + "=" * 60)

if __name__ == "__main__":
    # Run demo if executed directly
    demo()