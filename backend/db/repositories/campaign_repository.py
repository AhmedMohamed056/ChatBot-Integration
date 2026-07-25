"""Repository for :class:`Campaign` entities."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.models import Campaign, CampaignUpdate
from db.repositories.base import BaseRepository


class CampaignRepository(BaseRepository[Campaign]):
    """CRUD + domain-specific queries for campaigns.

    Enforces the **no duplicated campaign names** rule at the repository
    level (in addition to the database unique constraint).
    """

    model = Campaign

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: dict[str, Any]) -> Campaign:
        """Create a campaign, raising ``ValueError`` on duplicate name."""
        name = (data.get("campaign_name") or "").strip()
        if not name:
            raise ValueError("campaign_name is required")

        if self.get_by_name(name) is not None:
            raise ValueError(f"Campaign with name '{name}' already exists")

        data["campaign_name"] = name
        return super().create(data)

    # ------------------------------------------------------------------
    # Read – domain-specific lookups
    # ------------------------------------------------------------------

    def get_by_name(self, campaign_name: str) -> Optional[Campaign]:
        """Return the campaign with the given name (case-sensitive)."""
        stmt = select(Campaign).where(Campaign.campaign_name == campaign_name)
        return self.session.execute(stmt).scalars().first()

    def get_by_name_case_insensitive(self, campaign_name: str) -> Optional[Campaign]:
        """Return the campaign matching *campaign_name* (case-insensitive)."""
        stmt = select(Campaign).where(
            Campaign.campaign_name.ilike(campaign_name)
        )
        return self.session.execute(stmt).scalars().first()

    def list_active(self) -> List[Campaign]:
        """Return all campaigns whose status is ``'active'``."""
        stmt = select(Campaign).where(Campaign.status == "active")
        return list(self.session.execute(stmt).scalars().all())

    def list_by_status(self, status: str) -> List[Campaign]:
        """Return all campaigns with the given status."""
        stmt = select(Campaign).where(Campaign.status == status)
        return list(self.session.execute(stmt).scalars().all())

    def list_by_type(self, campaign_type: str) -> List[Campaign]:
        """Return all campaigns of a given type."""
        stmt = select(Campaign).where(Campaign.campaign_type == campaign_type)
        return list(self.session.execute(stmt).scalars().all())

    def list_active_on_date(self, target_date: date) -> List[Campaign]:
        """Return campaigns active on a specific date.

        A campaign is considered active on *target_date* when:
        - ``status == 'active'`` **and**
        - ``start_date`` is null or ``<= target_date`` **and**
        - ``end_date`` is null or ``>= target_date``.
        """
        stmt = select(Campaign).where(Campaign.status == "active")
        stmt = stmt.where(
            (Campaign.start_date.is_(None)) | (Campaign.start_date <= target_date)
        )
        stmt = stmt.where(
            (Campaign.end_date.is_(None)) | (Campaign.end_date >= target_date)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_with_updates(self, campaign_id: int) -> Optional[Campaign]:
        """Return a campaign with its ``updates`` relationship loaded."""
        stmt = (
            select(Campaign)
            .options(selectinload(Campaign.updates))
            .where(Campaign.id == campaign_id)
        )
        return self.session.execute(stmt).scalars().first()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_campaign(
        self,
        campaign_id: int,
        data: dict[str, Any],
    ) -> Optional[Campaign]:
        """Update a campaign.

        If ``campaign_name`` is being changed, the new name is checked for
        uniqueness before the update is applied.
        """
        new_name = data.get("campaign_name")
        if new_name is not None:
            new_name = new_name.strip()
            if not new_name:
                raise ValueError("campaign_name cannot be empty")
            existing = self.get_by_name(new_name)
            if existing is not None and existing.id != campaign_id:
                raise ValueError(f"Campaign with name '{new_name}' already exists")
            data["campaign_name"] = new_name
        return self.update_by_id(campaign_id, data)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_campaign(self, campaign_id: int) -> bool:
        """Delete a campaign and all its updates (cascade)."""
        return self.delete_by_id(campaign_id)

    # ------------------------------------------------------------------
    # History / audit
    # ------------------------------------------------------------------

    def get_update_history(self, campaign_id: int) -> List[CampaignUpdate]:
        """Return the full update history for a campaign (newest first)."""
        stmt = (
            select(CampaignUpdate)
            .where(CampaignUpdate.campaign_id == campaign_id)
            .order_by(CampaignUpdate.created_at.desc(), CampaignUpdate.id.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def add_update(self, campaign_id: int, data: dict[str, Any]) -> CampaignUpdate:
        """Append a new audit-log entry for a campaign.

        This is the **only** way campaign changes should be recorded –
        history is never overwritten.
        """
        update = CampaignUpdate(campaign_id=campaign_id, **data)
        self.session.add(update)
        self.session.flush()
        self.session.refresh(update)
        return update