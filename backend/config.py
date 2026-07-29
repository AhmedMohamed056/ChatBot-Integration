"""Application configuration module.

Runtime supervisor authorization uses active PostgreSQL records.
Legacy ``supervisor_phones`` settings remain a fallback during cutover.
"""

import json
import logging
import sys
from pathlib import Path

file_path = Path(__file__).resolve()
parent_dir = file_path.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from database import get_setting, normalize_phone, set_setting

logger = logging.getLogger(__name__)

SUPERVISOR_PHONES_KEY = "supervisor_phones"


def get_supervisor_phones() -> list[str]:
    phones_str = get_setting(SUPERVISOR_PHONES_KEY, "")
    if not phones_str:
        return []
    phones_str = phones_str.strip()
    if phones_str.startswith("[") and phones_str.endswith("]"):
        try:
            return json.loads(phones_str)
        except json.JSONDecodeError:
            return []
    return [p.strip() for p in phones_str.split(",") if p.strip()]


def set_supervisor_phones(phones: list[str]) -> None:
    set_setting(SUPERVISOR_PHONES_KEY, json.dumps(phones))


def _legacy_is_supervisor(phone: str) -> bool:
    supervisor_phones = get_supervisor_phones()
    normalized_phone = normalize_phone(phone)
    return normalized_phone in [normalize_phone(p) for p in supervisor_phones]


def is_supervisor(phone: str) -> bool:
    try:
        from db.base import get_session
        from services.supervisor_authorization_service import is_active_supervisor

        with get_session() as session:
            if is_active_supervisor(session, phone):
                return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("DB supervisor check failed, using legacy settings: %s", exc)
    return _legacy_is_supervisor(phone)
