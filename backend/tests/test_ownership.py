"""Campaign ownership enforcement tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import select

from db import init_db
from db.base import get_session, init_engine
from db.models import Campaign
from db.platform_models import Supervisor
from db.repositories.platform_repository import SupervisorRepository
from services.campaign_lifecycle_service import CampaignLifecycleService
from services.conversation_service import ConversationService


class TestOwnership(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()
        with get_session() as session:
            a = SupervisorRepository(session).create(
                {
                    "phone_number": "966501111111",
                    "display_name": "Ali",
                    "is_active": True,
                    "activated_at": datetime.now(timezone.utc),
                }
            )
            b = SupervisorRepository(session).create(
                {
                    "phone_number": "966502222222",
                    "display_name": "Bob",
                    "is_active": True,
                    "activated_at": datetime.now(timezone.utc),
                }
            )
            session.add(
                Campaign(
                    campaign_name="Ali Campaign",
                    owner_supervisor_id=a.id,
                    status="active",
                )
            )
            session.add(
                Campaign(
                    campaign_name="Bob Campaign",
                    owner_supervisor_id=b.id,
                    status="active",
                )
            )

    def test_cannot_commit_other_campaign_name(self) -> None:
        with get_session() as session:
            supervisor_b = session.scalar(
                select(Supervisor).where(Supervisor.phone_number == "966502222222")
            )
            assert supervisor_b is not None
            conv = ConversationService(session).get_or_create(
                channel="whatsapp",
                external_chat_id="966502222222@c.us",
                participant_phone="966502222222",
                chat_type="private",
            )
            state = ConversationService(session).get_state(conv.id)
            ConversationService(session).set_state(
                state,
                state_name="WAITING_FOR_CONFIRMATION",
                state_data={
                    "draft": {
                        "campaign_name": "Ali Campaign",
                        "description": "hack",
                        "operation": "update",
                    },
                    "operation": "update",
                },
            )
            svc = CampaignLifecycleService(session)
            reply = svc.handle(
                supervisor=supervisor_b,
                conversation_id=conv.id,
                message="OK",
                original_message="OK",
            )
            self.assertIn("do not own", reply.lower())


if __name__ == "__main__":
    unittest.main()
