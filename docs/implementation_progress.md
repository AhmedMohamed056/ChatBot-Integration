# Implementation progress

Last updated: 2026-07-29

This log tracks execution of the production roadmap (not a redesign). Status reflects verified behavior where noted.

## Phase A — Assistant separation and WhatsApp routing

### Completed

- **Website chatbot decoupled from campaign management**: `/chat` no longer injects `build_active_campaign_context()`; visitors get datetime + RAG only (`backend/main.py`).
- **WhatsApp group policy**: groups use visitor/RAG flow for knowledge; campaign mutation intents are refused in groups; supervisors in groups can ask knowledge questions (`backend/services/message_orchestrator.py`).
- **Private non-supervisor policy**: unregistered phones get a polite rejection with no conversation persistence (`backend/services/message_orchestrator.py`).
- **Supervisor private chat**: authorized supervisors use `CampaignLifecycleService` with PostgreSQL-backed state (`backend/services/conversation_service.py`, `backend/services/campaign_lifecycle_service.py`).
- **Confirmation tokens**: OK / Yes / Approve / Confirm / Arabic equivalents accepted in review state (`backend/services/intent_router.py`).

### Files modified

- `backend/main.py`
- `backend/services/message_orchestrator.py`
- `backend/services/intent_router.py`
- `backend/services/campaign_lifecycle_service.py`
- `backend/services/supervisor_context_service.py` (new)

### Tests executed

```text
python -m unittest tests.test_platform_routing tests.test_e2e_supervisor_flow tests.test_phase0_contracts tests.test_phase1_schema -q
```

Result: **OK** (11 tests in full suite run earlier).

---

## Phase B — Admin authentication and PostgreSQL dashboard reads

### Completed

- **Admin login** uses `admin_users` + `admin_sessions` (PBKDF2 password hashes), seeded from `ADMIN_USERNAME` / `ADMIN_PASSWORD` on first startup when table is empty.
- **Distinct login errors** via redirect query params: `invalid_username`, `invalid_password`.
- **Password change** updates PostgreSQL hash for the active session user.
- **Campaign list / messages / stats** read from SQLAlchemy platform DB (`backend/services/platform_admin_service.py`).
- **Admin delete campaign** removes PostgreSQL row (cascade), writes audit event, removes Chroma embeddings for that campaign id.
- **Campaign Excel import** (`POST /admin/campaign/import`) activates supervisor/ownership import and attempts visitor import when columns allow.
- **Audit API**: `GET /admin/audit`.

### Files modified

- `backend/services/admin_auth_service.py` (new)
- `backend/services/platform_admin_service.py` (new)
- `backend/main.py`

### Database

- Uses existing Phase 1 tables: `admin_users`, `admin_sessions`, `audit_events`, `campaigns`, `campaign_versions`, `campaign_updates`.

### Known issues

- **Settings / uploaded file metadata** still partially stored in legacy `app.db` (`backend/database.py`) while campaigns/supervisors use `campaigns.db` / `DATABASE_URL`. Full PostgreSQL unification is remaining work.
- **Admin dashboard UI** does not yet include a dedicated Audit Log page (API exists).

---

## Phase C — Campaign lifecycle, versions, RAG worker

### Completed

- Draft → missing fields → review → explicit confirmation → commit with `CampaignVersion`, `CampaignUpdate`, outbox event.
- Supervisor greeting includes name, campaign, id, version, conversation state.
- Ownership enforced on commit/delete paths.
- Supervisor-initiated delete sets campaign `status=deleted` and enqueues `campaign.deleted`.
- **Incremental RAG hook**: `backend/services/rag_campaign_indexer.py` replaces embeddings per `campaign_id`; `backend/worker.py` processes outbox (also invoked best-effort after commit).

### Files modified

- `backend/services/campaign_lifecycle_service.py`
- `backend/services/rag_campaign_indexer.py` (new)
- `backend/worker.py`

### Tests executed

- `tests/test_e2e_supervisor_flow.py` — greeting, update, confirm, version persisted.

### Known issues

- **Chroma indexing in CI/dev** requires LangChain/torch stack installed (same as main app). Worker logs and skips on failure without breaking commit.
- **Contract note**: Phase 0 docs require standalone `OK` only; production prompt explicitly allows Yes/Approve/Arabic — implementation follows production prompt.
- **Restore / cancel / optimistic locking** on campaign row: partial (`lock_version` on models; not all mutation paths bump version yet).

---

## Phase D — End-to-end validation (automated subset)

| Step | Status |
|------|--------|
| Supervisor import (Excel → PostgreSQL) | Implemented (`supervisor_import_service` + admin import endpoint); manual upload not run in this session |
| Calendar import | Existing endpoints unchanged; not re-verified live |
| WhatsApp identify supervisor | Covered by `test_e2e_supervisor_flow` |
| Collect → review → confirm → save | Covered by `test_e2e_supervisor_flow` |
| Chroma update | Code path present; not verified with full embedding stack in unittest env |
| Dashboard refresh | PostgreSQL-backed list/stats wired; browser not exercised |
| Admin delete + embedding cleanup | API wired; manual not run |

---

## Remaining work (roadmap)

1. Migrate **all** admin settings, visitor questions, and file registry from `app.db` to unified PostgreSQL.
2. Wire **admin dashboard** audit log + version history UI to new APIs.
3. Complete **calendar-first routing** in visitor flow (priority over generic RAG) for WhatsApp groups.
4. Harden **optimistic locking** and idempotency on campaign commit under concurrent workers.
5. Run full **manual E2E** with WhatsApp bot + Docker PostgreSQL + Redis worker per `docs/cutover-runbook.md`.
6. Add **pytest** to CI (`requirements-dev`) and run embedding integration tests in pipeline with optional job.

---

## API changes (summary)

| Method | Path | Change |
|--------|------|--------|
| POST | `/admin/login` | Session token cookie; PG auth |
| POST | `/admin/settings/change-password` | Updates `admin_users.password_hash` |
| GET | `/admin/campaigns` | PostgreSQL campaigns |
| GET | `/admin/stats` | Merged legacy + platform stats |
| DELETE | `/admin/campaigns/{id}` | PG delete + Chroma cleanup + audit |
| POST | `/admin/campaign/import` | Supervisor activate + optional visitors |
| GET | `/admin/audit` | New |
