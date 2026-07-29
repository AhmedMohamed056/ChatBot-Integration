"""Runtime supervisor authorization from PostgreSQL/SQLAlchemy records.

Excel is import-only. Runtime authority is always the ``supervisors`` table.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from db.platform_models import Supervisor
from db.repositories.platform_repository import CampaignOwnershipRepository, SupervisorRepository
from phone_utils import normalize_phone


def normalize_phone_for_auth(phone: str) -> str:
    normalized = normalize_phone(phone)
    return normalized or ""


def phone_lookup_candidates(phone: str) -> list[str]:
    """Return distinct phone forms to match WhatsApp IDs against imported rows."""
    raw = re.sub(r"\D", "", str(phone or ""))
    canonical = normalize_phone(phone)
    candidates: list[str] = []
    for value in (canonical, raw):
        if value and value not in candidates:
            candidates.append(value)
    if canonical.startswith("20") and len(canonical) > 2:
        local = "0" + canonical[2:]
        bare = canonical[2:]
        for value in (local, bare):
            if value and value not in candidates:
                candidates.append(value)
    return candidates


def get_active_supervisor(session: Session, phone: str) -> Optional[Supervisor]:
    """Return the active imported supervisor for *phone*, or ``None``.

    This is a read-only PostgreSQL/SQLite lookup. It never writes.
    """
    repo = SupervisorRepository(session)
    for candidate in phone_lookup_candidates(phone):
        row = repo.get_active_by_phone(candidate)
        if row is not None:
            return row
    return None


def is_active_supervisor(session: Session, phone: str) -> bool:
    return get_active_supervisor(session, phone) is not None


def authorize_private_sender(session: Session, phone: str) -> Optional[Supervisor]:
    """First-gate authorization for WhatsApp private chats (read-only)."""
    if not (phone or "").strip():
        return None
    return get_active_supervisor(session, phone)


def supervisor_owns_campaign(
    session: Session, supervisor_id: int, campaign_id: int
) -> bool:
    return CampaignOwnershipRepository(session).supervisor_owns(
        supervisor_id, campaign_id
    )
