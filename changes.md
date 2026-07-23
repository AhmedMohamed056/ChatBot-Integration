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