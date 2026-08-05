"""Intelligent campaign description generation using Gemini.

Generates final campaign descriptions by understanding the operation type
(replace, append, modify, remove) and applying it intelligently to the
current description.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "أنت محرر نصوص محترف لأوصاف الحملات الإعلانية. "
    "مهمتك تطبيق طلب المشرف على الوصف الحالي وإخراج النص النهائي فقط، "
    "بدون أي مقدمة أو شرح أو علامات تنسيق."
)


def _get_client():
    """Build a GeminiClient using the same runtime settings the visitor flow uses.

    Returns None on any failure so callers fall back to a deterministic merge.
    """
    try:
        from gemini_client import GeminiClient
        from database import get_setting
        from services.runtime_settings import apply_runtime_env

        apply_runtime_env()
        api_key = get_setting("gemini_api_key") or None
        model = get_setting("gemini_model") or None
        return GeminiClient(api_key=api_key, model_name=model)
    except Exception as exc:  # noqa: BLE001
        logger.warning("GeminiClient unavailable for description generation: %s", exc)
        return None


class OperationType:
    """Campaign edit operation types."""
    REPLACE = "replace"
    APPEND = "append"
    MODIFY = "modify"
    REMOVE = "remove"


def detect_operation_type(message: str) -> str:
    """Detect the operation type from the supervisor's message.

    Returns one of: replace, append, modify, remove
    """
    text = message.lower()

    # Replace indicators
    replace_keywords = ["غير", "استبدل", "بدل", "replace", "change to"]
    if any(kw in text for kw in replace_keywords):
        # Check if it's a complete replacement or partial modification
        if any(phrase in text for phrase in ["إلى", "بالكامل", "كل", "كامل"]):
            return OperationType.REPLACE
        # Otherwise it's a modification
        return OperationType.MODIFY

    # Append indicators
    append_keywords = ["أضف", "زود", "أضف معلومة", "add", "append"]
    if any(kw in text for kw in append_keywords):
        return OperationType.APPEND

    # Modify indicators
    modify_keywords = ["عدل", "صحح", "modify", "correct", "update"]
    if any(kw in text for kw in modify_keywords):
        return OperationType.MODIFY

    # Remove indicators
    remove_keywords = ["احذف", "شيل", "امسح", "delete", "remove"]
    if any(kw in text for kw in remove_keywords):
        return OperationType.REMOVE

    # Default to modify for ambiguous cases
    return OperationType.MODIFY


def generate_final_description(
    current_description: str,
    supervisor_request: str,
    operation: str,
) -> str:
    """Generate the final campaign description using Gemini.

    Args:
        current_description: The current approved campaign description
        supervisor_request: The supervisor's edit request message
        operation: One of: replace, append, modify, remove

    Returns:
        The final description to be persisted
    """
    client = _get_client()
    if client is None:
        return _fallback_merge(current_description, supervisor_request, operation)

    prompt = _build_generation_prompt(current_description, supervisor_request, operation)

    try:
        response = client.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.1,
            max_output_tokens=2048,
        )
        final_description = (response or "").strip()

        # Validate the result: an empty or absurdly short reply means the model
        # failed to follow the instruction — fall back deterministically.
        if len(final_description) < 5:
            logger.warning("Gemini returned invalid description, using fallback")
            return _fallback_merge(current_description, supervisor_request, operation)

        return final_description
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to generate description with Gemini: %s", exc)
        return _fallback_merge(current_description, supervisor_request, operation)


def _build_generation_prompt(
    current_description: str,
    supervisor_request: str,
    operation: str,
) -> str:
    """Build the prompt for Gemini to generate the final description."""

    operation_instructions = {
        OperationType.REPLACE: """استبدل الوصف الحالي بالكامل بالمحتوى الجديد المطلوب.
احذف كل المحتوى القديم وضع المحتوى الجديد فقط.""",

        OperationType.APPEND: """أضف المعلومات الجديدة إلى نهاية الوصف الحالي.
احتفظ بكل المحتوى الموجود وأضف المعلومات الجديدة بشكل طبيعي ومتناسق.""",

        OperationType.MODIFY: """عدل الجزء المحدد فقط من الوصف.
احتفظ بكل المعلومات الأخرى واحذف أو عدل فقط الجزء المطلوب تعديله.""",

        OperationType.REMOVE: """احذف المعلومات المحددة من الوصف.
احتفظ بكل المعلومات الأخرى واحذف فقط الجزء المطلوب حذفه.""",
    }

    instruction = operation_instructions.get(operation, operation_instructions[OperationType.MODIFY])

    prompt = f"""أنت مساعد ذكي لتحرير أوصاف الحملات.

**الوصف الحالي المعتمد:**
{current_description}

**طلب المشرف:**
{supervisor_request}

**العملية المطلوبة:** {operation}

**التعليمات:**
{instruction}

**القواعد المهمة:**
1. أخرج الوصف النهائي فقط، بدون مقدمة أو تفسير
2. احتفظ بالأسلوب واللغة المستخدمة في الوصف الأصلي
3. تأكد من أن النص النهائي متماسك ومفهوم
4. لا تضف معلومات لم يطلبها المشرف
5. إذا كانت العملية "استبدال"، اكتب الوصف الجديد كاملاً من طلب المشرف
6. إذا كانت العملية "إضافة"، اجعل الإضافة طبيعية ومتصلة بالنص الموجود
7. إذا كانت العملية "تعديل"، غير فقط الجزء المحدد
8. إذا كانت العملية "حذف"، احذف فقط المعلومات المحددة

**الوصف النهائي:**"""

    return prompt


def _fallback_merge(
    current_description: str,
    supervisor_request: str,
    operation: str,
) -> str:
    """Fallback merge logic when Gemini is not available."""

    if operation == OperationType.REPLACE:
        # Complete replacement
        return supervisor_request.strip()

    if operation == OperationType.APPEND:
        # Append with natural connector
        return f"{current_description}\n{supervisor_request}".strip()

    if operation == OperationType.MODIFY:
        # For modify, we can't do intelligent partial replacement without Gemini
        # So we treat it as append with a note
        return f"{current_description}\n[تعديل]: {supervisor_request}".strip()

    if operation == OperationType.REMOVE:
        # For remove, we also can't do intelligent removal without Gemini
        # Return current description unchanged with a warning
        logger.warning("Cannot perform intelligent removal without Gemini")
        return current_description

    # Default: return the request as new description
    return supervisor_request.strip()
