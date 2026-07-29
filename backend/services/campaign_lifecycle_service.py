"""Supervisor campaign draft, review, and versioned commit."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from campaign_update_extraction_service import extract_campaign_update
from db.models import Campaign, CampaignUpdate
from db.platform_models import CampaignVersion, Supervisor
from db.repositories.platform_repository import OutboxRepository
from services.conversation_service import ConversationService
from services.intent_router import Intent, detect_intent
from services.supervisor_context_service import (
    build_supervisor_greeting,
    get_owned_campaign,
    seed_draft_from_campaign,
)


REQUIRED_FIELDS = ("description",)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _missing_fields(draft: dict[str, Any], *, operation: str) -> list[str]:
    missing = []
    if operation != "delete":
        for key in REQUIRED_FIELDS:
            value = draft.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(key)
    if operation == "delete" and not (draft.get("deletion_reason") or "").strip():
        missing.append("deletion_reason")
    return missing


def _field_label(field: str) -> str:
    labels = {
        "description": "الوصف أو نص الإعلان",
        "deletion_reason": "سبب الحذف",
        "campaign_name": "اسم الحملة",
        "start_date": "تاريخ البداية",
        "end_date": "تاريخ النهاية",
        "location": "الموقع",
    }
    return labels.get(field, field)


class CampaignLifecycleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.conversations = ConversationService(session)
        self.outbox = OutboxRepository(session)

    def handle(
        self,
        *,
        supervisor: Supervisor,
        conversation_id: int,
        message: str,
        original_message: str,
    ) -> str:
        owned = get_owned_campaign(self.session, supervisor.id)
        state = self.conversations.get_state(conversation_id)
        data = dict(state.state_data or {})
        draft = dict(data.get("draft") or {})
        operation = str(draft.get("operation") or data.get("operation") or "update")
        pending = state.state_name == "WAITING_FOR_CONFIRMATION"
        intent_result = detect_intent(message, pending_confirmation=pending)

        if intent_result.intent == Intent.CANCEL:
            self.conversations.set_state(
                state, state_name="IDLE", state_data={"draft": {}, "missing": []}
            )
            return "تم إلغاء العملية. يمكنك البدء من جديد عند الحاجة."

        if intent_result.intent == Intent.CONFIRM_OK and pending:
            return self._commit(
                supervisor, state, draft, original_message, operation=operation
            )

        if intent_result.intent == Intent.GREETING and state.state_name == "IDLE":
            if owned and not draft:
                draft = seed_draft_from_campaign(owned)
                data["draft"] = draft
                data["operation"] = "update"
                self.conversations.set_state(
                    state, state_name="IDLE", state_data=data
                )
            return build_supervisor_greeting(
                self.session, supervisor, conversation_id
            )

        if intent_result.intent == Intent.DELETE_CAMPAIGN:
            operation = "delete"
            data["operation"] = operation
            draft.setdefault("campaign_name", owned.campaign_name if owned else "")
            if not draft.get("deletion_reason"):
                data["draft"] = draft
                self.conversations.set_state(
                    state,
                    state_name="WAITING_FOR_MISSING_FIELD",
                    state_data=data,
                )
                return "من فضلك أرسل سبب الحذف فقط."

        if intent_result.intent in {
            Intent.CREATE_CAMPAIGN,
            Intent.UPDATE_CAMPAIGN,
        } or state.state_name in {"COLLECTING", "WAITING_FOR_MISSING_FIELD"}:
            if owned and not draft.get("campaign_name"):
                draft.update(seed_draft_from_campaign(owned))
            extraction = extract_campaign_update(message)
            if extraction is not None:
                if extraction.operation:
                    operation = extraction.operation
                    data["operation"] = operation
                if extraction.campaign_name and not owned:
                    draft["campaign_name"] = extraction.campaign_name
            self._merge_extraction(draft, message, operation)
            missing = _missing_fields(draft, operation=operation)
            if missing:
                data["draft"] = draft
                data["missing"] = missing
                self.conversations.set_state(
                    state,
                    state_name="WAITING_FOR_MISSING_FIELD",
                    state_data=data,
                )
                return (
                    f"من فضلك أرسل {_field_label(missing[0])} فقط "
                    "(سؤال واحد في كل مرة)."
                )
            data["draft"] = draft
            data["missing"] = []
            self.conversations.set_state(
                state,
                state_name="WAITING_FOR_CONFIRMATION",
                state_data=data,
            )
            return self._review_summary(draft, operation=operation, owned=owned)

        if intent_result.intent == Intent.KNOWLEDGE_QUESTION:
            return (
                "في المحادثة الخاصة أساعدك في إدارة حملتك فقط. "
                "لأسئلة المعرفة استخدم المجموعة، أو اطلب تحديث الحملة هنا."
            )

        return build_supervisor_greeting(self.session, supervisor, conversation_id)

    def _merge_extraction(
        self, draft: dict[str, Any], message: str, operation: str
    ) -> None:
        text = message.strip()
        if operation == "delete":
            if not draft.get("deletion_reason"):
                draft["deletion_reason"] = text
            return
        if text:
            draft["description"] = text
        for token in text.split():
            if token.count("-") == 2 and len(token) >= 8:
                if not draft.get("start_date"):
                    draft["start_date"] = token
                elif not draft.get("end_date"):
                    draft["end_date"] = token

    def _review_summary(
        self,
        draft: dict[str, Any],
        *,
        operation: str,
        owned: Optional[Campaign],
    ) -> str:
        campaign_label = (
            draft.get("campaign_name")
            or (owned.campaign_name if owned else "")
            or "(حملتك)"
        )
        lines = [
            "راجع الملخص التالي:",
            f"- العملية: {operation}",
            f"- الحملة: {campaign_label}",
            f"- الوصف: {draft.get('description', '')}",
            f"- البداية: {draft.get('start_date', '')}",
            f"- النهاية: {draft.get('end_date', '')}",
            f"- الموقع: {draft.get('location', '')}",
        ]
        if operation == "delete":
            lines.append(f"- سبب الحذف: {draft.get('deletion_reason', '')}")
        lines.extend(
            [
                "",
                "Reply OK / Yes / Confirm / نعم / موافق to save, or send corrections.",
            ]
        )
        return "\n".join(lines)

    def _commit(
        self,
        supervisor: Supervisor,
        state,
        draft: dict[str, Any],
        original_message: str,
        *,
        operation: str,
    ) -> str:
        owned = get_owned_campaign(self.session, supervisor.id)
        if owned is None and operation != "create":
            return "لا توجد حملة مرتبطة بك. تواصل مع الإدارة لإتمام الاستيراد."

        requested = (draft.get("campaign_name") or "").strip()
        if owned and requested and requested != owned.campaign_name:
            return "You cannot modify a campaign you do not own."

        if operation == "delete":
            if owned is None:
                return "لا توجد حملة لحذفها."
            return self._tombstone_campaign(
                supervisor, owned, state, draft, original_message
            )

        campaign = owned
        created = campaign is None
        if created:
            name = draft.get("campaign_name") or f"Campaign-{supervisor.id}"
            campaign = Campaign(
                campaign_name=name,
                owner_supervisor_id=supervisor.id,
                description=draft.get("description"),
                start_date=draft.get("start_date"),
                end_date=draft.get("end_date"),
                notes=draft.get("location"),
                status="active",
            )
            self.session.add(campaign)
            self.session.flush()
        else:
            if campaign.owner_supervisor_id != supervisor.id:
                return "لا يمكنك تعديل حملة لا تملكها."
            campaign.description = draft.get("description") or campaign.description
            if draft.get("location"):
                campaign.notes = draft.get("location")

        version_number = (
            self.session.scalar(
                select(CampaignVersion.version_number)
                .where(CampaignVersion.campaign_id == campaign.id)
                .order_by(CampaignVersion.version_number.desc())
            )
            or 0
        ) + 1

        snapshot = {
            "campaign_name": campaign.campaign_name,
            "description": campaign.description,
            "start_date": str(campaign.start_date) if campaign.start_date else None,
            "end_date": str(campaign.end_date) if campaign.end_date else None,
            "location": campaign.notes,
        }
        self.session.add(
            CampaignVersion(
                campaign_id=campaign.id,
                version_number=version_number,
                snapshot=snapshot,
                change_reason="supervisor_whatsapp_commit",
                created_by_supervisor_id=supervisor.id,
            )
        )
        self.session.add(
            CampaignUpdate(
                campaign_id=campaign.id,
                update_type="create" if created else "field_change",
                changed_field="snapshot",
                new_value=str(snapshot),
                source="whatsapp",
                message_text=original_message,
                updated_by=supervisor.phone_number,
            )
        )
        self.outbox.enqueue(
            aggregate_type="campaign",
            aggregate_id=str(campaign.id),
            event_type="campaign.version.approved",
            payload={
                "campaign_id": campaign.id,
                "version_number": version_number,
                "snapshot": snapshot,
            },
        )
        self.conversations.set_state(
            state, state_name="IDLE", state_data={"draft": {}, "missing": []}
        )
        return "تم حفظ الحملة بنجاح بعد التأكيد."

    def _tombstone_campaign(
        self,
        supervisor: Supervisor,
        campaign: Campaign,
        state,
        draft: dict[str, Any],
        original_message: str,
    ) -> str:
        if campaign.owner_supervisor_id != supervisor.id:
            return "لا يمكنك حذف حملة لا تملكها."
        campaign.status = "deleted"
        self.session.add(
            CampaignUpdate(
                campaign_id=campaign.id,
                update_type="status_change",
                changed_field="status",
                old_value="active",
                new_value="deleted",
                source="whatsapp",
                message_text=original_message,
                updated_by=supervisor.phone_number,
            )
        )
        self.outbox.enqueue(
            aggregate_type="campaign",
            aggregate_id=str(campaign.id),
            event_type="campaign.deleted",
            payload={"campaign_id": campaign.id},
        )
        self.conversations.set_state(
            state, state_name="IDLE", state_data={"draft": {}, "missing": []}
        )
        reason = draft.get("deletion_reason", "")
        return f"تم وضع علامة حذف على حملتك. السبب: {reason}"
