"""Staged supervisor + campaign ownership import from Excel."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import select

from database import get_setting
from db.base import get_session
from db.models import Campaign
from db.platform_models import ImportBatch, Supervisor
from db.repositories.platform_repository import SupervisorRepository
from phone_utils import normalize_phone

REQUIRED_COLUMNS = {"campaign name", "supervisor name", "phone number"}


def _headers(row) -> dict[str, int]:
    normalised = {}
    for idx, cell in enumerate(row):
        if cell is None:
            continue
        key = str(cell).strip().lower()
        if key:
            normalised[key] = idx
    missing = REQUIRED_COLUMNS - set(normalised.keys())
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    return {col: normalised[col] for col in REQUIRED_COLUMNS}


def preview_supervisor_import() -> dict[str, Any]:
    path = Path(get_setting("campaign_file", ""))
    if not path.exists():
        raise FileNotFoundError("Campaign/supervisor file not configured.")
    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel file is empty.")
    col = _headers([str(c or "") for c in rows[0]])
    preview = []
    errors = []
    for i, row in enumerate(rows[1:], start=2):
        try:
            campaign_name = str(row[col["campaign name"]] or "").strip()
            supervisor_name = str(row[col["supervisor name"]] or "").strip()
            phone_raw = str(row[col["phone number"]] or "").strip()
            phone = normalize_phone(phone_raw)
            if not (campaign_name and supervisor_name and phone):
                raise ValueError("missing required values")
            preview.append(
                {
                    "row": i,
                    "campaign_name": campaign_name,
                    "supervisor_name": supervisor_name,
                    "phone_number": phone,
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"row": i, "error": str(exc)})
    return {"ok": True, "preview": preview, "errors": errors}


def activate_supervisor_import() -> dict[str, Any]:
    preview = preview_supervisor_import()
    activated = 0
    with get_session() as session:
        batch = ImportBatch(
            import_type="supervisor_campaign",
            status="activating",
            row_count=len(preview["preview"]),
            error_count=len(preview["errors"]),
        )
        session.add(batch)
        session.flush()
        sup_repo = SupervisorRepository(session)
        for row in preview["preview"]:
            phone = row["phone_number"]
            supervisor = sup_repo.get_by_phone(phone)
            if supervisor is None:
                supervisor = sup_repo.create(
                    {
                        "phone_number": phone,
                        "display_name": row["supervisor_name"],
                        "is_active": True,
                        "activated_at": datetime.now(timezone.utc),
                    }
                )
            else:
                supervisor.display_name = row["supervisor_name"]
                supervisor.is_active = True
                supervisor.activated_at = datetime.now(timezone.utc)
            existing = session.scalar(
                select(Campaign).where(Campaign.campaign_name == row["campaign_name"])
            )
            if existing is None:
                session.add(
                    Campaign(
                        campaign_name=row["campaign_name"],
                        owner_supervisor_id=supervisor.id,
                        status="active",
                        description="",
                    )
                )
            else:
                existing.owner_supervisor_id = supervisor.id
            activated += 1
        batch.status = "active"
        batch.result = {"activated": activated}
    return {"ok": True, "activated": activated, "errors": preview["errors"]}
