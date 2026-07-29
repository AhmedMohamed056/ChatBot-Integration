"""Full in-memory pipeline: import → WhatsApp → version → delete → audit."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from db import init_db
from db.base import get_session, init_engine
from db.models import Campaign
from db.platform_models import AuditEvent, CampaignVersion
from openpyxl import Workbook
from services.message_orchestrator import InboundMessage, MessageOrchestrator
from services.platform_admin_service import delete_campaign_transactional, list_audit_events
from services.runtime_settings import set_runtime_setting
from services.supervisor_import_service import activate_supervisor_import
from sqlalchemy import func, select


class TestFullE2EPipeline(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()
        wb = Workbook()
        ws = wb.active
        ws.append(["Campaign Name", "Supervisor Name", "Phone Number"])
        ws.append(["Summer Campaign", "Ahmed", "966501234567"])
        self.xls = Path(tempfile.mkdtemp()) / "c.xlsx"
        wb.save(self.xls)
        set_runtime_setting("campaign_file", str(self.xls))
        activate_supervisor_import()

    @patch.object(MessageOrchestrator, "_get_visitor_flow")
    def test_pipeline(self, visitor_flow) -> None:
        visitor_flow.return_value.handle_message.return_value = unittest.mock.Mock(reply="")
        orch = MessageOrchestrator()
        phone = "966501234567"
        chat = f"{phone}@c.us"
        g = orch.handle(
            InboundMessage(phone=phone, message="Hi", chat_type="private", external_chat_id=chat)
        )
        self.assertIn("Summer Campaign", g)
        orch.handle(
            InboundMessage(
                phone=phone,
                message="تحديث: موعد التجمع 5pm",
                chat_type="private",
                external_chat_id=chat,
                external_message_id="u1",
            )
        )
        orch.handle(
            InboundMessage(
                phone=phone,
                message="نعم",
                chat_type="private",
                external_chat_id=chat,
                external_message_id="u2",
            )
        )
        with get_session() as session:
            versions = session.scalar(
                select(func.count()).select_from(CampaignVersion)
            )
            self.assertGreaterEqual(versions, 1)
            campaign = session.scalar(
                select(Campaign).where(Campaign.campaign_name == "Summer Campaign")
            )
            self.assertIsNotNone(campaign)
            cid = campaign.id
            delete_campaign_transactional(session, cid)
            audit = list_audit_events(session, 10)
            self.assertTrue(any(e["action"] == "campaign.delete" for e in audit))


if __name__ == "__main__":
    unittest.main()
