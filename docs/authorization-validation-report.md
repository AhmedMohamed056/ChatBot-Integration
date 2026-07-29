# Authorization validation report

**Date:** 2026-07-29  
**Scope:** WhatsApp private-chat supervisor gate  
**Status:** Automated tests passed (29). Gate verified before conversation / AI / persistence.

---

## Root cause of the bug

Three issues combined so unknown private numbers still looked “answered”:

1. **Default policy was `private_unauthorized_mode=message`.**  
   With an empty or un-imported `supervisors` table, every private message still returned a rejection string. The WhatsApp client treated that as a normal reply, so the bot appeared to answer everyone.

2. **Gate existed but was easy to misread as incomplete.**  
   Authorization ran early, but the default reply + WhatsApp error fallback (`Sorry, I could not reach…`) still produced outbound messages for non-supervisors.

3. **Private lifecycle could fall through to `VisitorFlow` (RAG/Gemini)** for knowledge intents after authorization. That path is removed for private supervisors so private WhatsApp cannot become a generic RAG assistant.

Runtime authority was already PostgreSQL/SQLite `supervisors` (not Excel). Local DB had **0 active supervisors**, so the intended outcome for unknowns is **ignore** (empty reply), not AI and not a rejection text unless mode=`message`.

---

## Authorization flow (after fix)

```text
Incoming WhatsApp message
        │
        ▼
chat_type == private?
   │              │
  yes             no (group)
   │              ▼
   │         knowledge / RAG only
   │         (campaign intents refused)
   ▼
authorize_private_sender(phone)
  = active row in supervisors
   │
   ├── NOT FOUND
   │     • return "" (ignore) or rejection text (message)
   │     • NO conversation / state / memory
   │     • NO Gemini / RAG / lifecycle / audit writes
   │
   └── FOUND
         • re-check in write session
         • conversation + lifecycle only
```

Excel path remains: **Upload → Import → PostgreSQL `supervisors` → WhatsApp auth**. The bot never reads Excel at runtime.

---

## Files modified

| File | Change |
|------|--------|
| `backend/services/message_orchestrator.py` | Auth-first private gate; ignore default; no pipeline before authorize |
| `backend/services/supervisor_authorization_service.py` | `authorize_private_sender`, phone lookup candidates |
| `backend/services/campaign_lifecycle_service.py` | Removed private `VisitorFlow`/RAG fallback; no inline Chroma worker on commit |
| `backend/services/runtime_settings.py` | Default unauthorized mode `ignore` |
| `backend/database.py` | Seed `private_unauthorized_mode=ignore` |
| `backend/main.py` | Startup forces ignore policy; `/message` docstring corrected |
| `whatsapp-bot/src/handlers/messageHandler.js` | Empty reply = silent; no error reply on private transport failure |
| `backend/tests/test_authorization_gate.py` | New gate / import / inactive / group regression tests |
| `backend/tests/test_private_whatsapp.py` | Updated for ignore + message modes |
| `backend/tests/test_platform_routing.py` | Private unknown → empty reply |
| `.github/workflows/ci.yml` | Includes `test_authorization_gate` |

---

## Tests added

`tests/test_authorization_gate.py`:

1. Unknown private → empty reply, VisitorFlow not called, **no** conversation/message/state/memory rows  
2. Message mode → rejection text only, still no conversation rows  
3. `is_active=false` → ignored  
4. Imported active supervisor → greeting with name + campaign  
5. Re-import Excel without supervisor → access revoked  
6. Group unknown → still knowledge path  

Also updated `test_private_whatsapp` and `test_platform_routing`.

---

## Test results

```text
python -m unittest \
  tests.test_authorization_gate \
  tests.test_private_whatsapp \
  tests.test_platform_routing \
  tests.test_e2e_supervisor_flow \
  tests.test_full_e2e_pipeline \
  tests.test_excel_import \
  tests.test_ownership \
  tests.test_admin_auth \
  tests.test_calendar_answer \
  tests.test_phase0_contracts \
  tests.test_phase1_schema \
  -q

Ran 29 tests in ~17.6s
OK
```

---

## Manual validation checklist

| Actor | Expected | How to verify |
|-------|----------|---------------|
| Unknown private WhatsApp | Silence (ignore) | Send DM from non-imported phone; bot must not reply |
| Imported active supervisor | Greeting with name + campaign | Import Excel, DM from that phone |
| Deactivated / removed after re-import | Silence | Re-import without that row; DM again |
| Group member | Knowledge answers only | Ask prayer/FAQ in group; campaign create refused |
| Website visitor | `/chat` still works | Browser chat independent of supervisors |

**Operator note:** Restart `uvicorn` so startup sets `private_unauthorized_mode=ignore`. Restart the WhatsApp bot process to pick up `messageHandler.js`. Re-run **Campaign import** so `supervisors` is populated (local DB previously had **0** supervisors).

To send a polite rejection instead of silence, set setting `private_unauthorized_mode` to `message` (admin/settings persistence).

---

## Remaining issues

1. **Settings still live in legacy `app.db`** for `private_unauthorized_mode`. Runtime auth itself is SQLAlchemy `supervisors` only.  
2. **Live WhatsApp smoke** must be done by the operator after restart + Excel import (not automatable in this environment without a linked session).  
3. **Chroma refresh** after campaign commit requires running `python worker.py` (no longer inline on commit).

None of these reopen the private unauthorized AI/conversation pipeline.
