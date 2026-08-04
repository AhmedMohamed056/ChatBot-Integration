"""Simple test with proper intent matching."""

import os
os.environ['DATABASE_URL'] = 'sqlite:///campaigns.db'

from db.base import get_session
from db.models import CampaignUpdate, Campaign
from db.platform_models import OutboxEvent, CampaignVersion, Supervisor
from services.message_orchestrator import MessageOrchestrator, InboundMessage

def check_counts(label):
    """Print current database counts."""
    with get_session() as session:
        print(f"\n{label}:")
        print(f"  campaign_updates: {session.query(CampaignUpdate).count()}")
        print(f"  campaign_versions: {session.query(CampaignVersion).count()}")
        print(f"  outbox_events: {session.query(OutboxEvent).count()}")

# Use existing supervisor
phone = "+201000000001"
with get_session() as session:
    supervisor = session.query(Supervisor).filter_by(phone_number=phone).first()
    if not supervisor:
        print("No supervisor found")
        exit(1)
    campaign = session.query(Campaign).filter_by(owner_supervisor_id=supervisor.id).first()
    if not campaign:
        print("No campaign found")
        exit(1)
    print(f"Using supervisor: {supervisor.id}, campaign: {campaign.id}")

check_counts("BEFORE")

orchestrator = MessageOrchestrator()

# Message 1: Use exact phrase that matches UPDATE regex
reply1 = orchestrator.handle(
    InboundMessage(
        phone=phone,
        message="update campaign description to new description",
        chat_type="private",
        external_chat_id=phone,
        external_message_id="test_001"
    )
)
print(f"Reply 1: {reply1}")

# Message 2: confirm
reply2 = orchestrator.handle(
    InboundMessage(
        phone=phone,
        message="OK",
        chat_type="private",
        external_chat_id=phone,
        external_message_id="test_002"
    )
)
print(f"Reply 2: {reply2}")

check_counts("AFTER")

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

    if len(updates) > 0 or len(versions) > 0 or len(outbox) > 0:
        print("\n✓ SUCCESS: Database persistence is working!")
    else:
        print("\n✗ FAILURE: No rows were persisted")