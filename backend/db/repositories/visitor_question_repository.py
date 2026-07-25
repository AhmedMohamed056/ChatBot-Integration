"""Repository for :class:`VisitorQuestion` entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import VisitorQuestion
from db.repositories.base import BaseRepository


class VisitorQuestionRepository(BaseRepository[VisitorQuestion]):
    """CRUD + domain-specific queries for visitor questions."""

    model = VisitorQuestion

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Read – domain-specific lookups
    # ------------------------------------------------------------------

    def list_by_phone(self, phone_number: str) -> List[VisitorQuestion]:
        """Return all questions from a given phone number."""
        stmt = (
            select(VisitorQuestion)
            .where(VisitorQuestion.phone_number == phone_number)
            .order_by(VisitorQuestion.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_by_campaign(self, campaign_id: int) -> List[VisitorQuestion]:
        """Return all questions linked to a campaign."""
        stmt = (
            select(VisitorQuestion)
            .where(VisitorQuestion.campaign_id == campaign_id)
            .order_by(VisitorQuestion.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_unanswered(self, limit: Optional[int] = None) -> List[VisitorQuestion]:
        """Return all unanswered questions, newest first."""
        stmt = (
            select(VisitorQuestion)
            .where(VisitorQuestion.answered == False)  # noqa: E712
            .order_by(VisitorQuestion.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def list_answered(self, limit: Optional[int] = None) -> List[VisitorQuestion]:
        """Return all answered questions, newest first."""
        stmt = (
            select(VisitorQuestion)
            .where(VisitorQuestion.answered == True)  # noqa: E712
            .order_by(VisitorQuestion.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def list_in_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> List[VisitorQuestion]:
        """Return questions created within ``[start, end)``."""
        stmt = (
            select(VisitorQuestion)
            .where(VisitorQuestion.created_at >= start)
            .where(VisitorQuestion.created_at < end)
            .order_by(VisitorQuestion.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_top_questions(self, limit: int = 10) -> List[tuple[str, int]]:
        """Return the most frequently asked questions.

        Returns a list of ``(question, count)`` tuples.
        """
        from sqlalchemy import func

        stmt = (
            select(
                func.lower(VisitorQuestion.question).label("q"),
                func.count().label("c"),
            )
            .group_by("q")
            .order_by(func.count().desc(), "q")
            .limit(limit)
        )
        return [
            (row.q, row.c)
            for row in self.session.execute(stmt).all()
        ]

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def ask(
        self,
        question: str,
        phone_number: Optional[str] = None,
        detected_campaign: Optional[str] = None,
        campaign_id: Optional[int] = None,
        ai_answer: Optional[str] = None,
        answered: bool = False,
    ) -> VisitorQuestion:
        """Record a visitor question.

        Convenience wrapper around :meth:`create`.
        """
        data: dict[str, Any] = {
            "question": question,
            "phone_number": phone_number,
            "detected_campaign": detected_campaign,
            "campaign_id": campaign_id,
            "ai_answer": ai_answer,
            "answered": answered,
        }
        return self.create(data)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def mark_answered(
        self,
        question_id: int,
        ai_answer: Optional[str] = None,
    ) -> Optional[VisitorQuestion]:
        """Mark a question as answered, optionally storing the AI answer."""
        data: dict[str, Any] = {"answered": True}
        if ai_answer is not None:
            data["ai_answer"] = ai_answer
        return self.update_by_id(question_id, data)

    def mark_unanswered(self, question_id: int) -> Optional[VisitorQuestion]:
        """Mark a question as unanswered."""
        return self.update_by_id(question_id, {"answered": False})