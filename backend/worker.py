"""RAG indexing jobs triggered from the transactional outbox."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from db.base import get_session
from db.repositories.platform_repository import OutboxRepository
from services.rag_campaign_indexer import (
    index_campaign_version,
    remove_campaign_embeddings,
)

logger = logging.getLogger(__name__)


def process_pending_outbox(limit: int = 50) -> int:
    processed = 0
    now = datetime.now(timezone.utc)
    with get_session() as session:
        repo = OutboxRepository(session)
        for event in repo.list_pending(now, limit=limit):
            payload = event.payload or {}
            try:
                if event.event_type == "campaign.version.approved":
                    snapshot = payload.get("snapshot") or {}
                    index_campaign_version(
                        int(payload["campaign_id"]),
                        int(payload["version_number"]),
                        snapshot,
                    )
                elif event.event_type == "campaign.deleted":
                    remove_campaign_embeddings(int(payload["campaign_id"]))
            except Exception as exc:  # noqa: BLE001
                event.last_error = str(exc)
                event.attempts = (event.attempts or 0) + 1
                logger.exception("Outbox event %s failed", event.id)
                continue
            event.published_at = now
            processed += 1
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = process_pending_outbox()
    print(f"Processed {count} outbox event(s)")
