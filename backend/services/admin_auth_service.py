"""Admin authentication backed by PostgreSQL ``admin_users`` / ``admin_sessions``."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.platform_models import AdminSession, AdminUser


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000
    )
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest_hex = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000
    )
    return secrets.compare_digest(digest.hex(), digest_hex)


def get_admin_by_username(session: Session, username: str) -> Optional[AdminUser]:
    name = (username or "").strip()
    if not name:
        return None
    return session.scalar(
        select(AdminUser).where(
            AdminUser.email == name,
            AdminUser.is_active.is_(True),
        )
    )


def ensure_default_admin(session: Session) -> None:
    """Seed the first admin from env when the table is empty."""
    exists = session.scalar(select(AdminUser.id).limit(1))
    if exists is not None:
        return
    username = os.getenv("ADMIN_USERNAME", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not username or not password:
        return
    session.add(
        AdminUser(
            email=username,
            password_hash=hash_password(password),
            display_name="Administrator",
            is_active=True,
        )
    )
    session.flush()


class AdminAuthError(Exception):
    code: str

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def login(session: Session, username: str, password: str) -> str:
    """Validate credentials and return a session token for the cookie."""
    user = get_admin_by_username(session, username)
    if user is None:
        raise AdminAuthError("invalid_username")
    if not verify_password(password, user.password_hash):
        raise AdminAuthError("invalid_password")
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session.add(
        AdminSession(
            admin_user_id=user.id,
            token_hash=token_hash,
            expires_at=_utcnow() + timedelta(hours=8),
        )
    )
    session.flush()
    return token


def resolve_session(session: Session, token: Optional[str]) -> Optional[AdminUser]:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = _utcnow()
    row = session.scalar(
        select(AdminSession).where(
            AdminSession.token_hash == token_hash,
            AdminSession.revoked_at.is_(None),
            AdminSession.expires_at > now,
        )
    )
    if row is None:
        return None
    return session.get(AdminUser, row.admin_user_id)


def logout(session: Session, token: Optional[str]) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = session.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash)
    )
    if row:
        row.revoked_at = _utcnow()


def change_password(
    session: Session, token: Optional[str], old_password: str, new_password: str
) -> bool:
    user = resolve_session(session, token)
    if user is None:
        return False
    if not verify_password(old_password, user.password_hash):
        return False
    if not new_password or len(new_password) < 6:
        return False
    user.password_hash = hash_password(new_password)
    session.flush()
    return True
