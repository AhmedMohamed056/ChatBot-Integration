"""Platform routing policy tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from db import init_db
from db.base import init_engine
from services.intent_router import Intent, detect_intent
from services.message_orchestrator import InboundMessage, MessageOrchestrator
from services.runtime_settings import set_runtime_setting


class TestIntentRouter(unittest.TestCase):
    def test_confirm_accepts_production_tokens(self) -> None:
        for token in ("OK", "yes", "Approve", "Confirm", "نعم", "موافق"):
            with self.subTest(token=token):
                self.assertEqual(
                    detect_intent(token, pending_confirmation=True).intent,
                    Intent.CONFIRM_OK,
                )


class TestMessageOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()
        set_runtime_setting("private_unauthorized_mode", "ignore")

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_group_supervisor_campaign_intent_refused(self, get_visitor_flow: MagicMock) -> None:
        get_visitor_flow.return_value.handle_message.return_value = MagicMock(reply="ignored")
        orchestrator = MessageOrchestrator()
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

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_group_supervisor_knowledge_uses_rag(self, get_visitor_flow: MagicMock) -> None:
        get_visitor_flow.return_value.handle_message.return_value = MagicMock(
            reply="knowledge answer"
        )
        orchestrator = MessageOrchestrator()
        reply = orchestrator.handle(
            InboundMessage(
                phone="201012345678",
                message="What time is Maghrib?",
                chat_type="group",
                external_chat_id="g1@g.us",
            )
        )
        self.assertEqual(reply, "knowledge answer")
        get_visitor_flow.return_value.handle_message.assert_called_once()

    def test_private_non_supervisor_ignored(self) -> None:
        orchestrator = MessageOrchestrator()
        with patch(
            "services.message_orchestrator.authorize_private_sender",
            return_value=None,
        ):
            reply = orchestrator.handle(
                InboundMessage(
                    phone="201099999999",
                    message="hello",
                    chat_type="private",
                    external_chat_id="201099999999@c.us",
                )
            )
        self.assertEqual(reply, "")


if __name__ == "__main__":
    unittest.main()
