"""Repository for CampaignKnowledge model - Phase 4 Supervisor Learning."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CampaignKnowledge

class CampaignKnowledgeRepository:
    """Repository for managing campaign knowledge entries.

    Provides CRUD operations for storing and retrieving supervisor-taught
    facts about campaigns.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, knowledge_id: int) -> Optional[CampaignKnowledge]:
        """Get a knowledge entry by its ID."""
        return self.session.scalar(
            select(CampaignKnowledge).where(CampaignKnowledge.id == knowledge_id)
        )

    def get_all_by_campaign(
        self,
        campaign_id: int,
        is_active: bool = True,
        category: Optional[str] = None
    ) -> List[CampaignKnowledge]:
        """Get all knowledge entries for a specific campaign.

        Args:
            campaign_id: The campaign ID to filter by.
            is_active: Only return active entries if True.
            category: Optional category filter.

        Returns:
            List of CampaignKnowledge entries matching the criteria.
        """
        query = select(CampaignKnowledge).where(
            CampaignKnowledge.campaign_id == campaign_id
        )

        if is_active:
            query = query.where(CampaignKnowledge.is_active == True)  # noqa: E712

        if category:
            query = query.where(CampaignKnowledge.category == category)

        query = query.order_by(CampaignKnowledge.created_at.asc())

        return list(self.session.scalars(query))

    def get_active_knowledge_texts(self, campaign_id: int) -> List[str]:
        """Get all active knowledge fact texts for a campaign.

        This is the primary method for retrieving knowledge to inject
        into AI prompts.

        Args:
            campaign_id: The campaign ID.

        Returns:
            List of fact_text strings for all active knowledge entries.
        """
        knowledge_entries = self.get_all_by_campaign(
            campaign_id=campaign_id,
            is_active=True
        )
        return [entry.fact_text for entry in knowledge_entries]

    def get_by_category(
        self,
        campaign_id: int,
        category: str,
        is_active: bool = True
    ) -> List[CampaignKnowledge]:
        """Get knowledge entries by category for a campaign."""
        return self.get_all_by_campaign(
            campaign_id=campaign_id,
            is_active=is_active,
            category=category
        )

    def create(
        self,
        campaign_id: int,
        fact_text: str,
        category: str = "general",
        source_type: str = "supervisor",
        created_by_supervisor_id: Optional[int] = None,
        is_active: bool = True
    ) -> CampaignKnowledge:
        """Create a new knowledge entry.

        Args:
            campaign_id: The campaign this knowledge belongs to.
            fact_text: The fact text to store.
            category: Category for organizing knowledge.
            source_type: How this knowledge was acquired.
            created_by_supervisor_id: The supervisor who created this.
            is_active: Whether this knowledge should be active.

        Returns:
            The created CampaignKnowledge entry.
        """
        entry = CampaignKnowledge(
            campaign_id=campaign_id,
            fact_text=fact_text,
            category=category,
            source_type=source_type,
            created_by_supervisor_id=created_by_supervisor_id,
            is_active=is_active,
            version=1
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def update(
        self,
        knowledge_id: int,
        fact_text: Optional[str] = None,
        category: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[CampaignKnowledge]:
        """Update an existing knowledge entry.

        Args:
            knowledge_id: The ID of the entry to update.
            fact_text: New fact text (optional).
            category: New category (optional).
            is_active: New active status (optional).

        Returns:
            The updated CampaignKnowledge entry, or None if not found.
        """
        entry = self.get_by_id(knowledge_id)
        if not entry:
            return None

        if fact_text is not None:
            entry.fact_text = fact_text
        if category is not None:
            entry.category = category
        if is_active is not None:
            entry.is_active = is_active

        # Increment version on any update
        entry.version += 1

        self.session.commit()
        self.session.refresh(entry)
        return entry

    def deactivate(self, knowledge_id: int) -> bool:
        """Deactivate a knowledge entry.

        Args:
            knowledge_id: The ID of the entry to deactivate.

        Returns:
            True if the entry was found and deactivated, False otherwise.
        """
        entry = self.get_by_id(knowledge_id)
        if not entry:
            return False

        entry.is_active = False
        entry.version += 1
        self.session.commit()
        return True

    def delete(self, knowledge_id: int) -> bool:
        """Delete a knowledge entry.

        Args:
            knowledge_id: The ID of the entry to delete.

        Returns:
            True if the entry was found and deleted, False otherwise.
        """
        entry = self.get_by_id(knowledge_id)
        if not entry:
            return False

        self.session.delete(entry)
        self.session.commit()
        return True

    def exists(
        self,
        campaign_id: int,
        fact_text: str,
        is_active: bool = True
    ) -> bool:
        """Check if a knowledge entry with the same text exists for a campaign.

        Args:
            campaign_id: The campaign ID.
            fact_text: The fact text to check.
            is_active: Only check active entries if True.

        Returns:
            True if a matching entry exists, False otherwise.
        """
        query = select(CampaignKnowledge).where(
            CampaignKnowledge.campaign_id == campaign_id,
            CampaignKnowledge.fact_text == fact_text
        )

        if is_active:
            query = query.where(CampaignKnowledge.is_active == True)  # noqa: E712

        return self.session.scalar(query) is not None

    def get_knowledge_count(self, campaign_id: int, is_active: bool = True) -> int:
        """Get the count of knowledge entries for a campaign.

        Args:
            campaign_id: The campaign ID.
            is_active: Only count active entries if True.

        Returns:
            The count of matching entries.
        """
        query = select(CampaignKnowledge).where(
            CampaignKnowledge.campaign_id == campaign_id
        )

        if is_active:
            query = query.where(CampaignKnowledge.is_active == True)  # noqa: E712

        return len(list(self.session.scalars(query)))