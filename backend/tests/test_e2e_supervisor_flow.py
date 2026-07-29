"""End-to-end supervisor WhatsApp flow (in-memory PostgreSQL/SQLite)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import select

from db import init_db
from db.base import get_session, init_engine
from db.models import Campaign
from db.platform_models import Supervisor
from db.repositories.platform_repository import SupervisorRepository
from services.message_orchestrator import InboundMessage, MessageOrchestrator


class TestSupervisorE2E(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()
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
                    description="Initial",
                )
            )

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_collect_review_commit(self, visitor_flow) -> None:
        visitor_flow.return_value.handle_message.return_value = unittest.mock.Mock(
            reply="unused"
        )
        orchestrator = MessageOrchestrator()
        phone = "966501234567"
        chat = "966501234567@c.us"

        greeting = orchestrator.handle(
            InboundMessage(phone=phone, message="مرحبا", chat_type="private", external_chat_id=chat)
        )
        self.assertIn("Summer Campaign", greeting)

        orchestrator.handle(
            InboundMessage(
                phone=phone,
                message="تحديث: موعد التجمع الساعة 5 مساءً",
                chat_type="private",
                external_chat_id=chat,
                external_message_id="m1",
            )
        )
        commit_reply = orchestrator.handle(
            InboundMessage(
                phone=phone,
                message="نعم",
                chat_type="private",
                external_chat_id=chat,
                external_message_id="m2",
            )
        )
        self.assertTrue(
            "حفظ" in commit_reply or "تم" in commit_reply,
            commit_reply,
        )

        with get_session() as session:
            campaign = session.scalar(
                select(Campaign).where(Campaign.campaign_name == "Summer Campaign")
            )
            self.assertIsNotNone(campaign)
            self.assertIn("5", campaign.description or "")


if __name__ == "__main__":
    unittest.main()
