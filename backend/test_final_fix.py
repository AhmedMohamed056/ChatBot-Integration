"""Final test to verify persistence fix."""

import os
os.environ['DATABASE_URL'] = 'sqlite:///campaigns.db'

from db.base import get_session, init_engine
from db.models import CampaignUpdate, Campaign
from db.platform_models import OutboxEvent, CampaignVersion, Supervisor
from services.message_orchestrator import MessageOrchestrator, InboundMessage

# Re-initialize engine to pick up any DB changes
init_engine()

def check_counts(label):
    """Print current database counts."""
    with get_session() as session:
        print(f"\n{label}:")
        print(f"  campaign_updates: {session.query(CampaignUpdate).count()}")
        print(f"  campaign_versions: {session.query(CampaignVersion).count()}")
        print(f"  outbox_events: {session.query(OutboxEvent).count()}")

print("=" * 60)
print("TEST: Supervisor updates campaign via WhatsApp")
print("=" * 60)

check_counts("BEFORE")

orchestrator = MessageOrchestrator()

# Use phone that matches normalized format in DB
phone = "201000000001"  # This is the normalized version

# Message 1: update campaign
reply1 = orchestrator.handle(
    InboundMessage(
        phone=phone,
        message="update campaign description to test persistence",
        chat_type="private",
        external_chat_id=phone,
        external_message_id="test_001"
    )
)
print(f"Reply 1: {reply1[:200] if reply1 else '(empty)'}")

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
print(f"Reply 2: {reply2[:200] if reply2 else '(empty)'}")

check_counts("AFTER")

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
        exit(0)
    else:
        print("\n✗ FAILURE: No rows were persisted")
        exit(1)