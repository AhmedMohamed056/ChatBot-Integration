# Task 2 — Admin Settings System

## Summary

Implemented a complete **Settings System** for the Admin Panel. The Settings page is the central control center where the administrator configures the chatbot: general info, AI, campaign/calendar file uploads, prompt templates, WhatsApp settings, and security. All secrets are masked in API responses. File uploads are validated (extension + size) and registered in the existing `uploaded_files` table. No Excel/calendar parsing, WhatsApp logic, or AI processing is implemented in this task.

---

## Files Modified

### 1. `backend/main.py`
- **Endpoint path fixes**: Renamed `POST /admin/settings/calendar` → `POST /admin/settings/upload/calendar` and `POST /admin/settings/campaign-list` → `POST /admin/settings/upload/campaign` to match the required API spec.
- **Settings endpoints** (already present, verified):
  - `GET /admin/settings` — returns all settings with secrets masked and file paths converted to filenames.
  - `PUT /admin/settings` — updates general, AI, WhatsApp, and security settings. Ignores masked API-key placeholders so secrets are not overwritten accidentally.
  - `GET /admin/settings/prompts` — returns all prompt templates.
  - `PUT /admin/settings/prompts` — updates system/campaign/visitor/update prompts.
  - `POST /admin/settings/change-password` — verifies current password (DB or env), enforces min length 6, stores new hash.
  - `POST /admin/settings/upload/calendar` — validates extension (xlsx/xls/csv/json), saves to `calendar_files/`, enforces 10 MB max, registers in `uploaded_files`, stores path in `settings.calendar_file`.
  - `POST /admin/settings/upload/campaign` — validates extension (xlsx/xls/csv), saves to `calendar_files/`, enforces 10 MB max, registers in `uploaded_files`, stores path in `settings.campaign_list_file`.
- **Validation**: file extension, file size (10 MB), missing required values, duplicate uploads (upsert replaces old record with same filename).
- **Secrets**: `gemini_api_key` is stored but returned masked (`••••••••`) via `mask_secret()`.

### 2. `backend/admin_dashboard.html`
- **Updated upload API calls** to use the new `/admin/settings/upload/calendar` and `/admin/settings/upload/campaign` paths.
- **SettingsView** (already present, verified) renders 7 grouped cards:
  1. General Settings (organization, mosque, language, timezone, country, city)
  2. AI Settings (Gemini API key as password, model, temperature, max tokens)
  3. Campaign Files (drag-drop upload, current file + upload date + size)
  4. Calendar File (drag-drop upload, current file + upload date + size)
  5. Prompt Configuration (system/campaign/visitor/update prompts)
  6. WhatsApp Settings (bot number, welcome message, fallback message)
  7. Security (change password, session timeout)
- **UI features**: loading indicators, success/error messages, Save + Reset buttons, file validation (extension + size) on the client.

### 3. `backend/database.py`
- Already contains the required tables and functions (verified):
  - `system_settings` (key/value settings)
  - `prompt_templates` (named prompt templates)
  - `admin_users` (password change)
  - `uploaded_files` (reused for campaign/calendar files)
  - Functions: `get_all_settings`, `set_setting`, `get_all_prompts`, `set_prompt`, `get_admin_user`, `change_admin_password`, `upsert_uploaded_file`, `list_uploaded_files_db`, `delete_uploaded_file_record`, `get_uploaded_file_by_filename`.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/settings` | Return all settings (secrets masked) |
| `PUT` | `/admin/settings` | Update general/AI/WhatsApp/security settings |
| `GET` | `/admin/settings/prompts` | Return all prompt templates |
| `PUT` | `/admin/settings/prompts` | Update prompt templates |
| `POST` | `/admin/settings/upload/campaign` | Upload + register campaign Excel/CSV |
| `POST` | `/admin/settings/upload/calendar` | Upload + register calendar file |
| `POST` | `/admin/settings/change-password` | Change admin password |

---

## Validation

- **Missing API key**: handled — key is optional; masked placeholder is never saved.
- **Wrong file type**: rejected with 400 (calendar: xlsx/xls/csv/json; campaign: xlsx/xls/csv).
- **Large files**: rejected with 413 (max 10 MB).
- **Duplicate uploads**: upsert replaces the old `uploaded_files` record with the same filename.
- **Missing required values**: password min length 6 enforced server-side; client-side validation for file size/type.

---

## What was NOT implemented (per task scope)

- Excel parsing, calendar parsing, campaign import, WhatsApp processing, AI extraction, reports, relative dates, calendar engine, prayer engine.

---

## Verification

- Integration test confirmed: all tables exist, settings/prompts round-trip, password change, uploaded_files upsert/replace/delete all work.
- Route listing confirmed all 7 settings endpoints are registered with the correct paths.

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
