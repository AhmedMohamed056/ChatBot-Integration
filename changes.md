# Task 11 — Reports Backend

## Summary

Implemented the **Reports Backend** — an internal, read-only aggregation
API layer that collects data already stored in the database and returns it
for the Admin Dashboard. No AI, no analytics, no charts, no exports. The
service (`reports_service.py`) is the only place that aggregates data; the
FastAPI endpoints are thin wrappers.

### Key design decisions

- **Aggregation service only** — `reports_service.py` is responsible only
  for aggregating data. Endpoints contain no business logic.
- **Reuse existing repositories** — every read goes through an existing
  repository (`CampaignRepository`, `CampaignVisitorRepository`,
  `CalendarEventRepository`, `VisitorQuestionRepository`) or an existing
  helper in `database.py` (`get_setting`, `get_uploaded_file_record`).
- **No new tables** — no import-history table; import timestamps are read
  from the existing `uploaded_files` information keyed by the
  `campaign_file` / `calendar_file` settings.
- **Never raises** — when no data exists, returns `0` or `[]`. Every public
  method wraps its body in `try/except` and returns safe defaults.
- **No duplicated SQL** — the only new query is a single grouped count
  added to `CampaignVisitorRepository.count_by_campaign()`; everything
  else reuses existing repository methods.

---

## New Files

| File | Purpose |
|---|---|
| `backend/reports_service.py` | Aggregation service: `get_summary_report()`, `get_campaign_report()`, `get_questions_report()`, `get_calendar_report()`, `get_imports_report()` |

## Modified Files

| File | Change |
|---|---|
| `backend/db/repositories/campaign_visitor_repository.py` | Added `count_by_campaign()` — single grouped count query (visitor count per campaign) |
| `backend/db/repositories/visitor_question_repository.py` | Added `list_latest_questions(limit)` — returns latest questions ordered by `message_timestamp` desc |
| `backend/main.py` | Imported `reports_service`; added 5 thin report endpoints |

---

## New API Endpoints

| Method | Path | Response |
|---|---|---|
| `GET` | `/admin/reports/summary` | `{campaigns:{total_campaigns,total_visitors}, calendar:{total_events}, questions:{total_questions}, prayers:{today_count}}` |
| `GET` | `/admin/reports/campaigns` | `[{campaign_name, visitor_count}, ...]` |
| `GET` | `/admin/reports/questions` | Latest 50 questions: `{visitor_name, campaign_name, phone_number, question, detected_language, message_timestamp}` |
| `GET` | `/admin/reports/calendar` | `{total_events}` |
| `GET` | `/admin/reports/imports` | `{campaign_import, calendar_import}` (ISO timestamps or `""`) |

---

## Repositories Reused

- `CampaignRepository` — `count()` for total campaigns
- `CampaignVisitorRepository` — `count()` for total visitors; new
  `count_by_campaign()` for the campaign report
- `CalendarEventRepository` — `count()` for total calendar events
- `VisitorQuestionRepository` — `count()` for total questions; new
  `list_latest_questions()` for the questions report
- `database.get_setting()` + `database.get_uploaded_file_record()` — for
  the imports report (no new import-history table)

---

## Validation Implemented

- All public service methods wrap their bodies in `try/except` and return
  `0` / `[]` / `""` on any failure — endpoints never throw or crash.
- Verified with an empty database: summary returns `0` counts, campaign
  report returns `[]`, questions report returns `[]` (or the stored
  questions newest-first), calendar report returns `{"total_events": 0}`,
  imports report returns `{"campaign_import": "", "calendar_import": ""}`.

---

## Confirmation — No Restricted Functionality

The Reports Backend contains **NO**:
- Analytics / trending / "most common" / "most active" computations
- AI / Gemini / LLM calls
- Dashboard UI / charts / graphs / widgets
- Excel / PDF / CSV export
- Search / filters / pagination options / sorting options
- New database tables
- Duplicated SQL queries

