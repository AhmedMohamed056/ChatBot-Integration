"""Admin dashboard reads and privileged campaign operations (PostgreSQL)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from db.models import Campaign, CampaignUpdate, VisitorQuestion
from db.platform_models import AuditEvent, CampaignVersion, Supervisor


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def list_campaigns_with_stats(session: Session) -> list[dict[str, Any]]:
    campaigns = session.scalars(
        select(Campaign)
        .options(selectinload(Campaign.owner), selectinload(Campaign.updates))
        .order_by(Campaign.updated_at.desc())
    ).all()
    rows: list[dict[str, Any]] = []
    for c in campaigns:
        last_update = None
        if c.updates:
            last_update = max(u.created_at for u in c.updates).isoformat()
        rows.append(
            {
                "id": c.id,
                "name": c.campaign_name,
                "supervisor_name": (c.owner.display_name if c.owner else "") or "",
                "whatsapp_number": (c.owner.phone_number if c.owner else "") or "",
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else "",
                "last_update": last_update,
                "total_updates": len(c.updates),
            }
        )
    return rows


def get_campaign_messages(session: Session, campaign_id: int) -> list[dict[str, Any]]:
    updates = session.scalars(
        select(CampaignUpdate)
        .where(CampaignUpdate.campaign_id == campaign_id)
        .order_by(CampaignUpdate.created_at.desc())
    ).all()
    return [
        {
            "id": u.id,
            "campaign_id": u.campaign_id,
            "campaign_name": "",
            "original_message": u.message_text or "",
            "extracted_info": u.new_value or u.changed_field or "",
            "event_date": None,
            "expires_at": None,
            "created_at": u.created_at.isoformat() if u.created_at else "",
            "is_active": 1,
        }
        for u in updates
    ]


def get_dashboard_stats(session: Session, legacy_stats: dict[str, Any]) -> dict[str, Any]:
    total_campaigns = session.scalar(select(func.count()).select_from(Campaign)) or 0
    total_updates = session.scalar(select(func.count()).select_from(CampaignUpdate)) or 0
    total_supervisors = session.scalar(
        select(func.count()).select_from(Supervisor).where(Supervisor.is_active.is_(True))
    ) or 0
    total_questions = session.scalar(select(func.count()).select_from(VisitorQuestion)) or 0
    unanswered = legacy_stats.get("total_unanswered_questions", 0)
    latest_version = session.scalar(
        select(CampaignVersion)
        .order_by(CampaignVersion.created_at.desc())
        .limit(1)
    )
    latest_campaign_update = None
    if latest_version:
        latest_campaign_update = {
            "campaign_name": latest_version.snapshot.get("campaign_name", ""),
            "created_at": latest_version.created_at.isoformat(),
        }
    return {
        **legacy_stats,
        "total_campaigns": int(total_campaigns),
        "total_campaign_messages": int(total_updates),
        "total_active_supervisors": int(total_supervisors),
        "total_visitor_questions": int(total_questions or legacy_stats.get("total_visitor_questions", 0)),
        "total_unanswered_questions": int(
            unanswered or legacy_stats.get("total_unanswered_questions", 0)
        ),
        "latest_campaign_update": latest_campaign_update
        or legacy_stats.get("latest_campaign_update"),
    }


def record_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_id: str = "admin",
    actor_type: str = "admin",
    before_data: Optional[dict] = None,
    after_data: Optional[dict] = None,
) -> None:
    session.add(
        AuditEvent(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before_data,
            after_data=after_data,
            occurred_at=_utcnow(),
        )
    )


def delete_campaign_transactional(
    session: Session, campaign_id: int, *, actor_id: str = "admin"
) -> bool:
    campaign = session.get(
        Campaign,
        campaign_id,
        options=(selectinload(Campaign.owner),),
    )
    if campaign is None:
        return False
    before = {
        "campaign_name": campaign.campaign_name,
        "owner_supervisor_id": campaign.owner_supervisor_id,
        "status": campaign.status,
    }
    record_audit(
        session,
        action="campaign.delete",
        entity_type="campaign",
        entity_id=str(campaign_id),
        actor_id=actor_id,
        before_data=before,
    )
    session.delete(campaign)
    session.flush()
    return True


def list_audit_events(session: Session, limit: int = 100) -> list[dict[str, Any]]:
    events = session.scalars(
        select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": e.id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "actor_type": e.actor_type,
            "actor_id": e.actor_id,
            "occurred_at": e.occurred_at.isoformat() if e.occurred_at else "",
            "before_data": e.before_data,
            "after_data": e.after_data,
        }
        for e in events
    ]


def list_campaign_versions(session: Session, campaign_id: int) -> list[dict[str, Any]]:
    versions = session.scalars(
        select(CampaignVersion)
        .where(CampaignVersion.campaign_id == campaign_id)
        .order_by(CampaignVersion.version_number.desc())
    ).all()
    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "snapshot": v.snapshot,
            "change_reason": v.change_reason,
            "created_at": v.created_at.isoformat() if v.created_at else "",
        }
        for v in versions
    ]


def get_campaign_activity_report(session: Session) -> list[dict[str, Any]]:
    updates = session.scalars(
        select(CampaignUpdate)
        .options(selectinload(CampaignUpdate.campaign))
        .order_by(CampaignUpdate.created_at.desc())
        .limit(200)
    ).all()
    items = []
    seen: set[int] = set()
    for u in updates:
        if u.campaign_id in seen:
            continue
        seen.add(u.campaign_id)
        name = u.campaign.campaign_name if u.campaign else ""
        items.append(
            {
                "campaign": name,
                "last_message": u.message_text or "",
                "extracted_info": u.new_value or "",
                "date": u.created_at.isoformat() if u.created_at else "",
            }
        )
    return items
