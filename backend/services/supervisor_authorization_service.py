"""Runtime supervisor authorization from PostgreSQL/SQLAlchemy records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from db.platform_models import Supervisor
from db.repositories.platform_repository import CampaignOwnershipRepository, SupervisorRepository
from phone_utils import normalize_phone


def normalize_phone_for_auth(phone: str) -> str:
    normalized = normalize_phone(phone)
    return normalized or ""


def get_active_supervisor(session: Session, phone: str) -> Optional[Supervisor]:
    canonical = normalize_phone_for_auth(phone)
    if not canonical:
        return None
    return SupervisorRepository(session).get_active_by_phone(canonical)


def is_active_supervisor(session: Session, phone: str) -> bool:
    return get_active_supervisor(session, phone) is not None


def supervisor_owns_campaign(
    session: Session, supervisor_id: int, campaign_id: int
) -> bool:
    return CampaignOwnershipRepository(session).supervisor_owns(
        supervisor_id, campaign_id
    )
