"""Application configuration module.

This module provides centralized configuration management for the application.
It uses the database system_settings table for persistent configuration.
"""

import sys
from pathlib import Path

# Add backend directory to path for imports
file_path = Path(__file__).resolve()
parent_dir = file_path.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from database import get_setting, set_setting

# Supervisor phone numbers configuration key
SUPERVISOR_PHONES_KEY = "supervisor_phones"

def get_supervisor_phones() -> list[str]:
    """Get the list of supervisor phone numbers from configuration.

    Returns:
        list[str]: List of supervisor phone numbers.
    """
    phones_str = get_setting(SUPERVISOR_PHONES_KEY, "")
    if not phones_str:
        return []
    # Parse comma-separated or JSON array format
    phones_str = phones_str.strip()
    if phones_str.startswith('[') and phones_str.endswith(']'):
        # JSON array format
        import json
        try:
            return json.loads(phones_str)
        except json.JSONDecodeError:
            return []
    # Comma-separated format
    return [p.strip() for p in phones_str.split(',') if p.strip()]

def set_supervisor_phones(phones: list[str]) -> None:
    """Set the list of supervisor phone numbers in configuration.

    Args:
        phones: List of supervisor phone numbers.
    """
    import json
    set_setting(SUPERVISOR_PHONES_KEY, json.dumps(phones))

def is_supervisor(phone: str) -> bool:
    """Check if a phone number belongs to a supervisor.

    Args:
        phone: The phone number to check.

    Returns:
        bool: True if the phone is in the supervisor list, False otherwise.
    """
    from database import normalize_phone
    supervisor_phones = get_supervisor_phones()
    normalized_phone = normalize_phone(phone)
    return normalized_phone in [normalize_phone(p) for p in supervisor_phones]
