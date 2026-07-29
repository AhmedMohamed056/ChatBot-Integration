"""Resolve supervisor + owned campaign context for WhatsApp private chat."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Campaign
from db.platform_models import CampaignVersion, ConversationState, Supervisor
from services.conversation_service import ConversationService


def get_owned_campaign(session: Session, supervisor_id: int) -> Optional[Campaign]:
    return session.scalar(
        select(Campaign).where(Campaign.owner_supervisor_id == supervisor_id)
    )


def latest_version_number(session: Session, campaign_id: int) -> int:
    return (
        session.scalar(
            select(CampaignVersion.version_number)
            .where(CampaignVersion.campaign_id == campaign_id)
            .order_by(CampaignVersion.version_number.desc())
        )
        or 0
    )


def build_supervisor_greeting(
    session: Session,
    supervisor: Supervisor,
    conversation_id: int,
    *,
    include_state: bool = False,
) -> str:
    campaign = get_owned_campaign(session, supervisor.id)
    name = (supervisor.display_name or "").strip() or "Supervisor"
    if campaign is None:
        return (
            f"Hello {name}.\n"
            "You are not linked to a campaign yet. Please contact admin after import completes."
        )
    version = latest_version_number(session, campaign.id)
    lines = [
        f"Hello {name}.",
        f"You are managing the {campaign.campaign_name}.",
    ]
    if include_state:
        conv = ConversationService(session)
        state = conv.get_state(conversation_id)
        lines.append(f"Campaign ID: {campaign.id}. Current version: {version or 0}.")
        lines.append(f"Conversation state: {state.state_name}.")
    lines.append("How can I help you today?")
    return "\n".join(lines)


def seed_draft_from_campaign(campaign: Campaign) -> dict[str, Any]:
    return {
        "campaign_name": campaign.campaign_name,
        "description": campaign.description or "",
        "start_date": str(campaign.start_date) if campaign.start_date else "",
        "end_date": str(campaign.end_date) if campaign.end_date else "",
        "location": campaign.notes or "",
        "operation": "update",
    }
