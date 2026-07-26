"""Shared phone-number normalisation helper.

This module is the **single source of truth** for phone-number normalisation
across the whole backend.  Both the Campaign Excel Import system and the
WhatsApp Campaign Detection system import :func:`normalize_phone` from here
so that they always produce identical canonical phone numbers.

Canonical format (Egyptian numbers):
    01012345678   -> 201012345678
    +201012345678 -> 201012345678
    201012345678  -> 201012345678
    0020101234567 -> 201012345678
"""

from __future__ import annotations

import re


def normalize_phone(phone: str) -> str:
    """Normalise a phone number to a canonical international format.

    The rules are intentionally simple and deterministic so that the same
    visitor is always matched regardless of how their number was typed:

    1. Strip every non-digit character.
    2. Drop a leading ``00`` (international prefix).
    3. Drop a leading single ``0`` (local format) and prepend the country
       code ``20`` (Egypt).

    Returns an empty string for falsy / empty input.
    """
    if not phone:
        return ""

    # Extract digits only
    digits = re.sub(r"\D", "", str(phone))

    # Remove leading double-zero (international prefix)
    if digits.startswith("00"):
        digits = digits[2:]
    # Remove leading single zero (local format) and prepend country code 20
    elif digits.startswith("0"):
        digits = "20" + digits[1:]

    return digits