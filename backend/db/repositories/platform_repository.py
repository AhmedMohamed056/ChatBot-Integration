"""Persistence primitives used by later application-service phases."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Campaign
from db.platform_models import IdempotencyKey, OutboxEvent, Supervisor
from db.repositories.base import BaseRepository


class SupervisorRepository(BaseRepository[Supervisor]):
    model = Supervisor

    def get_by_phone(self, phone_number: str) -> Optional[Supervisor]:
        return self.session.scalar(
            select(Supervisor).where(Supervisor.phone_number == phone_number)
        )

    def get_active_by_phone(self, phone_number: str) -> Optional[Supervisor]:
        return self.session.scalar(
            select(Supervisor).where(
                Supervisor.phone_number == phone_number,
                Supervisor.is_active.is_(True),
            )
        )


class CampaignOwnershipRepository:
    """Read-only ownership checks; mutation belongs to later domain services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def supervisor_owns(self, supervisor_id: int, campaign_id: int) -> bool:
        return (
            self.session.scalar(
                select(Campaign.id).where(
                    Campaign.id == campaign_id,
                    Campaign.owner_supervisor_id == supervisor_id,
                )
            )
            is not None
        )


class IdempotencyRepository(BaseRepository[IdempotencyKey]):
    model = IdempotencyKey

    def get_valid(
        self, scope: str, key: str, now: datetime
    ) -> Optional[IdempotencyKey]:
        return self.session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == scope,
                IdempotencyKey.key == key,
                IdempotencyKey.expires_at > now,
            )
        )


class OutboxRepository(BaseRepository[OutboxEvent]):
    model = OutboxEvent

    def enqueue(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        return self.create(
            {
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": payload,
            }
        )

    def list_pending(self, now: datetime, limit: int = 100) -> list[OutboxEvent]:
        return list(
            self.session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.available_at <= now,
                )
                .order_by(OutboxEvent.id)
                .limit(limit)
            )
        )
