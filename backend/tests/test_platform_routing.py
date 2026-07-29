"""Platform routing policy tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from db import init_db
from db.base import init_engine
from services.intent_router import Intent, detect_intent
from services.message_orchestrator import InboundMessage, MessageOrchestrator


class TestIntentRouter(unittest.TestCase):
    def test_confirm_ok_only_exact_token(self) -> None:
        self.assertEqual(detect_intent("OK", pending_confirmation=True).intent, Intent.CONFIRM_OK)
        self.assertNotEqual(
            detect_intent("yes", pending_confirmation=True).intent, Intent.CONFIRM_OK
        )


class TestMessageOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_group_supervisor_gets_knowledge_only_reply(self, get_visitor_flow: MagicMock) -> None:
        get_visitor_flow.return_value.handle_message.return_value = MagicMock(reply="ignored")
        orchestrator = MessageOrchestrator()
        with patch(
            "services.message_orchestrator.get_active_supervisor",
            return_value=MagicMock(id=1, phone_number="2010", display_name="Ali"),
        ):
            reply = orchestrator.handle(
                InboundMessage(
                    phone="201012345678",
                    message="create campaign",
                    chat_type="group",
                    external_chat_id="g1@g.us",
                )
            )
        self.assertIn("المحادثة الخاصة", reply)
        get_visitor_flow.return_value.handle_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