Reports Backend is an **internal API layer only**. The Admin Dashboard UI
will consume these endpoints later.

---

# Task 7 — Calendar Engine

## Summary

Implemented the **Calendar Engine** — an independent service that reads the
administrator-uploaded Calendar Excel file (`calendar_file` setting),
validates it, converts every row into a Calendar Event, stores them in a new
`calendar_events` table, and exposes search APIs. The engine is fully
decoupled from FastAPI; the API endpoints are thin wrappers that only call
the service.

### Key design decisions

- **No hardcoded paths** — the file path is read from the `calendar_file`
  system setting (uploaded via Settings).
- **Flexible parser** — column matching is case-insensitive and
  whitespace-trimmed; the four required columns (`Date`, `Day`, `Event`,
  `Time`) are detected by name, and any extra columns are safely ignored.
- **Independent table** — `calendar_events` is separate from the
  `calendar_days` prayer-times table; the engine does not touch prayer
  times, Hijri dates, or any other concern.
- **Replace-on-import** — every import fully replaces the table so it
  always mirrors the latest uploaded file.
- **Never crashes** — invalid/empty rows are skipped; search APIs return
  empty lists on any error.

---

## New Files

| File | Purpose |
|---|---|
| `backend/calendar_engine.py` | Calendar Engine service: `load_calendar()`, `search_by_date()`, `search_by_day()`, `list_all_events()` + typed errors |
| `backend/db/repositories/calendar_event_repository.py` | `CalendarEventRepository` (CRUD + date/day lookups + bulk replace) |
| `backend/test_calendar_engine.py` | Example tests (load, search, case-insensitive headers, extra columns, skip invalid rows, missing columns/file/config rejected, never-crash search) |

## Modified Files

| File | Change |
|---|---|
| `backend/db/models.py` | Added `CalendarEvent` model (`calendar_events` table) |
| `backend/db/repositories/__init__.py` | Exported `CalendarEventRepository` |
| `backend/db/__init__.py` | Exported `CalendarEvent` model + `CalendarEventRepository` |
| `backend/db/init_db.py` | Imported `CalendarEvent` so it registers with `Base.metadata` |
| `backend/main.py` | Imported the engine; added 4 calendar endpoints |

---

## New Database Object

### Table `calendar_events` (in `campaigns.db`)
`id`, `event_date`, `day_name`, `event_title`, `event_time`, `created_at`, `updated_at`
+ indexes on `event_date` and `day_name`.

---

## New Service

`backend/calendar_engine.py` — public functions:
- `load_calendar()` → `{"ok": True, "events": <int>, "skipped": <int>}`
- `search_by_date(date)` → list of event dicts
- `search_by_day(day)` → list of event dicts
- `list_all_events()` → list of event dicts

Typed errors: `CalendarFileNotConfiguredError`,
`CalendarFileNotFoundError`, `CalendarFileUnsupportedError`,
`CalendarMissingColumnsError`.

---

## New API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/admin/calendar/import` | Load the uploaded calendar; returns `{"ok": true, "events": <int>}` |
| `GET` | `/admin/calendar/date/{date}` | Search events by date (case-insensitive) |
| `GET` | `/admin/calendar/day/{day}` | Search events by day name (case-insensitive) |
| `GET` | `/admin/calendar/events` | List all stored events |

---

## Validation

- Rejects missing file (404), unsupported extension (400), missing required
  columns (400), and unconfigured calendar (400).
- Skips empty rows and rows without an event title.
- Search APIs never raise — they return `[]` on any failure.

---

## Confirmation — No Restricted Logic

The Calendar Engine contains **NO**:
- Prayer Time logic
- AI / Gemini / LLM calls
- Context Builder logic
- WhatsApp logic
- Relative Date logic (no duplication)
- Reports / Campaign Updates / Visitor Questions logic

(Verified by regex search — the only mentions are in the module docstring
explicitly stating these are NOT implemented.)

---

## Verification

