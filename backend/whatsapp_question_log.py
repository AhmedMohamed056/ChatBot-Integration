"""Log WhatsApp knowledge questions into the SAME dashboard pipeline as the
website.

A WhatsApp visitor knowledge question (group or private) is stored through the
exact service the website ``/chat`` endpoint uses
(:func:`database.add_visitor_question` -> legacy ``visitor_questions`` table).
That single table feeds every dashboard stat and report
(``/admin/stats`` and ``/admin/reports/visitor-questions``), so WhatsApp
questions appear alongside website questions with no endpoint changes and no
parallel reporting system.

This module intentionally does NOT use the campaigns.db
``VisitorQuestionRepository`` (the testing-only path that does not feed the
dashboard).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_whatsapp_question(question: str, answer: str, phone: str | None = None) -> None:
    """Record one WhatsApp knowledge question. Never raises.

    Parameters
    ----------
    question:
        The visitor's question text. Empty/whitespace input is ignored.
    answer:
        The reply produced for the visitor. Used only to compute the
        ``answered`` flag via the shared heuristic.
    phone:
        Optional sender phone, stored in ``session_id`` for parity with the
        website's per-session tagging.
    """
    text = (question or "").strip()
    if not text:
        return
    try:
        # Imported lazily so this helper stays importable from the WhatsApp
        # pipeline without pulling the FastAPI app at module load time.
        from answer_quality import looks_like_successful_answer
        from database import add_visitor_question

        add_visitor_question(
            text,
            answered=looks_like_successful_answer(answer or ""),
            session_id=phone,
            source="whatsapp",
        )
    except Exception:
        logger.exception("Failed to log WhatsApp visitor question for dashboard")
