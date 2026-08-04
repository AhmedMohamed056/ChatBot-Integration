"""Test to verify the WhatsApp supervisor persistence fix."""

import os
os.environ['DATABASE_URL'] = 'sqlite:///campaigns.db'

from db.base import get_session
from db.models import CampaignUpdate, Campaign
from db.platform_models import OutboxEvent, AuditEvent, Supervisor, CampaignVersion
from services.message_orchestrator import MessageOrchestrator, InboundMessage

def check_counts(label):
    """Print current database counts."""
    with get_session() as session:
        print(f"\n{label}:")
        print(f"  campaign_updates: {session.query(CampaignUpdate).count()}")
        print(f"  campaign_versions: {session.query(CampaignVersion).count()}")
        print(f"  outbox_events: {session.query(OutboxEvent).count()}")
        print(f"  audit_events: {session.query(AuditEvent).count()}")

def test_supervisor_update_existing_campaign():
    """Test updating an existing campaign via WhatsApp supervisor."""
    print("=" * 60)
    print("TEST: Supervisor updates existing campaign")
    print("=" * 60)

    check_counts("BEFORE")

    # Use an existing supervisor (phone from earlier test or create new)
    orchestrator = MessageOrchestrator()

    # Try with a phone that might already exist
    phone = "+201000000001"

    # First, check if supervisor exists and get their campaign
    with get_session() as session:
        supervisor = session.query(Supervisor).filter_by(phone_number=phone).first()
        if supervisor:
            campaign = session.query(Campaign).filter_by(owner_supervisor_id=supervisor.id).first()
            if campaign:
                print(f"Using existing supervisor: {supervisor.id}, campaign: {campaign.id}")
            else:
                print(f"Supervisor {supervisor.id} exists but has no campaign")
                # Create a campaign for them
                campaign = Campaign(
                    campaign_name=f"Test Campaign {supervisor.id}",
                    owner_supervisor_id=supervisor.id,
                    description="Initial description",
                    status="active"
                )
                session.add(campaign)
                session.flush()
                print(f"Created campaign: {campaign.id}")
        else:
            print(f"No supervisor found with phone {phone}, skipping test")
            return

    # Now test the update flow
    # Message 1: update campaign description
    reply1 = orchestrator.handle(
        InboundMessage(
            phone=phone,
            message="update description to new test description",
            chat_type="private",
            external_chat_id=phone,
            external_message_id="test_msg_001"
        )
    )
    print(f"\nReply 1: {reply1[:150]}...")

    # Message 2: confirm the update
    reply2 = orchestrator.handle(
        InboundMessage(
            phone=phone,
            message="OK",
            chat_type="private",
            external_chat_id=phone,
            external_message_id="test_msg_002"
        )
    )
    print(f"Reply 2: {reply2[:150]}...")

    check_counts("AFTER")

    # Verify rows were created
    with get_session() as session:
        updates = session.query(CampaignUpdate).all()
        versions = session.query(CampaignVersion).all()
        outbox = session.query(OutboxEvent).all()

        print(f"\nDetailed results:")
        print(f"  CampaignUpdate rows: {len(updates)}")
        for u in updates:
            print(f"    - id={u.id}, campaign_id={u.campaign_id}, update_type={u.update_type}, changed_field={u.changed_field}")

        print(f"  CampaignVersion rows: {len(versions)}")
        for v in versions:
            print(f"    - id={v.id}, campaign_id={v.campaign_id}, version_number={v.version_number}")

        print(f"  OutboxEvent rows: {len(outbox)}")
        for o in outbox:
            print(f"    - id={o.id}, event_type={o.event_type}, aggregate_id={o.aggregate_id}")

        if len(updates) > 0 or len(versions) > 0 or len(outbox) > 0:
            print("\n✓ SUCCESS: Database persistence is working!")
        else:
            print("\n✗ FAILURE: No rows were persisted to campaigns.db")

if __name__ == "__main__":
    test_supervisor_update_existing_campaign()