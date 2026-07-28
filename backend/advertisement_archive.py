"""Advertisement Archive Module.

This module provides the foundation for archiving advertisement records.
It is completely standalone and has NO dependencies on:

- Databases
- AI / Gemini
- Prompt Builder
- Conversation State Manager
- Supervisor Flow
- WhatsApp
- API
- Main

The AdvertisementArchive class is responsible for:
- Storing advertisement records in memory
- Providing methods to save and retrieve advertisement records
- Maintaining a history of advertisements for each campaign
"""

import sys
from pathlib import Path

# Add parent directory to path for imports when running as script
file_path = Path(__file__).resolve()
parent_dir = file_path.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from backend.advertisement_type_detector import AdvertisementType

@dataclass
class AdvertisementRecord:
    """A record representing an advertisement in the archive.

    Attributes:
        campaign_name: The name of the campaign this advertisement belongs to.
        supervisor_name: The name of the supervisor who created/approved the advertisement.
        phone_number: The phone number associated with the advertisement.
        original_announcement: The original announcement text before any modifications.
        final_announcement: The final announcement text after all modifications.
        advertisement_type: The type of advertisement (NEW, UPDATE, ADD, CANCEL, UNKNOWN).
        attachments: List of file paths or URLs for attachments.
        sent_at: The datetime when the advertisement was sent.
        approved_at: The datetime when the advertisement was approved (None if not approved).
        change_summary: A summary of changes made to the advertisement.
    """

    campaign_name: str
    supervisor_name: str
    phone_number: str
    original_announcement: str
    final_announcement: str
    advertisement_type: AdvertisementType
    attachments: list[str]
    sent_at: datetime
    approved_at: Optional[datetime]
    change_summary: str

class AdvertisementArchive:
    """Repository for storing and retrieving advertisement records.

    This class provides an in-memory storage for advertisement records.
    It maintains a list of all records and provides methods to:
    - Save new records
    - Retrieve the current advertisement for a campaign
    - Retrieve the full history of advertisements for a campaign

    Note: This implementation uses only in-memory storage. No persistence
    to database, filesystem, or any external storage is implemented.
    """

    def __init__(self) -> None:
        """Initialize the archive with an empty list of records."""
        self._records: list[AdvertisementRecord] = []

    def save(self, record: AdvertisementRecord) -> None:
        """Save an advertisement record to the archive.

        Args:
            record: The AdvertisementRecord to save.
        """
        if not isinstance(record, AdvertisementRecord):
            raise TypeError("record must be an instance of AdvertisementRecord")
        self._records.append(record)

    def get_current(self, campaign_name: str) -> AdvertisementRecord:
        """Retrieve the most recent advertisement record for a campaign.

        Args:
            campaign_name: The name of the campaign to retrieve the current advertisement for.

        Returns:
            The most recent AdvertisementRecord for the specified campaign.

        Raises:
            ValueError: If campaign_name is empty or no records exist for the campaign.
        """
        if not campaign_name:
            raise ValueError("campaign_name cannot be empty")

        matching_records = [
            record for record in self._records
            if record.campaign_name == campaign_name
        ]

        if not matching_records:
            raise ValueError("Campaign not found")

        return matching_records[-1]

    def get_history(self, campaign_name: str) -> list[AdvertisementRecord]:
        """Retrieve all advertisement records for a campaign.

        Args:
            campaign_name: The name of the campaign to retrieve history for.

        Returns:
            A list of all AdvertisementRecord instances for the specified campaign,
            ordered from oldest to newest. Returns empty list if no records exist.

        Raises:
            ValueError: If campaign_name is empty.
        """
        if not campaign_name:
            raise ValueError("campaign_name cannot be empty")

        return [
            record for record in self._records
            if record.campaign_name == campaign_name
        ]

if __name__ == "__main__":
    # Demo: Create one AdvertisementRecord instance and print it
    record = AdvertisementRecord(
        campaign_name="Test Campaign",
        supervisor_name="Test Supervisor",
        phone_number="+1234567890",
        original_announcement="Original text",
        final_announcement="Final text",
        advertisement_type=AdvertisementType.NEW,
        attachments=[],
        sent_at=datetime.now(),
        approved_at=None,
        change_summary="Test changes"
    )
    print(record)