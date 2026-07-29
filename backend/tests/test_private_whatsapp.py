"""Private WhatsApp access policy tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from db import init_db
from db.base import init_engine
from services.message_orchestrator import InboundMessage, MessageOrchestrator
from services.runtime_settings import set_runtime_setting


class TestPrivateWhatsAppAccess(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()
        set_runtime_setting("private_unauthorized_mode", "ignore")

    @patch("services.message_orchestrator.authorize_private_sender", return_value=None)
    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_no_visitor_flow_for_unknown_private(self, visitor_flow, _sup) -> None:
        orchestrator = MessageOrchestrator()
        reply = orchestrator.handle(
            InboundMessage(
                phone="966500000000",
                message="hello",
                chat_type="private",
            )
        )
        self.assertEqual(reply, "")
        visitor_flow.return_value.handle_message.assert_not_called()

    @patch("services.message_orchestrator.authorize_private_sender", return_value=None)
    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_message_mode_rejection_text(self, visitor_flow, _sup) -> None:
        set_runtime_setting("private_unauthorized_mode", "message")
        orchestrator = MessageOrchestrator()
        reply = orchestrator.handle(
            InboundMessage(
                phone="966500000000",
                message="hello",
                chat_type="private",
            )
        )
        self.assertIn("not registered", reply.lower())
        visitor_flow.return_value.handle_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
