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
from services.conversation_memory_service import ConversationMemoryService
from services.conversation_service import ConversationService
from services.intent_router import Intent, detect_intent
from services.platform_admin_service import record_audit
from services.supervisor_context_service import (
    build_supervisor_context,
    build_supervisor_greeting,
    get_owned_campaign,
    seed_draft_from_campaign,
)
from visitor_flow import VisitorFlow


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
        # Initialize memory service
        memory_service = ConversationMemoryService(self.session)
        
        # Update memory with inbound message
        memory_service.update_memory_from_message(
            conversation_id=conversation_id,
            message=message,
            direction="inbound",
            sender_phone=supervisor.phone_number
        )
        
        owned = get_owned_campaign(self.session, supervisor.id)
        state = self.conversations.get_state(conversation_id)
        data = dict(state.state_data or {})
        draft = dict(data.get("draft") or {})
        operation = str(draft.get("operation") or data.get("operation") or "update")
        pending = state.state_name == "WAITING_FOR_CONFIRMATION"
        intent_result = detect_intent(message, pending_confirmation=pending)

        # A "command trigger" is the very first mutation message that opens a
        # draft (e.g. "غير وصف الحملة") sent from a non-collecting state. Its
        # text is a COMMAND, never content — so it must not populate the
        # description and must not jump to confirmation. Content only arrives on
        # later turns (a missing-field reply, or a correction while confirming),
        # which are always in one of the collecting states below.
        _COLLECTING_STATES = {
            "COLLECTING",
            "WAITING_FOR_MISSING_FIELD",
            "WAITING_FOR_CONFIRMATION",
        }
        is_command_trigger = (
            not pending
            and state.state_name not in _COLLECTING_STATES
            and intent_result.intent
            in {Intent.CREATE_CAMPAIGN, Intent.UPDATE_CAMPAIGN}
        )

        if intent_result.intent == Intent.CANCEL:
            self.conversations.set_state(
                state, state_name="IDLE", state_data={"draft": {}, "missing": []}
            )
            # Clear task state in memory (set to IDLE)
            memory_service.set_idle(conversation_id)
            reply = "تم إلغاء العملية. يمكنك البدء من جديد عند الحاجة."
            # Update memory with outbound response
            memory_service.update_memory_from_message(
                conversation_id=conversation_id,
                message=reply,
                direction="outbound",
                sender_phone=None,
                response=None
            )
            return reply

        if intent_result.intent == Intent.CONFIRM_OK and pending:
            # Persist the ORIGINAL business request captured when the workflow
            # first started (e.g. "غير وصف الحملة"), not the confirmation word
            # ("نعم"/"OK") that triggers this turn. Fall back to the current
            # message only if the request was never stored.
            business_request = draft.get("original_request") or original_message
            reply = self._commit(
                supervisor, state, draft, business_request, operation=operation
            )
            # Clear task state in memory after successful commit
            memory_service.set_idle(conversation_id)
            # Update memory with outbound response
            memory_service.update_memory_from_message(
                conversation_id=conversation_id,
                message=reply,
                direction="outbound",
                sender_phone=None,
                response=None
            )
            return reply

        if intent_result.intent == Intent.DELETE_CAMPAIGN:
            operation = "delete"
            data["operation"] = operation
            # Capture the first business request that triggered the workflow
            draft.setdefault("original_request", message)
            draft.setdefault("campaign_name", owned.campaign_name if owned else "")
            if not draft.get("deletion_reason"):
                data["draft"] = draft
                self.conversations.set_state(
                    state,
                    state_name="WAITING_FOR_MISSING_FIELD",
                    state_data=data,
                )
                reply = "من فضلك أرسل سبب الحذف فقط."
                # Update memory with outbound response
                memory_service.update_memory_from_message(
                    conversation_id=conversation_id,
                    message=reply,
                    direction="outbound",
                    sender_phone=None,
                    response=None
                )
                return reply

        if intent_result.intent in {
            Intent.CREATE_CAMPAIGN,
            Intent.UPDATE_CAMPAIGN,
        } or state.state_name in {"COLLECTING", "WAITING_FOR_MISSING_FIELD"}:
            # Capture the first business request that triggered the workflow.
            # setdefault ensures later turns (new description, missing field)
            # never overwrite the original request.
            draft.setdefault("original_request", message)
            if owned and not draft.get("campaign_name"):
                draft.update(seed_draft_from_campaign(owned))
                # A fresh mutation command must not inherit the campaign's
                # existing description as the new candidate value — the
                # supervisor is asked for fresh content instead.
                if is_command_trigger:
                    draft.pop("description", None)
            extraction = extract_campaign_update(message)
            if extraction is not None:
                if extraction.operation:
                    operation = extraction.operation
                    data["operation"] = operation
                if extraction.campaign_name and not owned:
                    draft["campaign_name"] = extraction.campaign_name
            # The command sentence itself (e.g. "غير وصف الحملة") must NEVER
            # become the description. Only merge content from genuine content
            # turns — never from the initial command that opened the draft.
            if not is_command_trigger:
                self._merge_extraction(draft, message, operation, owned=owned)
            missing = _missing_fields(draft, operation=operation)
            if missing:
                data["draft"] = draft
                data["missing"] = missing
                self.conversations.set_state(
                    state,
                    state_name="WAITING_FOR_MISSING_FIELD",
                    state_data=data,
                )
                reply = (
                    f"من فضلك أرسل {_field_label(missing[0])} فقط "
                    "(سؤال واحد في كل مرة)."
                )
                # Update memory with outbound response
                memory_service.update_memory_from_message(
                    conversation_id=conversation_id,
                    message=reply,
                    direction="outbound",
                    sender_phone=None,
                    response=None
                )
                return reply
            data["draft"] = draft
            data["missing"] = []
            self.conversations.set_state(
                state,
                state_name="WAITING_FOR_CONFIRMATION",
                state_data=data,
            )
            reply = self._review_summary(draft, operation=operation, owned=owned)
            # Update memory with outbound response
            memory_service.update_memory_from_message(
                conversation_id=conversation_id,
                message=reply,
                direction="outbound",
                sender_phone=None,
                response=None
            )
            return reply

        if intent_result.intent == Intent.KNOWLEDGE_QUESTION:
            reply = (
                "في المحادثة الخاصة أساعدك في إدارة حملتك فقط. "
                "لأسئلة المعرفة استخدم المجموعة، أو اطلب تحديث الحملة هنا."
            )
            # Update memory with outbound response
            memory_service.update_memory_from_message(
                conversation_id=conversation_id,
                message=reply,
                direction="outbound",
                sender_phone=None,
                response=None
            )
            return reply

        # Fallback for general questions - call AI with supervisor context
        # Build supervisor context for injection into AI requests
        supervisor_context = build_supervisor_context(
            self.session, supervisor, conversation_id
        )

        # Create a custom VisitorFlow that injects supervisor context
        visitor_flow = VisitorFlow()
        result = visitor_flow.handle_message_with_supervisor(
            phone=supervisor.phone_number,
            message=message,
            supervisor_context=supervisor_context,
            conversation_id=conversation_id
        )

        # Update memory with the response
        if result.handled and result.reply:
            memory_service.update_memory_from_message(
                conversation_id=conversation_id,
                message=result.reply,
                direction="outbound",
                sender_phone=None,
                response=None
            )

        # A supervisor asking a general knowledge question in private is a
        # visitor knowledge question too — record it into the SAME dashboard
        # pipeline as website/group questions (no parallel reporting system).
        from whatsapp_question_log import log_whatsapp_question

        log_whatsapp_question(message, result.reply, phone=supervisor.phone_number)

        return result.reply if result.handled else ""

    def _merge_extraction(
        self,
        draft: dict[str, Any],
        message: str,
        operation: str,
        *,
        owned: Optional[Campaign] = None,
    ) -> None:
        text = message.strip()
        if operation == "delete":
            if not draft.get("deletion_reason"):
                draft["deletion_reason"] = text
            return
        if not text:
            return

        # The edit operation (replace/append/modify/remove) is carried by the
        # ORIGINAL command that opened the draft (e.g. "أضف معلومة"، "احذف"),
        # not by this content turn — the content turn is the payload to apply.
        from services.campaign_description_generator import (
            detect_operation_type,
            generate_final_description,
        )

        current_description = ((owned.description if owned else "") or "").strip()
        op_type = detect_operation_type(draft.get("original_request") or "")

        # With no existing description, or an explicit full replacement, the
        # content turn IS the new description — no merge needed. Otherwise ask
        # the generator to apply the operation against the approved text.
        if not current_description or op_type == "replace":
            draft["description"] = text
        else:
            draft["description"] = generate_final_description(
                current_description=current_description,
                supervisor_request=text,
                operation=op_type,
            )

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

        # Build comprehensive campaign snapshot with all available information
        snapshot = {
            "campaign_name": campaign.campaign_name,
            "description": campaign.description,
            "campaign_type": campaign.campaign_type,
            "start_date": str(campaign.start_date) if campaign.start_date else None,
            "end_date": str(campaign.end_date) if campaign.end_date else None,
            "status": campaign.status,
            "notes": campaign.notes,
            "lock_version": campaign.lock_version,
            "owner_supervisor_id": campaign.owner_supervisor_id,
            "current_version": version_number,
            "created_at": str(campaign.created_at) if campaign.created_at else None,
            "updated_at": str(campaign.updated_at) if campaign.updated_at else None,
        }

        # Include owner/supervisor information
        if campaign.owner:
            snapshot["owner"] = {
                "supervisor_id": campaign.owner.id,
                "phone_number": campaign.owner.phone_number,
                "display_name": campaign.owner.display_name,
                "is_active": campaign.owner.is_active,
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
        record_audit(
            self.session,
            action="campaign.create" if created else "campaign.update",
            entity_type="campaign",
            entity_id=str(campaign.id),
            actor_id=supervisor.phone_number,
            actor_type="supervisor",
            after_data=snapshot,
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
        record_audit(
            self.session,
            action="campaign.delete",
            entity_type="campaign",
            entity_id=str(campaign.id),
            actor_id=supervisor.phone_number,
            actor_type="supervisor",
            before_data={"status": "active"},
            after_data={"status": "deleted"},
        )
        self.conversations.set_state(
            state, state_name="IDLE", state_data={"draft": {}, "missing": []}
        )
        reason = draft.get("deletion_reason", "")
        return f"تم وضع علامة حذف على حملتك. السبب: {reason}"
