"""Supervisor Excel import validation tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from db import init_db
from db.base import get_session, init_engine
from openpyxl import Workbook
from services.supervisor_import_service import activate_supervisor_import, preview_supervisor_import
from services.runtime_settings import set_runtime_setting
from services.supervisor_authorization_service import get_active_supervisor


class TestExcelImport(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()
        wb = Workbook()
        ws = wb.active
        ws.append(["Campaign Name", "Supervisor Name", "Phone Number", "Status"])
        ws.append(["Summer Campaign", "Ahmed", "966501111111", "active"])
        ws.append(["Winter Campaign", "Sara", "966502222222", "active"])
        self.path = Path(tempfile.mkdtemp()) / "campaigns.xlsx"
        wb.save(self.path)
        set_runtime_setting("campaign_file", str(self.path))

    def test_preview_and_activate(self) -> None:
        preview = preview_supervisor_import()
        self.assertEqual(len(preview["preview"]), 2)
        result = activate_supervisor_import()
        self.assertEqual(result["activated"], 2)
        with get_session() as session:
            sup = get_active_supervisor(session, "966501111111")
            self.assertIsNotNone(sup)
            self.assertEqual(sup.display_name, "Ahmed")

    def test_duplicate_phone_rejected(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.append(["Campaign Name", "Supervisor Name", "Phone Number"])
        ws.append(["A", "One", "966509999999"])
        ws.append(["B", "Two", "966509999999"])
        dup_path = self.path.parent / "dup.xlsx"
        wb.save(dup_path)
        set_runtime_setting("campaign_file", str(dup_path))
        with self.assertRaises(ValueError):
            activate_supervisor_import()


if __name__ == "__main__":
    unittest.main()
