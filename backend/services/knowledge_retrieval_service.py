"""Read-only knowledge retrieval over the shared Chroma vector store.

This is NOT a second retrieval system. It opens the SAME persisted store the
website `/chat` chain and the campaign indexer already use, by reusing
:func:`services.rag_campaign_indexer._get_vectordb` (same ``chroma_db``
directory, same ``intfloat/multilingual-e5-base`` embeddings, same default
collection). It only performs similarity search for the WhatsApp/visitor path,
which previously did no retrieval at all.

The handle is cached at module level so the embedding model loads once.
Everything is guarded — retrieval failures degrade to an empty list and never
break the reply pipeline.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_vectordb = None


def _get_store():
    global _vectordb
    if _vectordb is None:
        # Reuse the indexer's store factory so reader and writer share one
        # persist dir / embedding model / collection — single source of truth.
        from services.rag_campaign_indexer import _get_vectordb

        _vectordb = _get_vectordb()
    return _vectordb


def retrieve_knowledge(query: str, k: int = 3) -> list[str]:
    """Return up to *k* relevant document snippets for *query*.

    Reuses the shared Chroma store (campaigns + uploaded documents). Returns an
    empty list on any failure or when the query is blank.
    """
    text = (query or "").strip()
    if not text:
        return []
    try:
        store = _get_store()
        docs = store.similarity_search(text, k=k)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Knowledge retrieval failed: %s", exc)
        return []

    snippets: list[str] = []
    for doc in docs or []:
        content = (getattr(doc, "page_content", "") or "").strip()
        if content:
            snippets.append(content)
    return snippets
