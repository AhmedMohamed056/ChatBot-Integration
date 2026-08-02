# Phase 3.1 — Persistent Conversation Memory: Final Report

## Overview

Implemented a persistent conversation memory layer for authorized supervisors that enables multi-turn conversation understanding. The assistant can now resolve contextual references like "it", "this", "No", and "Cancel" based on the active conversation state.

---

## Files Modified

### 1. `backend/services/conversation_memory_service.py` (primary implementation)

**Why changed:** This is the core of the memory layer. The existing `ConversationMemoryService` was enhanced (not duplicated) to store and maintain the full set of required memory fields.

**What was added/changed:**

- **Memory keys** for all required fields:
  - `current_topic` — the subject being discussed (description, budget, services, channels)
  - `last_user_intent` — the user's last intent
  - `last_assistant_action` — the assistant's last action
  - `pending_context` — structured `{field, old_value, new_value}` for in-progress edits
  - `pending_draft` — in-progress draft data
  - `conversation_summary` — short running summary
  - `last_edited_field` — most recently modified field
  - `recent_messages` — last 10 messages for context

- **`UserIntent` enum:** `UPDATE_DESCRIPTION`, `UPDATE_BUDGET`, `UPDATE_SERVICES`, `UPDATE_CHANNELS`, `UPDATE_FIELD`, `DELETE_SERVICE`, `DELETE_PARAGRAPH`, `CONFIRM`, `REJECT`, `CANCEL`, `UNKNOWN`.

- **`AssistantAction` enum:** `AskedForDescription`, `AskedForBudget`, `AskedForServices`, `AskedForChannels`, `AskedForField`, `WaitingForConfirmation`, `UpdatedDescription`, `UpdatedBudget`, `UpdatedServices`, `UpdatedChannels`, `UpdatedField`, `DeletedService`, `DeletedParagraph`, `ProposedChange`, `Idle`.

- **`PendingContext` dataclass** with `to_dict`/`from_dict` for structured pending edit state.

- **`ConversationMemoryData` dataclass** with `is_idle()` and `clear_task_state()` methods.

- **Intent detection (`_update_user_intent`)** — Arabic + English keyword matching. Key fix: **context-aware "No" handling**. "No"/"لا"/"لاء" is classified as `REJECT` when the assistant is `WaitingForConfirmation` or `ProposedChange`, and as `CANCEL` otherwise. Explicit "cancel"/"إلغاء"/"الغاء" is always `CANCEL`.

- **Assistant action detection (`_update_assistant_action`)** — infers action from outbound message content (asking, waiting for confirmation, update/delete completion, proposals).

- **Pending context tracking (`_update_pending_context`)** — captures the field being edited and the new value when the user provides it.

- **Memory lifecycle methods:**
  - `update_memory_from_message()` — called on every inbound supervisor message and every outbound assistant reply.
  - `clear_task_state()` / `set_idle()` — clears task-specific state (intent, action, pending context/draft) while preserving topic/summary/last-edited-field/recent-messages for continuity.
  - `clear_memory()` / `clear_memory_field()` — full/field-level clearing.

- **Persistence fix (`_save_memory_field`):** Previously `None` values were silently skipped, so cleared fields (e.g. `pending_context`, `last_user_intent`) kept their stale values after a task ended. Now `None` triggers an explicit `clear_memory_field()` (tombstone), and each save commits. This was the root cause of the Scenario 4 failure.

### 2. `backend/prompt_builder.py`

**Why changed:** To inject the conversation memory into the AI prompt so the model can resolve references.

**What changed:** `_conversation_memory_section()` now extracts and displays `current_topic`, `last_user_intent`, `last_assistant_action`, `pending_context` (with Field/Old Value/New Value sub-lines, values truncated to 100 chars), `conversation_summary`, `last_edited_field`, `pending_draft`, and `recent_messages`. The header hint mentions 'it', 'this', 'No', 'Cancel' references. The section is omitted entirely when all fields are blank. Prompt structure was otherwise unchanged.

