"""Test to prove the WhatsApp supervisor persistence bug."""

import os
os.environ['DATABASE_URL'] = 'sqlite:///campaigns.db'

from db.base import get_session, init_engine
from db.models import CampaignUpdate, Campaign
from db.platform_models import OutboxEvent, AuditEvent, Supervisor, Conversation, ConversationState, CampaignVersion
from services.message_orchestrator import MessageOrchestrator, InboundMessage
from services.campaign_lifecycle_service import CampaignLifecycleService
from services.conversation_service import ConversationService
from datetime import datetime, timezone

def setup_test_data():
    """Create a test supervisor and campaign."""
    with get_session() as session:
        # Create a test supervisor
        supervisor = Supervisor(
            phone_number="+201000000001",
            display_name="Test Supervisor",
            is_active=True
        )
        session.add(supervisor)
        session.flush()

        # Create a test campaign
        campaign = Campaign(
            campaign_name="Test Campaign",
            owner_supervisor_id=supervisor.id,
            description="Initial description",
            status="active"
        )
        session.add(campaign)
        session.flush()

        # Create conversation
        conv_service = ConversationService(session)
        conversation = conv_service.get_or_create(
            channel="whatsapp",
            external_chat_id="+201000000001",
            participant_phone="+201000000001",
            chat_type="private",
            campaign_id=None
        )
        session.flush()

        print(f"Created supervisor: {supervisor.id}, campaign: {campaign.id}, conversation: {conversation.id}")
        return supervisor, campaign, conversation

def check_counts(label):
    """Print current database counts."""
    with get_session() as session:
        print(f"\n{label}:")
        print(f"  campaign_updates: {session.query(CampaignUpdate).count()}")
        print(f"  campaign_versions: {session.query(CampaignVersion).count()}")
        print(f"  outbox_events: {session.query(OutboxEvent).count()}")
        print(f"  audit_events: {session.query(AuditEvent).count()}")

def test_supervisor_create_campaign():
    """Test creating a campaign via WhatsApp supervisor."""
    print("=" * 60)
    print("TEST: Supervisor creates a campaign")
    print("=" * 60)

    check_counts("BEFORE")

    # Setup test data
    supervisor, campaign, conversation = setup_test_data()

    # Simulate WhatsApp message to create campaign
    orchestrator = MessageOrchestrator()

    # First message: start creating campaign
    reply1 = orchestrator.handle(
        InboundMessage(
            phone="+201000000001",
            message="create campaign TestCampaign2",
            chat_type="private",
            external_chat_id="+201000000001",
            external_message_id="msg_001"
        )
    )
    print(f"\nReply 1: {reply1[:100]}...")

    # Second message: provide description
    reply2 = orchestrator.handle(
        InboundMessage(
            phone="+201000000001",
            message="This is a test campaign description",
            chat_type="private",
            external_chat_id="+201000000001",
            external_message_id="msg_002"
        )
    )
    print(f"Reply 2: {reply2[:100]}...")

    # Third message: confirm
    reply3 = orchestrator.handle(
        InboundMessage(
            phone="+201000000001",
            message="OK",
            chat_type="private",
            external_chat_id="+201000000001",
            external_message_id="msg_003"
        )
    )
    print(f"Reply 3: {reply3[:100]}...")

    check_counts("AFTER")

    # Check if any rows were actually created
    with get_session() as session:
        updates = session.query(CampaignUpdate).all()
        versions = session.query(CampaignVersion).all()
        outbox = session.query(OutboxEvent).all()

        print(f"\nDetailed results:")
        print(f"  CampaignUpdate rows: {len(updates)}")
        for u in updates:
            print(f"    - id={u.id}, campaign_id={u.campaign_id}, update_type={u.update_type}")

        print(f"  CampaignVersion rows: {len(versions)}")
        for v in versions:
            print(f"    - id={v.id}, campaign_id={v.campaign_id}, version_number={v.version_number}")

        print(f"  OutboxEvent rows: {len(outbox)}")
        for o in outbox:
            print(f"    - id={o.id}, event_type={o.event_type}")

if __name__ == "__main__":
    test_supervisor_create_campaign()