"""Lightweight consistency checks for the Phase 0 documentation contracts."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class TestPhase0Contracts(unittest.TestCase):
    def test_normative_contract_files_exist(self):
        for path in (
            "docs/contracts/routing-and-authorization.md",
            "docs/contracts/campaign-lifecycle.md",
            "docs/contracts/knowledge-and-retention.md",
            "docs/architecture/target-platform.md",
            "docs/cutover-runbook.md",
        ):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_group_and_private_policy_matches_prompts(self):
        routing = read("docs/contracts/routing-and-authorization.md").lower()
        supervisor = read("backend/prompts/supervisor_instructions.md")
        visitor = read("backend/prompts/visitor_instructions.md")

        self.assertIn("groups are knowledge-only", routing)
        self.assertIn("campaign management is available only in a private chat", routing)
        self.assertIn("المجموعات للمعرفة فقط", supervisor)
        self.assertIn("إدارة الحملات مسموحة في المحادثة الخاصة فقط", supervisor)
        self.assertIn("المجموعات **للسؤال والمعرفة فقط**", visitor)

    def test_authorization_and_confirmation_are_unambiguous(self):
        routing = read("docs/contracts/routing-and-authorization.md")
        lifecycle = read("docs/contracts/campaign-lifecycle.md")
        supervisor = read("backend/prompts/supervisor_instructions.md")

        self.assertIn("active supervisor and ownership records imported into and activated in PostgreSQL", routing)
        self.assertIn("Configuration values", routing)
        self.assertIn("Excel is an import source only", routing)
        self.assertIn("exactly one active owner", routing)
        self.assertIn("No database write", lifecycle)
        self.assertIn("standalone, case-insensitive Latin token `OK`", lifecycle)
        self.assertIn("لا أكتب أي تغيير على الحملة قبل وصول `OK`", supervisor)

    def test_history_rag_time_and_retention_are_frozen(self):
        lifecycle = read("docs/contracts/campaign-lifecycle.md")
        knowledge = read("docs/contracts/knowledge-and-retention.md")
        architecture = read("docs/architecture/target-platform.md")

        self.assertIn("immutable campaign versions", lifecycle)
        self.assertIn("refreshes embeddings only for the changed campaign/version", lifecycle)
        self.assertIn("Asia/Riyadh", knowledge)
        self.assertIn("Ordinary deletion creates a tombstone", knowledge)
        self.assertIn("regulated purge", knowledge.lower())
        self.assertIn("Admin access uses authenticated identities and least-privilege roles", knowledge)
        self.assertIn("Persistent state survives restarts", architecture)
        self.assertIn("prompt-injection boundaries", architecture)


if __name__ == "__main__":
    unittest.main()