`cd backend && python test_calendar_engine.py` — all tests pass ✅

---

# Campaigns Page — Read-Only Implementation

## Summary

Implemented a **read-only Campaigns page** in the admin dashboard. The administrator cannot create, edit, or delete campaigns manually — campaign information is managed automatically by the AI from WhatsApp messages. The only allowed write operation is deleting **individual campaign updates** from the details panel.

---

## Files Modified

### 1. `backend/database.py`
- **Migration**: Added `supervisor_name` column to the `campaigns` table (safe `ALTER TABLE` wrapped in try/except so it runs only once).
- **New function** `list_campaigns_with_stats()`: Returns all campaigns enriched with `supervisor_name`, `last_update` (max of `campaign_messages.created_at`), and `total_updates` (count of messages). Ordered by most recent update.
- **New function** `get_campaign_messages(campaign_id)`: Returns all update messages for a campaign, newest first.
- **New function** `delete_campaign_message(message_id)`: Deletes a single campaign update message. Returns `True` if a row was removed.

### 2. `backend/main.py`
- **Imports**: Added `delete_campaign_message`, `get_campaign_messages`, `list_campaigns_with_stats` to the database import block.
- **Updated** `GET /admin/campaigns`: Now returns campaigns with stats (supervisor name, last update, total updates) via `list_campaigns_with_stats()`.
- **New endpoint** `GET /admin/campaigns/{campaign_id}/messages`: Returns all update messages for a single campaign (powers the details panel).
- **New endpoint** `DELETE /admin/campaigns/messages/{message_id}`: Deletes a single campaign update message — the **only** write operation allowed on campaign data from the admin UI.
- The existing `POST`, `PUT`, and `DELETE /admin/campaigns` endpoints remain in the backend (used by the WhatsApp bot / AI pipeline), but are **no longer exposed in the admin UI**.

### 3. `backend/admin_dashboard.html`
- **CSS**: Added styles for the read-only banner, status badges, clickable campaign rows, the slide-in details panel overlay, update cards, meta chips, and update sections.
- **New component** `StatusBadge`: Renders active/inactive status as a colored pill.
- **New component** `CampaignDetailsPanel`: Slide-in panel showing:
  - Campaign name, supervisor name, WhatsApp number
  - A read-only banner explaining campaigns are AI-managed
  - **Latest Updates** list, each update card showing:
    - Extracted Information
    - Original Message
    - Date (event date or created date)
    - Meta chips (event date, expiry, created date, inactive flag)
    - **Delete Update** button (only allowed write operation)
- **Rewrote** `CampaignsView`: Now a read-only table with columns:
  - Campaign Name
  - Supervisor Name
  - WhatsApp Number
  - Last Update
  - Total Updates
  - Status
  - Clicking a row opens the `CampaignDetailsPanel`.
  - **No Add / Edit / Delete campaign buttons.**

---

## Components Added

| Component | Location | Purpose |
|---|---|---|
| `StatusBadge` | `admin_dashboard.html` | Renders campaign status as a colored badge |
| `CampaignDetailsPanel` | `admin_dashboard.html` | Slide-in panel with update details + per-update delete |

---

