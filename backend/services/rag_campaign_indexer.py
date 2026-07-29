"""Incremental Chroma indexing for approved campaign versions."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CHROMA_DIR = str(BACKEND_DIR / "chroma_db")
EMBEDDING_MODEL = "intfloat/multilingual-e5-base"


def _format_campaign_text(snapshot: dict[str, Any]) -> str:
    parts = [
        f"Campaign: {snapshot.get('campaign_name') or ''}",
        f"Description: {snapshot.get('description') or ''}",
        f"Start: {snapshot.get('start_date') or ''}",
        f"End: {snapshot.get('end_date') or ''}",
        f"Location: {snapshot.get('location') or snapshot.get('notes') or ''}",
    ]
    return "\n".join(p for p in parts if p.split(": ", 1)[-1])


def _get_vectordb(db_dir: Optional[str] = None):
    from langchain_community.vectorstores import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings

    persist = db_dir or os.getenv("CHROMA_PERSIST_DIR", DEFAULT_CHROMA_DIR)
    os.makedirs(persist, exist_ok=True)
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    if os.path.exists(persist) and os.listdir(persist):
        return Chroma(
            embedding_function=embeddings,
            persist_directory=persist,
        )
    return Chroma(embedding_function=embeddings, persist_directory=persist)


def remove_campaign_embeddings(campaign_id: int, *, db_dir: Optional[str] = None) -> None:
    try:
        store = _get_vectordb(db_dir)
        store._collection.delete(where={"campaign_id": campaign_id})  # noqa: SLF001
        logger.info("Removed Chroma embeddings for campaign %s", campaign_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chroma delete for campaign %s failed: %s", campaign_id, exc)


def index_campaign_version(
    campaign_id: int,
    version_number: int,
    snapshot: dict[str, Any],
    *,
    db_dir: Optional[str] = None,
) -> None:
    """Replace prior embeddings for *campaign_id* with the approved version."""
    text = _format_campaign_text(snapshot)
    if not text.strip():
        return
    try:
        store = _get_vectordb(db_dir)
        try:
            store._collection.delete(where={"campaign_id": campaign_id})  # noqa: SLF001
        except Exception:
            pass
        doc = Document(
            page_content=text,
            metadata={
                "source_type": "campaign",
                "campaign_id": campaign_id,
                "version_number": version_number,
                "stable_key": f"campaign:{campaign_id}:v{version_number}",
            },
        )
        store.add_documents([doc])
        logger.info(
            "Indexed campaign %s version %s into Chroma (%d chars)",
            campaign_id,
            version_number,
            len(text),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to index campaign %s: %s", campaign_id, exc)


def process_outbox_event(event_type: str, payload: dict[str, Any], snapshot: dict[str, Any]) -> None:
    if event_type != "campaign.version.approved":
        return
    campaign_id = int(payload["campaign_id"])
    version_number = int(payload["version_number"])
    index_campaign_version(campaign_id, version_number, snapshot)
