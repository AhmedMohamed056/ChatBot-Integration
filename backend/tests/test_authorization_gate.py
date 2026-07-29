"""Strict WhatsApp private authorization gate tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from openpyxl import Workbook
from sqlalchemy import func, select

from db import init_db
from db.base import get_session, init_engine
from db.models import Campaign
from db.platform_models import Conversation, ConversationMemory, ConversationState, Message
from db.repositories.platform_repository import SupervisorRepository
from services.message_orchestrator import InboundMessage, MessageOrchestrator
from services.runtime_settings import set_runtime_setting
from services.supervisor_import_service import activate_supervisor_import


def _counts(session):
    return {
        "conversations": session.scalar(select(func.count()).select_from(Conversation)) or 0,
        "messages": session.scalar(select(func.count()).select_from(Message)) or 0,
        "states": session.scalar(select(func.count()).select_from(ConversationState)) or 0,
        "memories": session.scalar(select(func.count()).select_from(ConversationMemory)) or 0,
    }


class TestPrivateAuthorizationGate(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()
        set_runtime_setting("private_unauthorized_mode", "ignore")

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_unknown_private_no_reply_no_db_writes(self, visitor_flow: MagicMock) -> None:
        visitor_flow.return_value.handle_message.return_value = MagicMock(reply="SHOULD_NOT")
        orch = MessageOrchestrator()
        before = None
        with get_session() as session:
            before = _counts(session)

        reply = orch.handle(
            InboundMessage(
                phone="966509999999",
                message="hello create campaign",
                chat_type="private",
                external_chat_id="966509999999@c.us",
                external_message_id="x1",
            )
        )
        self.assertEqual(reply, "")
        visitor_flow.return_value.handle_message.assert_not_called()

        with get_session() as session:
            after = _counts(session)
        self.assertEqual(before, after)

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_unknown_private_message_mode_only_rejection(self, visitor_flow: MagicMock) -> None:
        set_runtime_setting("private_unauthorized_mode", "message")
        visitor_flow.return_value.handle_message.return_value = MagicMock(reply="RAG")
        orch = MessageOrchestrator()
        reply = orch.handle(
            InboundMessage(phone="966508888888", message="hi", chat_type="private")
        )
        self.assertIn("not registered", reply.lower())
        visitor_flow.return_value.handle_message.assert_not_called()
        with get_session() as session:
            self.assertEqual(_counts(session)["conversations"], 0)

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_inactive_supervisor_rejected(self, visitor_flow: MagicMock) -> None:
        with get_session() as session:
            SupervisorRepository(session).create(
                {
                    "phone_number": "966501111111",
                    "display_name": "Inactive",
                    "is_active": False,
                    "activated_at": datetime.now(timezone.utc),
                }
            )
        orch = MessageOrchestrator()
        reply = orch.handle(
            InboundMessage(phone="966501111111", message="hello", chat_type="private")
        )
        self.assertEqual(reply, "")
        visitor_flow.return_value.handle_message.assert_not_called()

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_imported_supervisor_greeting(self, visitor_flow: MagicMock) -> None:
        with get_session() as session:
            sup = SupervisorRepository(session).create(
                {
                    "phone_number": "966501234567",
                    "display_name": "Ahmed",
                    "is_active": True,
                    "activated_at": datetime.now(timezone.utc),
                }
            )
            session.add(
                Campaign(
                    campaign_name="Summer Campaign",
                    owner_supervisor_id=sup.id,
                    status="active",
                )
            )
        orch = MessageOrchestrator()
        reply = orch.handle(
            InboundMessage(
                phone="966501234567",
                message="Hi",
                chat_type="private",
                external_chat_id="966501234567@c.us",
            )
        )
        self.assertIn("Ahmed", reply)
        self.assertIn("Summer Campaign", reply)
        visitor_flow.return_value.handle_message.assert_not_called()

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_removed_after_reimport_cannot_access(self, visitor_flow: MagicMock) -> None:
        wb1 = Workbook()
        ws = wb1.active
        ws.append(["Campaign Name", "Supervisor Name", "Phone Number"])
        ws.append(["Summer Campaign", "Ahmed", "966501234567"])
        ws.append(["Other", "Sara", "966502222222"])
        path1 = Path(tempfile.mkdtemp()) / "a.xlsx"
        wb1.save(path1)
        set_runtime_setting("campaign_file", str(path1))
        activate_supervisor_import()

        wb2 = Workbook()
        ws2 = wb2.active
        ws2.append(["Campaign Name", "Supervisor Name", "Phone Number"])
        ws2.append(["Other", "Sara", "966502222222"])
        path2 = path1.parent / "b.xlsx"
        wb2.save(path2)
        set_runtime_setting("campaign_file", str(path2))
        activate_supervisor_import()

        orch = MessageOrchestrator()
        reply = orch.handle(
            InboundMessage(phone="966501234567", message="hello", chat_type="private")
        )
        self.assertEqual(reply, "")
        visitor_flow.return_value.handle_message.assert_not_called()

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_group_unknown_still_uses_knowledge(self, visitor_flow: MagicMock) -> None:
        visitor_flow.return_value.handle_message.return_value = MagicMock(reply="group-rag")
        orch = MessageOrchestrator()
        reply = orch.handle(
            InboundMessage(
                phone="966509999999",
                message="What time is Maghrib?",
                chat_type="group",
                external_chat_id="g@g.us",
            )
        )
        self.assertEqual(reply, "group-rag")
        visitor_flow.return_value.handle_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
