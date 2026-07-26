"""WhatsApp Campaign Detection service.

Responsibilities (and **only** these):
- Normalise an incoming WhatsApp sender phone number.
- Search the ``campaign_visitors`` table for that number.
- Return the visitor object (``campaign_name``, ``visitor_name``,
  ``phone_number``) or ``None`` if not found.

This service intentionally contains **no business logic**.  It does not
perform AI, campaign updates, calendar lookups, replies, or any other
future-task functionality.
"""

from __future__ import annotations

from typing import Optional

from db.base import get_session
from db.repositories.campaign_visitor_repository import CampaignVisitorRepository
from phone_utils import normalize_phone


def detect_visitor(raw_phone: str) -> Optional[dict[str, str]]:
    """Detect whether a phone number belongs to a known campaign visitor.

    Parameters
    ----------
    raw_phone:
        The sender phone number exactly as received from WhatsApp
        (e.g. ``"+201012345678"``, ``"00201012345678"``, ``"01012345678"``).

    Returns
    -------
    dict or None
        A dict with ``campaign_name``, ``visitor_name`` and ``phone_number``
        if a matching visitor exists, otherwise ``None``.
    """
    phone_number = normalize_phone(raw_phone)
    if not phone_number:
        return None

    with get_session() as session:
        repo = CampaignVisitorRepository(session)
        return repo.find_by_phone(phone_number)