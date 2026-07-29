"""Admin authentication tests (PostgreSQL in-memory)."""

from __future__ import annotations

import os
import unittest

from db import init_db
from db.base import get_session, init_engine
from services.admin_auth_service import (
    AdminAuthError,
    change_password,
    ensure_default_admin,
    hash_password,
    login,
    resolve_session,
    verify_password,
)


class TestAdminAuth(unittest.TestCase):
    def setUp(self) -> None:
        init_engine(":memory:")
        init_db()
        os.environ["ADMIN_USERNAME"] = "admin@test"
        os.environ["ADMIN_PASSWORD"] = "secret123"
        with get_session() as session:
            ensure_default_admin(session)

    def test_wrong_username(self) -> None:
        with get_session() as session:
            with self.assertRaises(AdminAuthError) as ctx:
                login(session, "wrong", "secret123")
            self.assertEqual(ctx.exception.code, "invalid_username")

    def test_wrong_password(self) -> None:
        with get_session() as session:
            with self.assertRaises(AdminAuthError) as ctx:
                login(session, "admin@test", "bad")
            self.assertEqual(ctx.exception.code, "invalid_password")

    def test_login_and_password_change(self) -> None:
        with get_session() as session:
            token = login(session, "admin@test", "secret123")
            self.assertTrue(resolve_session(session, token))
            self.assertTrue(change_password(session, token, "secret123", "newpass456"))
            with self.assertRaises(AdminAuthError):
                login(session, "admin@test", "secret123")
            token2 = login(session, "admin@test", "newpass456")
            self.assertTrue(resolve_session(session, token2))

    def test_password_hash_roundtrip(self) -> None:
        stored = hash_password("x")
        self.assertTrue(verify_password("x", stored))
        self.assertFalse(verify_password("y", stored))


if __name__ == "__main__":
    unittest.main()
