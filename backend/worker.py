"""RAG indexing jobs triggered from the transactional outbox."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from db.base import get_session
from db.repositories.platform_repository import OutboxRepository

logger = logging.getLogger(__name__)


def process_pending_outbox(limit: int = 50) -> int:
    """Mark campaign indexing events as published (worker hook).

    A full Chroma incremental indexer can replace this stub in production.
    """
    processed = 0
    now = datetime.now(timezone.utc)
    with get_session() as session:
        repo = OutboxRepository(session)
        for event in repo.list_pending(now, limit=limit):
            if event.event_type == "campaign.version.approved":
                logger.info(
                    "RAG refresh queued for campaign %s v%s",
                    event.payload.get("campaign_id"),
                    event.payload.get("version_number"),
                )
            event.published_at = now
            processed += 1
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = process_pending_outbox()
    print(f"Processed {count} outbox event(s)")