## Endpoints Added

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/campaigns/{campaign_id}/messages` | Fetch all updates for a campaign |
| `DELETE` | `/admin/campaigns/messages/{message_id}` | Delete a single campaign update |

---

## Remaining TODO Items

- **Supervisor name population**: The `supervisor_name` column is now part of the schema and displayed, but it is not yet populated automatically. A future task should update the WhatsApp bot / campaign ingestion pipeline to set `supervisor_name` when a campaign is created or updated (e.g., from the WhatsApp contact name or a campaign list file).
- **Backend write endpoints cleanup (optional)**: The `POST/PUT/DELETE /admin/campaigns` endpoints still exist in `main.py` for the AI pipeline. If desired, they can be restricted to internal/service calls only (e.g., via a separate API key or by moving them out of the `/admin` namespace) so they cannot be used from the admin UI even by direct API calls.
- **Empty-state testing**: The page was verified with zero campaigns. End-to-end testing with real campaign data (created via the WhatsApp bot) should be performed once the bot is running.

---

# Task 1 — Campaign Database Layer

## Summary

Designed and implemented a **new, isolated database layer** (`backend/db/`) that serves as the single source of truth for all campaign information. The layer uses SQLAlchemy 2.0 + SQLite and is completely decoupled from the legacy `app.db` / `database.py` module — no existing endpoints or chatbot behavior were modified.

### Key design decisions

- **Separate database file** (`campaigns.db`) so the legacy `app.db` is untouched.
- **No separate prayer-times table** — prayer times are columns on `calendar_days`, as required.
- **Append-only audit log** — `campaign_updates` never overwrites; every WhatsApp modification is a new row.
- **Foreign keys enforced** via `PRAGMA foreign_keys=ON` on every connection.
- **Schema-version table** for future migrations.
- **Unique constraint** on `campaigns.campaign_name` (no duplicates).
- **Indexes** on all frequently queried columns (status, type, dates, phone_number, etc.).

---

## New Files

| File | Purpose |
|---|---|
| `backend/db/__init__.py` | Public API: `init_db`, `get_session`, models, repositories |
| `backend/db/base.py` | Engine, `SessionLocal`, `Base`, `get_session()` context manager, `init_engine()` |
| `backend/db/models.py` | 5 SQLAlchemy ORM models with relationships, indexes, constraints |
| `backend/db/init_db.py` | `init_db()`, `drop_all()`, schema-version tracking, migration runner |
| `backend/db/test_db.py` | Smoke test covering all repositories + FK enforcement |
| `backend/db/repositories/__init__.py` | Repository package exports |
| `backend/db/repositories/base.py` | `BaseRepository[T]` generic CRUD |
| `backend/db/repositories/campaign_repository.py` | `CampaignRepository` |
| `backend/db/repositories/campaign_update_repository.py` | `CampaignUpdateRepository` |
| `backend/db/repositories/calendar_repository.py` | `CalendarRepository` |
| `backend/db/repositories/uploaded_file_repository.py` | `UploadedFileRepository` |
| `backend/db/repositories/visitor_question_repository.py` | `VisitorQuestionRepository` |

## Modified Files

| File | Change |
|---|---|
| `backend/requirements.txt` | Added `sqlalchemy>=2.0` |
| `backend/.gitignore` | Added `*.db` and `*.db-journal` |

---

## Tables

### `campaigns`
`id`, `campaign_name` (unique), `campaign_type`, `start_date`, `end_date`, `status`, `description`, `notes`, `created_at`, `updated_at`

### `campaign_updates` (append-only)
`id`, `campaign_id` (FK → campaigns, CASCADE), `update_type`, `changed_field`, `old_value`, `new_value`, `source`, `message_text`, `updated_by`, `created_at`

### `calendar_days`
`id`, `gregorian_date` (unique), `hijri_date`, `weekday`, `fajr`, `dhuhr`, `asr`, `maghrib`, `isha`, `is_ramadan`, `ramadan_day`, `is_eid`, `islamic_event`, `public_event`, `notes`

### `uploaded_files`
`id`, `filename`, `file_type`, `uploaded_at`, `imported_rows`, `checksum`, `status`

### `visitor_questions`
`id`, `phone_number`, `question`, `detected_campaign`, `ai_answer`, `answered`, `created_at`, `campaign_id` (FK → campaigns, SET NULL)

---

## Usage

```python
from db import init_db, get_session, CampaignRepository

init_db()  # idempotent – safe to call on startup

with get_session() as session:
    repo = CampaignRepository(session)
    campaign = repo.create({"campaign_name": "Ramadan 1447", ...})
```

## Verification

`python -m db.test_db` — all tests pass ✅ (campaigns, updates, calendar, files, questions, FK enforcement).
