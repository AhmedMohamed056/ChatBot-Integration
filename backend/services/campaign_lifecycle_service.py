"""Supervisor campaign draft, review, and versioned commit."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Campaign, CampaignUpdate
from db.platform_models import CampaignVersion, Supervisor
from db.repositories.platform_repository import OutboxRepository
from services.conversation_service import ConversationService
from services.intent_router import Intent, IntentResult, detect_intent


REQUIRED_FIELDS = ("campaign_name", "description", "start_date", "end_date", "location")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _missing_fields(draft: dict[str, Any]) -> list[str]:
    missing = []
    for key in REQUIRED_FIELDS:
        value = draft.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    return missing


def _field_label(field: str) -> str:
    labels = {
        "campaign_name": "اسم الحملة",
        "description": "الوصف",
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
        state = self.conversations.get_state(conversation_id)
        data = dict(state.state_data or {})
        draft = dict(data.get("draft") or {})
        pending = state.state_name == "WAITING_FOR_CONFIRMATION"
        intent_result = detect_intent(message, pending_confirmation=pending)

        if intent_result.intent == Intent.CANCEL:
            self.conversations.set_state(
                state, state_name="IDLE", state_data={"draft": {}, "missing": []}
            )
            return "تم إلغاء العملية. يمكنك البدء من جديد عند الحاجة."

        if intent_result.intent == Intent.CONFIRM_OK and pending:
            return self._commit(supervisor, state, draft, original_message)

        if intent_result.intent in {
            Intent.CREATE_CAMPAIGN,
            Intent.UPDATE_CAMPAIGN,
        } or state.state_name in {"COLLECTING", "WAITING_FOR_MISSING_FIELD"}:
            self._merge_extraction(draft, message)
            missing = _missing_fields(draft)
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
            return self._review_summary(draft)

        if intent_result.intent == Intent.GREETING:
            return (
                f"أهلاً وسهلاً أستاذ {supervisor.display_name or ''}. "
                "هل تريد إنشاء حملة جديدة أو تحديث حملتك؟"
            ).strip()

        if intent_result.intent == Intent.DELETE_CAMPAIGN:
            return (
                "لحذف حملتك، أرسل سبب الحذف ثم سنطلب منك المراجعة وال replying بـ OK."
            )

        return (
            "يمكنني مساعدتك في إنشاء أو تحديث حملتك في هذه المحادثة الخاصة. "
            "ما التغيير الذي تريده؟"
        )

    def _merge_extraction(self, draft: dict[str, Any], message: str) -> None:
        text = message.strip()
        if not draft.get("campaign_name") and len(text) > 3 and "حملة" in text:
            draft.setdefault("description", text)
        elif "description" not in draft or not draft["description"]:
            draft["description"] = text
        for token in text.split():
            if token.count("-") == 2 and len(token) >= 8:
                if not draft.get("start_date"):
                    draft["start_date"] = token
                elif not draft.get("end_date"):
                    draft["end_date"] = token

    def _review_summary(self, draft: dict[str, Any]) -> str:
        lines = [
            "راجع الملخص التالي:",
            f"- اسم الحملة: {draft.get('campaign_name') or '(يُحدد من ملكيتك)'}",
            f"- الوصف: {draft.get('description', '')}",
            f"- البداية: {draft.get('start_date', '')}",
            f"- النهاية: {draft.get('end_date', '')}",
            f"- الموقع: {draft.get('location', '')}",
            "",
            "Reply with OK to save, or send corrections.",
        ]
        return "\n".join(lines)

    def _commit(
        self,
        supervisor: Supervisor,
        state,
        draft: dict[str, Any],
        original_message: str,
    ) -> str:
        campaign = self.session.scalar(
            select(Campaign).where(Campaign.owner_supervisor_id == supervisor.id)
        )
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
            payload={"campaign_id": campaign.id, "version_number": version_number},
        )
        self.conversations.set_state(
            state, state_name="IDLE", state_data={"draft": {}, "missing": []}
        )
        return "تم حفظ الحملة بنجاح بعد تأكيد OK."