### 3. `backend/services/campaign_lifecycle_service.py`

**Why changed:** To wire memory updates into the supervisor message flow at every response path (not just the AI fallback).

**What changed:**
- Initializes `ConversationMemoryService` at the start of `handle()` and records the inbound message.
- **CANCEL path:** calls `set_idle()` then records the outbound reply.
- **CONFIRM_OK + pending path:** after `_commit()`, calls `set_idle()` then records the outbound reply.
- **DELETE_CAMPAIGN, missing-field, review-summary, KNOWLEDGE_QUESTION paths:** each records the outbound reply in memory before returning.
- **AI fallback path:** removed duplicate inline import and duplicate inbound memory update (now handled once at the top of `handle()`); kept the outbound memory update after `visitor_flow.handle_message_with_supervisor()`.

### 4. `backend/test_conversation_memory_scenarios.py` (new)

**Why added:** Validation harness for the 4 required scenarios, using an in-memory SQLite database and a test supervisor.

---

## Validation Scenarios

All 4 scenarios **PASS** (`python test_conversation_memory_scenarios.py`):

### Scenario 1 — "Make it shorter" ✅
`Change campaign description` → intent `UPDATE_DESCRIPTION`; `What is the new description?` → action `AskedForDescription`, `pending_context.field = description`; user provides text → `pending_context.new_value` captured; `Done` → action `UpdatedDescription`; `Make it shorter` → context maintained (`last_edited_field = description`, `current_topic = description`), so "it" resolves to the description.

### Scenario 2 — "Delete this paragraph" ✅
After a description edit flow, `last_edited_field = description`. `Delete this paragraph` → intent `DELETE_PARAGRAPH`, with `last_edited_field` available so "this" resolves to the previous description.

### Scenario 3 — "No" (rejection) ✅
Assistant reaches `WaitingForConfirmation`. `No` → intent `REJECT` (not `CANCEL`), because the context-aware check detects the pending confirmation state.

### Scenario 4 — "Cancel" → IDLE ✅
Active task (`AskedForDescription` + pending context). `Cancel` → intent `CANCEL`; after `set_idle()`: action = `Idle`, `pending_context = None`, `last_user_intent = None`. Conversation is IDLE.

---

## Remaining Limitations

1. **Keyword-based intent detection** — Intent/action classification relies on Arabic/English keyword matching, not ML. Unusual phrasings may fall back to `UNKNOWN`/`UPDATE_FIELD`. The AI model still does the heavy lifting via the injected memory section; the structured fields are a deterministic aid.
2. **Reference resolution is contextual, not semantic** — "it"/"this" resolve via `last_edited_field`/`current_topic`/`pending_context`. If the user switches topics mid-conversation without keywords, the reference may point to the previous field.
3. **Conversation summary is heuristic** — It's a truncated append of recent messages (max 500 chars), not an LLM-generated abstractive summary.
4. **Recent messages capped at 10** — Older context falls out of the window (by design, to bound memory size).
5. **`clear_task_state` preserves topic/summary/last-edited-field** — This is intentional for continuity, but means "IDLE" conversations still carry some context. A full wipe requires `clear_memory()`.
6. **No cross-conversation memory** — Memory is scoped per `conversation_id`. Long-term learning across conversations is explicitly out of scope per the task constraints.

---

## Scope Compliance

- ✅ Reused existing `ConversationMemoryService` (modified, not duplicated).
- ✅ Did NOT change: Authorization, Supervisor Detection, Visitor Flow, Website Flow, Group Flow, RAG, Prompt Builder structure, Campaign Snapshot.
- ✅ Did NOT implement: Campaign Knowledge, Long-term learning, Calendar, Campaign CRUD, Versioning, Draft Engine, RAG changes, New prompts, New personas, New architecture.
