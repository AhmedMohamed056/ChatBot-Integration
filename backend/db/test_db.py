"""Smoke test for the campaign database layer.

Run with:  python -m db.test_db
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timezone

# Ensure the backend dir is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (
    Campaign,
    CampaignRepository,
    CampaignUpdate,
    CampaignUpdateRepository,
    CalendarDay,
    CalendarRepository,
    UploadedFile,
    UploadedFileRepository,
    VisitorQuestion,
    VisitorQuestionRepository,
    drop_all,
    get_schema_version,
    init_db,
    init_engine,
    get_session,
)


def main() -> None:
    # Use a temporary database for testing
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    print(f"Using temporary database: {tmp.name}")
    init_engine(tmp.name)

    print("\n=== Initialising database ===")
    init_db()
    print(f"Schema version: {get_schema_version()}")

    # ------------------------------------------------------------------
    # Campaign tests
    # ------------------------------------------------------------------
    print("\n=== Campaign tests ===")
    with get_session() as session:
        repo = CampaignRepository(session)

        # Create
        c1 = repo.create({
            "campaign_name": "Ramadan 1447",
            "campaign_type": "ramadan",
            "start_date": date(2026, 2, 18),
            "end_date": date(2026, 3, 19),
            "status": "active",
            "description": "Ramadan campaign 1447 AH",
        })
        print(f"Created campaign: {c1}")

        # Duplicate name should fail
        try:
            repo.create({"campaign_name": "Ramadan 1447"})
            print("ERROR: duplicate name should have failed!")
        except ValueError as e:
            print(f"Duplicate name correctly rejected: {e}")

        # Lookup
        found = repo.get_by_name("Ramadan 1447")
        assert found is not None
        print(f"Found by name: {found}")

        # Update + audit log
        updated = repo.update_campaign(c1.id, {"status": "paused"})
        print(f"Updated status: {updated.status}")
        repo.add_update(c1.id, {
            "update_type": "status_change",
            "changed_field": "status",
            "old_value": "active",
            "new_value": "paused",
            "source": "whatsapp",
            "message_text": "Please pause the Ramadan campaign",
            "updated_by": "+1234567890",
        })

        history = repo.get_update_history(c1.id)
        print(f"Update history count: {len(history)}")
        assert len(history) == 1

    # ------------------------------------------------------------------
    # CampaignUpdate tests
    # ------------------------------------------------------------------
    print("\n=== CampaignUpdate tests ===")
    with get_session() as session:
        repo = CampaignUpdateRepository(session)
        updates = repo.list_by_campaign(1)
        print(f"Updates for campaign 1: {len(updates)}")
        assert len(updates) == 1

        whatsapp_updates = repo.list_by_source("whatsapp")
        print(f"WhatsApp updates: {len(whatsapp_updates)}")
        assert len(whatsapp_updates) == 1

    # ------------------------------------------------------------------
    # CalendarDay tests
    # ------------------------------------------------------------------
    print("\n=== CalendarDay tests ===")
    with get_session() as session:
        repo = CalendarRepository(session)

        # Create a few days
        repo.bulk_upsert([
            {
                "gregorian_date": date(2026, 2, 18),
                "hijri_date": "1447-08-01",
                "weekday": "Wednesday",
                "fajr": "05:12",
                "dhuhr": "12:30",
                "asr": "15:45",
                "maghrib": "18:01",
                "isha": "19:20",
                "is_ramadan": False,
            },
            {
                "gregorian_date": date(2026, 2, 19),
                "hijri_date": "1447-08-02",
                "weekday": "Thursday",
                "fajr": "05:11",
                "dhuhr": "12:31",
                "asr": "15:46",
                "maghrib": "18:02",
                "isha": "19:21",
                "is_ramadan": False,
            },
        ])
        print("Created 2 calendar days")

        day = repo.get_by_date(date(2026, 2, 18))
        print(f"Got day: {day}")
        assert day is not None
        assert day.fajr == "05:12"

        rng = repo.list_in_range(date(2026, 2, 18), date(2026, 2, 19))
        print(f"Days in range: {len(rng)}")
        assert len(rng) == 2

        # Upsert (update existing)
        repo.upsert({
            "gregorian_date": date(2026, 2, 18),
            "fajr": "05:10",
        })
        day = repo.get_by_date(date(2026, 2, 18))
        print(f"Updated fajr: {day.fajr}")
        assert day.fajr == "05:10"

    # ------------------------------------------------------------------
    # UploadedFile tests
    # ------------------------------------------------------------------
    print("\n=== UploadedFile tests ===")
    with get_session() as session:
        repo = UploadedFileRepository(session)

        f1 = repo.create({
            "filename": "campaigns.xlsx",
            "file_type": "campaign_excel",
            "imported_rows": 25,
            "checksum": "abc123def456",
            "status": "imported",
        })
        print(f"Created file record: {f1}")

        found = repo.get_by_checksum("abc123def456")
        assert found is not None
        print(f"Found by checksum: {found}")

        # Upsert
        repo.upsert({
            "filename": "campaigns.xlsx",
            "file_type": "campaign_excel",
            "imported_rows": 30,
            "status": "imported",
        })
        files = repo.list_by_type("campaign_excel")
        print(f"Files after upsert: {len(files)}")
        assert len(files) == 1  # upsert, not insert
        assert files[0].imported_rows == 30

    # ------------------------------------------------------------------
    # VisitorQuestion tests
    # ------------------------------------------------------------------
    print("\n=== VisitorQuestion tests ===")
    with get_session() as session:
        repo = VisitorQuestionRepository(session)

        q1 = repo.ask(
            question="What time is Maghrib prayer today?",
            phone_number="+1234567890",
            detected_campaign="Ramadan 1447",
            campaign_id=1,
        )
        print(f"Created question: {q1}")
        assert q1.id is not None

        unanswered = repo.list_unanswered()
        print(f"Unanswered: {len(unanswered)}")
        assert len(unanswered) == 1

        repo.mark_answered(q1.id, ai_answer="Maghrib is at 18:01 today.")
        answered = repo.list_answered()
        print(f"Answered: {len(answered)}")
        assert len(answered) == 1
        assert answered[0].ai_answer == "Maghrib is at 18:01 today."

    # ------------------------------------------------------------------
    # Foreign key test
    # ------------------------------------------------------------------
    print("\n=== Foreign key test ===")
    with get_session() as session:
        from sqlalchemy import text
        result = session.execute(text("PRAGMA foreign_keys")).scalar()
        print(f"foreign_keys PRAGMA = {result}")
        assert result == 1

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    print("\n=== Cleanup ===")
    drop_all()
    # Dispose the engine so Windows releases the file handle
    from db import base as _base
    _base.engine.dispose()
    try:
        os.unlink(tmp.name)
        print("Temporary database removed.")
    except PermissionError:
        print(f"Temporary database left at {tmp.name} (file locked).")

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    main()