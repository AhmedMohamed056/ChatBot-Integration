"""Resolve supervisor + owned campaign context for WhatsApp private chat."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Campaign
from db.platform_models import CampaignVersion, ConversationState, Supervisor
from services.conversation_service import ConversationService

@dataclass
class SupervisorContext:
    """Structured context for authorized WhatsApp supervisors.

    This context is injected into every Gemini request for authorized supervisors,
    providing them with personalized information about their identity and campaign.

    Attributes
    ----------
    supervisor_name : str
        The supervisor's display name.
    phone : str
        The supervisor's phone number.
    campaign_id : int or None
        The ID of the campaign owned by this supervisor.
    campaign_name : str or None
        The name of the campaign owned by this supervisor.
    campaign_status : str or None
        The status of the campaign (active, deleted, etc.).
    current_campaign_version : int
        The latest version number of the campaign.
    conversation_state : str or None
        The current state of the conversation (IDLE, COLLECTING, etc.).
    pending_draft : dict or None
        The pending draft data if the conversation is in a draft state.
    """

    supervisor_name: str
    phone: str
    campaign_id: Optional[int] = None
    campaign_name: Optional[str] = None
    campaign_status: Optional[str] = None
    current_campaign_version: int = 0
    conversation_state: Optional[str] = None
    pending_draft: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (JSON-friendly contract)."""
        return asdict(self)

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
        "campaign_type": campaign.campaign_type or "",
        "start_date": str(campaign.start_date) if campaign.start_date else "",
        "end_date": str(campaign.end_date) if campaign.end_date else "",
        "status": campaign.status,
        "location": campaign.notes or "",
        "operation": "update",
    }

def build_supervisor_context(
    session: Session,
    supervisor: Supervisor,
    conversation_id: Optional[int] = None,
) -> SupervisorContext:
    """Build a SupervisorContext object for an authorized supervisor.

    Parameters
    ----------
    session : Session
        Database session for querying campaign and conversation data.
    supervisor : Supervisor
        The authorized supervisor object.
    conversation_id : int, optional
        The conversation ID to get state and draft information.

    Returns
    -------
    SupervisorContext
        A structured context object containing all supervisor information.
    """
    # Get supervisor basic info
    supervisor_name = (supervisor.display_name or "").strip() or "Supervisor"
    phone = supervisor.phone_number

    # Get owned campaign info
    campaign = get_owned_campaign(session, supervisor.id)
    campaign_id = campaign.id if campaign else None
    campaign_name = campaign.campaign_name if campaign else None
    campaign_status = campaign.status if campaign else None

    # Get current campaign version
    current_campaign_version = 0
    if campaign_id:
        current_campaign_version = latest_version_number(session, campaign_id)

    # Get conversation state and pending draft
    conversation_state = None
    pending_draft = None

    if conversation_id:
        conv_service = ConversationService(session)
        state = conv_service.get_state(conversation_id)
        if state:
            conversation_state = state.state_name
            state_data = dict(state.state_data or {})
            pending_draft = dict(state_data.get("draft") or {})
            # Only include draft if it has content
            if not pending_draft:
                pending_draft = None

    return SupervisorContext(
        supervisor_name=supervisor_name,
        phone=phone,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        campaign_status=campaign_status,
        current_campaign_version=current_campaign_version,
        conversation_state=conversation_state,
        pending_draft=pending_draft,
    )