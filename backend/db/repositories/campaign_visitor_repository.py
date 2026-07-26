"""Repository for :class:`CampaignVisitor` entities."""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CampaignVisitor
from db.repositories.base import BaseRepository


class CampaignVisitorRepository(BaseRepository[CampaignVisitor]):
    """CRUD + domain-specific queries for campaign visitors.

    Provides an upsert method that normalizes phone numbers and updates
    existing records instead of inserting duplicates.
    """

    model = CampaignVisitor

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Read – domain-specific lookups
    # ------------------------------------------------------------------

    def get_by_phone(self, phone_number: str) -> Optional[CampaignVisitor]:
        """Return the visitor with the given phone number, or ``None``."""
        stmt = select(CampaignVisitor).where(
            CampaignVisitor.phone_number == phone_number
        )
        return self.session.execute(stmt).scalars().first()

    def list_by_campaign(self, campaign_name: str) -> List[CampaignVisitor]:
        """Return all visitors belonging to a given campaign."""
        stmt = (
            select(CampaignVisitor)
            .where(CampaignVisitor.campaign_name == campaign_name)
            .order_by(CampaignVisitor.visitor_name)
        )
        return list(self.session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Create / upsert
    # ------------------------------------------------------------------

    def upsert(
        self,
        campaign_name: str,
        visitor_name: str,
        phone_number: str,
    ) -> tuple[CampaignVisitor, bool]:
        """Insert a new visitor or update an existing one by phone number.

        Returns a tuple of ``(entity, created)`` where ``created`` is
        ``True`` if a new row was inserted.
        """
        existing = self.get_by_phone(phone_number)
        if existing is not None:
            updated = self.update(
                existing,
                {
                    "visitor_name": visitor_name,
                    "campaign_name": campaign_name,
                },
            )
            return updated, False
        visitor = self.create(
            {
                "campaign_name": campaign_name,
                "visitor_name": visitor_name,
                "phone_number": phone_number,
            }
        )
        return visitor, True