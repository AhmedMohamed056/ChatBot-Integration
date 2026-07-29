"""Phase 1 schema smoke tests (SQLite in-memory)."""

from __future__ import annotations

import unittest

from sqlalchemy import inspect

from db import init_db
from db.base import Base, init_engine
import db.base as db_base


class TestPhase1Schema(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()

    def test_core_platform_tables_exist(self) -> None:
        insp = inspect(db_base.engine)
        for name in (
            "supervisors",
            "campaigns",
            "campaign_versions",
            "conversations",
            "messages",
            "conversation_states",
            "conversation_memories",
            "outbox_events",
            "idempotency_keys",
            "import_batches",
            "rag_documents",
            "admin_users",
        ):
            self.assertTrue(insp.has_table(name), name)

    def test_metadata_has_fk_order(self) -> None:
        names = [t.name for t in Base.metadata.sorted_tables]
        self.assertIn("supervisors", names)
        self.assertLess(names.index("supervisors"), names.index("campaigns"))


if __name__ == "__main__":
    unittest.main()
