"""Answer-quality heuristic shared by the website and WhatsApp pipelines.

Single source of truth for deciding whether an AI reply counts as an
"answered" visitor question. Imported by both ``main`` (website ``/chat``)
and the WhatsApp question logger so the ``answered`` flag is computed
identically everywhere. No duplication.
"""

from __future__ import annotations

FAILURE_MARKERS = [
    "لم أجد معلومات موثقة",
    "لا أستطيع تقديم إجابة مؤكدة",
    "عذرًا، قاعدة المعرفة",
    "Sorry, the AI service is currently overloaded",
]


def looks_like_successful_answer(answer: str) -> bool:
    """Return True when the reply is a genuine answer (not a failure notice)."""
    text = answer or ""
    return not any(marker in text for marker in FAILURE_MARKERS)
