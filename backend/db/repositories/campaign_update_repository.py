"""Repository for :class:`CampaignUpdate` (append-only audit log)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CampaignUpdate
from db.repositories.base import BaseRepository


class CampaignUpdateRepository(BaseRepository[CampaignUpdate]):
    """CRUD + domain-specific queries for campaign update records.

    Because ``campaign_updates`` is an **append-only** audit log, the
    ``update`` / ``delete`` methods from :class:`BaseRepository` are
    intentionally **not** overridden to add business logic – callers
    should normally only *create* and *read*.
    """

    model = CampaignUpdate

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Read – domain-specific lookups
    # ------------------------------------------------------------------

    def list_by_campaign(
        self,
        campaign_id: int,
        limit: Optional[int] = None,
    ) -> List[CampaignUpdate]:
        """Return updates for a campaign, newest first."""
        stmt = (
            select(CampaignUpdate)
            .where(CampaignUpdate.campaign_id == campaign_id)
            .order_by(CampaignUpdate.created_at.desc(), CampaignUpdate.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def list_by_source(self, source: str) -> List[CampaignUpdate]:
        """Return all updates from a given source (e.g. ``whatsapp``)."""
        stmt = (
            select(CampaignUpdate)
            .where(CampaignUpdate.source == source)
            .order_by(CampaignUpdate.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_by_update_type(self, update_type: str) -> List[CampaignUpdate]:
        """Return all updates of a given type."""
        stmt = (
            select(CampaignUpdate)
            .where(CampaignUpdate.update_type == update_type)
            .order_by(CampaignUpdate.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_by_field(self, changed_field: str) -> List[CampaignUpdate]:
        """Return all updates that changed a specific field."""
        stmt = (
            select(CampaignUpdate)
            .where(CampaignUpdate.changed_field == changed_field)
            .order_by(CampaignUpdate.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_in_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> List[CampaignUpdate]:
        """Return updates created within ``[start, end)``."""
        stmt = (
            select(CampaignUpdate)
            .where(CampaignUpdate.created_at >= start)
            .where(CampaignUpdate.created_at < end)
            .order_by(CampaignUpdate.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_latest_for_campaign(self, campaign_id: int) -> Optional[CampaignUpdate]:
        """Return the most recent update for a campaign, or ``None``."""
        stmt = (
            select(CampaignUpdate)
            .where(CampaignUpdate.campaign_id == campaign_id)
            .order_by(CampaignUpdate.created_at.desc(), CampaignUpdate.id.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def get_latest_field_change(
        self,
        campaign_id: int,
        changed_field: str,
    ) -> Optional[CampaignUpdate]:
        """Return the most recent update for a specific field of a campaign."""
        stmt = (
            select(CampaignUpdate)
            .where(CampaignUpdate.campaign_id == campaign_id)
            .where(CampaignUpdate.changed_field == changed_field)
            .order_by(CampaignUpdate.created_at.desc(), CampaignUpdate.id.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def log_update(
        self,
        campaign_id: int,
        update_type: str,
        changed_field: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        source: str = "whatsapp",
        message_text: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> CampaignUpdate:
        """Append a new audit-log entry.

        This is the canonical way to record a campaign modification.
        History is never overwritten.
        """
        data: dict[str, Any] = {
            "campaign_id": campaign_id,
            "update_type": update_type,
            "changed_field": changed_field,
            "old_value": old_value,
            "new_value": new_value,
            "source": source,
            "message_text": message_text,
            "updated_by": updated_by,
        }
        return self.create(data)