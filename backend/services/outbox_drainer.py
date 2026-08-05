"""Background auto-drainer for the transactional outbox.

Reuses :func:`worker.process_pending_outbox` (the SAME job that
``python worker.py`` runs) on a short polling loop in a daemon thread. This
drains both the startup backlog and every event enqueued by a supervisor
commit within a few seconds — so approved campaign versions get indexed into
Chroma automatically, without anyone running the worker by hand.

It deliberately does NOT touch the commit path: ``_commit`` only enqueues the
outbox row as before; this poller picks it up independently.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# Poll interval — small enough that a commit is indexed within a few seconds,
# large enough to stay idle-cheap between campaign edits.
_POLL_SECONDS = 3.0

_thread: threading.Thread | None = None
_lock = threading.Lock()


def _run_loop() -> None:
    # Import lazily so importing this module never drags in the heavy RAG /
    # embedding stack until the drainer actually starts.
    from worker import process_pending_outbox

    while True:
        try:
            processed = process_pending_outbox()
            if processed:
                logger.info("Outbox drainer indexed %d event(s)", processed)
        except Exception as exc:  # noqa: BLE001 — never let the loop die
            logger.warning("Outbox drainer iteration failed: %s", exc)
        time.sleep(_POLL_SECONDS)


def start_outbox_drainer() -> None:
    """Start the background drainer once (idempotent)."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(
            target=_run_loop,
            name="outbox-drainer",
            daemon=True,
        )
        _thread.start()
        logger.info("Outbox drainer started (poll every %.0fs)", _POLL_SECONDS)
