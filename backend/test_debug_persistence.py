"""Debug test to trace the exact execution path."""

import os
os.environ['DATABASE_URL'] = 'sqlite:///campaigns.db'

from db.base import get_session
from db.models import CampaignUpdate, Campaign
from db.platform_models import OutboxEvent, CampaignVersion, Supervisor
from services.message_orchestrator import MessageOrchestrator, InboundMessage

# Patch to add debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check existing data
with get_session() as session:
    supervisor = session.query(Supervisor).filter_by(phone_number="+201000000001").first()
    if supervisor:
        campaign = session.query(Campaign).filter_by(owner_supervisor_id=supervisor.id).first()
        print(f"Found supervisor: {supervisor.id}, campaign: {campaign.id if campaign else None}")
    else:
        print("No supervisor found")
        exit(1)

# Now trace a simple update
print("\n" + "="*60)
print("Starting WhatsApp message processing...")
print("="*60)

orchestrator = MessageOrchestrator()

# Patch the session to see what's happening
from db import base as db_base
original_get_session = db_base.get_session

@contextmanager
def debug_get_session():
    """Wrapper to trace session operations."""
    import traceback
    session = original_get_session.__wrapped__(None) if hasattr(original_get_session, '__wrapped__') else None
    # Actually, let's just use the original
    with original_get_session() as sess:
        print(f"\n>>> Session created: {id(sess)}")
        try:
            yield sess
            print(f">>> Session committing: {id(sess)}")
            sess.commit()
            print(f">>> Session committed successfully: {id(sess)}")
        except Exception as e:
            print(f">>> Session rollback: {id(sess)}, error: {e}")
            sess.rollback()
            raise
        finally:
            print(f">>> Session closing: {id(sess)}")
            sess.close()

# Monkey patch temporarily
db_base.get_session = debug_get_session

try:
    reply = orchestrator.handle(
        InboundMessage(
            phone="+201000000001",
            message="update description to test persistence fix",
            chat_type="private",
            external_chat_id="+201000000001",
            external_message_id="debug_msg_001"
        )
    )
    print(f"\nReply: {reply[:200]}")
finally:
    # Restore
    db_base.get_session = original_get_session

# Check results
with get_session() as session:
    print(f"\nFinal counts:")
    print(f"  CampaignUpdate: {session.query(CampaignUpdate).count()}")
    print(f"  CampaignVersion: {session.query(CampaignVersion).count()}")
    print(f"  OutboxEvent: {session.query(OutboxEvent).count()}")