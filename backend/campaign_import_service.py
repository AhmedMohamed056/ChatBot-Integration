"""Campaign Excel import service.

Reads the Campaign List Excel file uploaded from the Settings page and
imports all visitors into the ``campaign_visitors`` table.

Responsibilities:
- Locate the uploaded Excel file path from system settings.
- Parse the Excel file (supports .xlsx and .xls).
- Validate that the required columns exist.
- Normalise phone numbers to a canonical international format.
- Upsert visitors (phone number is unique; existing rows are updated).
- Return a summary of imported / updated / skipped rows.

This service does **not** implement WhatsApp detection, AI extraction,
calendar integration, reports, or any other future-task functionality.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from database import get_setting
from db.base import get_session
from db.repositories.campaign_visitor_repository import CampaignVisitorRepository
from phone_utils import normalize_phone


# Required columns (case-insensitive, whitespace-trimmed)
REQUIRED_COLUMNS = {
    "campaign name",
    "visitor name",
    "phone number",
}


def _find_required_headers(header_row: list[str]) -> dict[str, int]:
    """Map normalised required column names to their index in the header row.

    Returns a dict like {"campaign name": 0, "visitor name": 1, "phone number": 2}.
    Raises ``ValueError`` if any required column is missing.
    """
    normalised = {}
    for idx, cell in enumerate(header_row):
        if cell is None:
            continue
        col = str(cell).strip().lower()
        if col:
            normalised[col] = idx

    missing = REQUIRED_COLUMNS - set(normalised.keys())
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    return {col: normalised[col] for col in REQUIRED_COLUMNS}


def import_campaign_visitors() -> dict[str, Any]:
    """Import all visitors from the uploaded Campaign List Excel file.

    Returns a summary dict::

        {
            "ok": True,
            "total_rows": 250,
            "imported": 240,
            "updated": 10,
            "skipped": 0
        }
    """
    print("Campaign import started...")

    # 1. Read campaign file path from settings
    file_path_str = get_setting("campaign_file", "")
    if not file_path_str:
        raise ValueError("Campaign file not uploaded. Please upload it in Settings first.")

    file_path = Path(file_path_str)
    if not file_path.exists():
        raise FileNotFoundError(f"Campaign Excel file not found at: {file_path}")

    print(f"Reading Excel: {file_path.name}")

    # 2. Open and parse Excel
    wb = load_workbook(filename=str(file_path), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel file is empty.")

    # 3. Validate required columns
    header_row = [str(cell) if cell is not None else "" for cell in rows[0]]
    col_map = _find_required_headers(header_row)

    print("Normalizing phones...")

    total_rows = 0
    imported = 0
    updated = 0
    skipped = 0

    # 4. Process data rows
    data_rows = rows[1:]
    if data_rows:
        print(f"Importing rows... ({len(data_rows)} rows to process)")

    with get_session() as session:
        repo = CampaignVisitorRepository(session)

        for row in data_rows:
            total_rows += 1
            try:
                campaign_name = str(row[col_map["campaign name"]] or "").strip()
                visitor_name = str(row[col_map["visitor name"]] or "").strip()
                phone_raw = str(row[col_map["phone number"]] or "").strip()

                # 5. Validation – skip invalid rows
                if not campaign_name or not visitor_name or not phone_raw:
                    skipped += 1
                    continue

                phone_number = normalize_phone(phone_raw)
                if not phone_number:
                    skipped += 1
                    continue

                # 6. Upsert (insert or update by phone number)
                _, created = repo.upsert(
                    campaign_name,
                    visitor_name,
                    phone_number,
                )
                if created:
                    imported += 1
                else:
                    updated += 1
            except Exception as row_err:
                # Skip invalid rows without crashing the whole import
                print(f"  ⚠️ Skipped row {total_rows}: {row_err}")
                skipped += 1
                continue

    print("Campaign import completed.")
    print(f"Imported: {imported}")
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")

    return {
        "ok": True,
        "total_rows": total_rows,
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
    }