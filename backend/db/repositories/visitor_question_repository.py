"""Repository for :class:`VisitorQuestion` entities.

Implements the Task 10 (Visitor Question Logging) repository contract:

- :meth:`log_question`           - persist a single visitor question.
- :meth:`list_questions`         - return the latest questions (newest first).
- :meth:`list_latest_questions`  - return the latest questions ordered by
  ``message_timestamp`` (used by the Reports Backend, Task 11).
- :meth:`count_questions`        - return the total number of stored questions.

Nothing else belongs here.  No reports, analytics, or AI logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import VisitorQuestion
from db.repositories.base import BaseRepository


class VisitorQuestionRepository(BaseRepository[VisitorQuestion]):
    """Persistence layer for visitor questions."""

    model = VisitorQuestion

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def log_question(
        self,
        question: str,
        phone_number: Optional[str] = None,
        visitor_name: Optional[str] = None,
        campaign_name: Optional[str] = None,
        detected_language: str = "unknown",
        message_timestamp: Optional[datetime] = None,
    ) -> VisitorQuestion:
        """Persist a single visitor question.

        Parameters
        ----------
        question:
            The question text.  Must be non-empty (validated by the
            service layer before reaching the repository).
        phone_number:
            Normalised WhatsApp number, or ``None`` when missing.
        visitor_name:
            Detected visitor name, or ``None``.
        campaign_name:
            Detected campaign name, or ``None``.
        detected_language:
            ``"ar"``, ``"en"`` or ``"unknown"``.
        message_timestamp:
            When the message was received.  Defaults to *now* (UTC).
        """
        data: dict[str, Any] = {
            "question": question,
            "phone_number": phone_number,
            "visitor_name": visitor_name,
            "campaign_name": campaign_name,
            "detected_language": detected_language,
            "message_timestamp": message_timestamp,
        }
        return self.create(data)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_questions(self, limit: int = 50) -> List[VisitorQuestion]:
        """Return the latest questions, newest first.

        A simple list with no pagination, search, or filters.
        """
        stmt = (
            select(VisitorQuestion)
            .order_by(VisitorQuestion.created_at.desc(), VisitorQuestion.id.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_latest_questions(self, limit: int = 50) -> List[VisitorQuestion]:
        """Return the latest questions ordered by ``message_timestamp``.

        Newest first (by ``message_timestamp`` then ``id``).  Used by the
        Reports Backend (Task 11) – read-only, no filters or search.
        """
        stmt = (
            select(VisitorQuestion)
            .order_by(
                VisitorQuestion.message_timestamp.desc(),
                VisitorQuestion.id.desc(),
            )
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def count_questions(self) -> int:
        """Return the total number of stored questions."""
        return self.count()