# Supervisor Message Execution Pipeline — Technical Audit

**Scope:** Read-only audit. No code was modified, refactored, or added.
**Test message:** `"من أنا"` ("Who am I") sent by an **authorized supervisor** in a private WhatsApp chat.
**Symptom under investigation:** Supervisor is correctly recognized (name, campaign, campaign exists), yet Gemini replies with the **Visitor** persona — "أنا معين الزائرين" — instead of the Campaign Supervisor Assistant persona.

---

## 1. Execution Diagram

```
WhatsApp (supervisor phone)
   │  "من أنا"
   ▼
[1] whatsapp-bot/src/handlers/messageHandler.js  handleIncomingMessage()
   │  POST /message  {phone, message, chat_type:"private", external_chat_id, external_message_id}
   ▼
[2] backend/main.py  @app.post("/message")  message()            (line 1654)
   │  validates body → MessageRequest → ConversationRouter.route_message()
   ▼
[2b] backend/conversation_router.py  ConversationRouter.route_message()  (line 12)
   │  wraps payload in InboundMessage → MessageOrchestrator.handle()
   ▼
[3] backend/services/message_orchestrator.py  MessageOrchestrator.handle()  (line 70)
   │  chat_type == "private" → _authorize_private_read_only() → _handle_supervisor_private()
   ▼
[4] backend/services/supervisor_authorization_service.py  authorize_private_sender()  (line 62)
   │  get_active_supervisor() → supervisors table lookup → Supervisor row (AUTHORIZED)
   ▼
[5] Conversation loading (message_orchestrator._handle_supervisor_private)
   │  get/create Conversation row for supervisor phone
   ▼
[6] backend/services/campaign_lifecycle_service.py  CampaignLifecycleService.handle()  (line 63)
   │  detect_intent("من أنا") → GENERAL_QUESTION → falls to FALLBACK branch (lines 145-183)
   ▼
[7] backend/services/intent_router.py  detect_intent()  (line 78)
   │  no regex match, no "?" → IntentResult(Intent.GENERAL_QUESTION, 0.4)
   ▼
[8] backend/services/supervisor_context_service.py  build_supervisor_context()  (line 109)
   │  SupervisorContext{name, phone, campaign_id, campaign_name, status, version, state, pending_draft}
   ▼
   │  (lifecycle FALLBACK) visitor_flow = VisitorFlow()
   │  visitor_flow.handle_message_with_supervisor(phone, message, supervisor_context, conversation_id)
   ▼
[11] backend/ai_context_builder.py  build_ai_context()  (line 181)
   │  AIContext{ supervisor=supervisor_context.to_dict(), conversation_memory=..., campaign_knowledge=..., ... }
   ▼
[13/14] backend/visitor_flow.py  handle_message_with_supervisor()  (line 170)
   │  line 223:  system_prompt = build_visitor_system_prompt()   <-- *** VISITOR PROMPT LOADED ***
   ▼
[12] backend/prompt_builder.py  build_prompt(system_prompt, context)  (line 332)
   │  assembles SYSTEM PROMPT + CURRENT CONTEXT (incl. SUPERVISOR section) + closing instruction
   ▼
[15] backend/gemini_client.py  GeminiClient.generate(system_prompt="", user_prompt=full_prompt)  (line 98)
   │  combined_prompt = f"{system_prompt}\n\n{user_prompt}"  →  messages=[{role:user, parts:[combined]}]
   ▼
   Gemini API  (model: gemini-2.5-flash)
   ▼
[16] Response string → VisitorFlowResult.reply → lifecycle → orchestrator → router → /message → messageHandler
   │  message.reply(reply)  → WhatsApp
   ▼
Supervisor sees: "أنا معين الزائرين ..."  (WRONG persona)
```

---

## 2. Call Stack (with per-layer verdict)

| # | File | Function | Input | Output | Executed? |
|---|------|----------|-------|--------|-----------|
| 1 | `whatsapp-bot/src/handlers/messageHandler.js` | `handleIncomingMessage()` (L43) | WA message | POST payload `{phone,message,chat_type,...}` (L178-184) | **YES** |
| 2 | `backend/main.py` | `message()` (L1654) | JSON body | `{"reply": str}` | **YES** |
| 2b | `backend/conversation_router.py` | `route_message()` (L12) | phone/message/chat_type | reply str | **YES** |
| 3 | `backend/services/message_orchestrator.py` | `handle()` (L70) | InboundMessage | reply str | **YES** |
| 4 | `backend/services/supervisor_authorization_service.py` | `authorize_private_sender()` (L62) → `get_active_supervisor()` (L43) | phone | `Supervisor` row | **YES** (authorized) |
| 5 | `message_orchestrator._handle_supervisor_private` | conversation load | supervisor | `Conversation` row | **YES** |
| 6 | `backend/services/campaign_lifecycle_service.py` | `handle()` (L63) | supervisor, conversation_id, message | reply | **YES** |
| 7 | `backend/services/intent_router.py` | `detect_intent()` (L78) | "من أنا" | `IntentResult(GENERAL_QUESTION, 0.4)` | **YES** |
| 8 | `backend/services/supervisor_context_service.py` | `build_supervisor_context()` (L109) | session, supervisor, conversation_id | `SupervisorContext` | **YES** |
| 9 | CampaignSnapshot builder | — | — | — | **NO** — no dedicated "CampaignSnapshot" builder is invoked in this path. Campaign data arrives only as scalar fields inside `SupervisorContext` (campaign_id/name/status/version). |
| 10 | `backend/services/conversation_memory_service.py` | `get_memory_for_prompt()` (L274) / `load_memory()` | conversation_id | memory dict | **YES** (via AIContextBuilder) |
| 11 | `backend/ai_context_builder.py` | `build_ai_context()` / `build_context()` (L181) | message, phone, supervisor, conversation_id | `AIContext` | **YES** |
| 12 | `backend/prompt_builder.py` | `build_prompt()` (L332) | system_prompt + AIContext | full prompt string | **YES** |
| 13 | `backend/prompts/supervisor_prompt.py` | `build_supervisor_system_prompt()` (L20) | — | supervisor prompt text | **NO — NEVER CALLED** |
| 14 | `backend/prompts/visitor_prompt.py` | `build_visitor_system_prompt()` (L20) | — | visitor prompt text | **YES** (loaded at visitor_flow.py:223) |
| 15 | `backend/gemini_client.py` | `generate()` (L98) | system_prompt="", user_prompt=full_prompt | response text | **YES** |
| 16 | `messageHandler.js` | `message.reply()` (L202) | reply str | WhatsApp message | **YES** |

---

## 3. Prompt Audit

### Which prompt is loaded?
**The VISITOR prompt.** In the supervisor path, `visitor_flow.handle_message_with_supervisor()` executes:

```python
# backend/visitor_flow.py  line 223
system_prompt = build_visitor_system_prompt()
```

`build_visitor_system_prompt()` (backend/prompts/visitor_prompt.py:20) loads **`backend/prompts/visitor_instructions.md`** (lru_cached).

`build_supervisor_system_prompt()` (backend/prompts/supervisor_prompt.py:20) — which would load `supervisor_instructions.md` — has **zero call sites** and is **not exported** from `backend/prompts/__init__.py` (which only exports `build_visitor_system_prompt`).

### Does PromptBuilder discard any section?
**No.** `build_prompt()` (prompt_builder.py:332) appends every non-empty section in fixed order (lines 355-393):
`date → language → campaign_knowledge → supervisor → visitor → calendar → prayer → conversation_memory → user_message`.
The `_supervisor_section()` (lines 199-238) **is** emitted because `ctx.supervisor` is a populated dict. Nothing is dropped. The user message is always included, labeled **"VISITOR MESSAGE"** (line 283) even for a supervisor.

### Is the supervisor prompt overwritten?
There is nothing to overwrite — the supervisor prompt is **never loaded**. Worse, `visitor_flow` calls Gemini with `system_prompt=""` (lines 241-244), so `GeminiClient.generate()` builds `combined_prompt = f"{system_prompt}\n\n{user_prompt}"` = `"\n\n" + full_prompt`. The **only** persona text Gemini sees is the visitor persona embedded at the top of `full_prompt`.

---

## 4. Gemini Input — EXACT final prompt

Reconstructed verbatim from `build_prompt()` assembly (prompt_builder.py:407-418) for message `"من أنا"`. Dynamic values shown as `‹…›`; all static text is exact.

```
# تعليمات التعامل مع الزائر — معين الزائرين
‹… full contents of backend/prompts/visitor_instructions.md …›
- أنا **معين الزائرين**، أخدم زوار النبي محمد صلى الله عليه وآله وسلم…
‹… rest of visitor persona / rules …›
========================
CURRENT CONTEXT
DATE
‹current date / weekday›
------------------------
LANGUAGE
‹ar›
------------------------
CAMPAIGN KNOWLEDGE
‹supervisor-taught facts, if any›
------------------------
SUPERVISOR
You are speaking with an authorized campaign supervisor.
Supervisor Name: ‹supervisor_name›
Phone: ‹phone›
Campaign ID: ‹campaign_id›
Campaign Name: ‹campaign_name›
Campaign Status: ‹campaign_status›
Current Campaign Version: ‹current_campaign_version›
Conversation State: ‹conversation_state›
Pending Draft: ‹pending_draft›
------------------------
CONVERSATION MEMORY
Use this memory to understand references like 'اجعله أقصر', 'غيرها', 'احذف الفقرة الثانية'
Current Topic: ‹current_topic›
Conversation Summary: ‹conversation_summary›
Last Edited Field: ‹last_edited_field›
Recent Messages:
  [inbound] من أنا
------------------------
VISITOR MESSAGE
من أنا
========================
Answer the user according to the System Prompt above.
```

**Key observation:** The `SUPERVISOR` block is present as *data*, but the **System Prompt header** (the strongest instruction) is the visitor persona. The closing line — "Answer the user according to the System Prompt above." — explicitly tells Gemini to follow the **visitor** system prompt.

---

## 5. Gemini Output

```
أنا معين الزائرين، أخدم زوار النبي محمد صلى الله عليه وآله وسلم…
```
(The model adopts the visitor persona declared in the system prompt, ignoring the SUPERVISOR context block.)

---

## 6. Root Cause Analysis

**Primary root cause (confidence: HIGH):**
The supervisor fallback path delegates to the **visitor** pipeline. Specifically:

1. `CampaignLifecycleService.handle()` (campaign_lifecycle_service.py:145-183) — for a `GENERAL_QUESTION` intent — builds a `SupervisorContext` and then calls `VisitorFlow().handle_message_with_supervisor(...)` (lines 165-171).
2. `VisitorFlow.handle_message_with_supervisor()` (visitor_flow.py:170) loads the **visitor** system prompt at **line 223**: `system_prompt = build_visitor_system_prompt()`.
3. The supervisor identity is injected only as a `SUPERVISOR` *context section* (prompt_builder.py:199-238), which is subordinate to the system prompt.
4. `GeminiClient.generate()` is invoked with `system_prompt=""` (visitor_flow.py:241-244), so no supervisor persona is ever presented as the system instruction.
5. The final instruction "Answer the user according to the System Prompt above." (prompt_builder.py:418) directs Gemini to obey the visitor persona.

**Net effect:** Gemini receives a visitor system prompt that explicitly says "أنا **معين الزائرين**" (visitor_instructions.md line 7), plus a data block mentioning a supervisor. The persona instruction wins, so the model answers as the Visitor Assistant.

**Contributing design gap (confidence: HIGH):**
`build_supervisor_system_prompt()` exists (supervisor_prompt.py:20) and `supervisor_instructions.md` contains the correct persona ("أنا المساعد المسؤول عن إدارة إعلانات الحملات…", line 7), but it is **dead code** — never imported into the runtime path and never called.

---

## 7. List of Suspected Bugs

| # | Bug | Location | Confidence |
|---|-----|----------|------------|
| B1 | Supervisor path loads the **visitor** system prompt instead of the supervisor prompt. | `backend/visitor_flow.py:223` | **HIGH** |
| B2 | `build_supervisor_system_prompt()` has **zero call sites** and is not exported from `prompts/__init__.py`; supervisor persona is unreachable. | `backend/prompts/supervisor_prompt.py:20`, `backend/prompts/__init__.py` | **HIGH** |
| B3 | Gemini is called with `system_prompt=""`, so the persona is carried only inside `full_prompt` and defaults to the visitor persona; nothing overrides it. | `backend/visitor_flow.py:241-244` | **HIGH** |
| B4 | Supervisor identity is injected as a *context section* rather than as the system prompt, so it cannot change the assistant's persona. | `backend/prompt_builder.py:199-238` + `visitor_flow.py:227` | **HIGH** |
| B5 | User message section is hard-labeled **"VISITOR MESSAGE"** even in the supervisor flow, reinforcing the wrong framing. | `backend/prompt_builder.py:283` | **MEDIUM** |
| B6 | Closing instruction "Answer the user according to the System Prompt above." forces adherence to the visitor system prompt. | `backend/prompt_builder.py:418` | **MEDIUM** |
| B7 | Legacy `backend/supervisor_flow.py` state machine exists but is **not wired** into the orchestrator (dead/parallel code), which may have caused confusion about where supervisor handling lives. | `backend/supervisor_flow.py` (self-references only) | **MEDIUM** |
| B8 | No dedicated "CampaignSnapshot" builder runs in this path; campaign data is limited to scalar fields on `SupervisorContext`. | `backend/services/supervisor_context_service.py` | **LOW** (design observation) |

---

## 8. Answers to Audit Questions

**Q1. Which prompt is loaded — Visitor or Supervisor?**
**Visitor.** `build_visitor_system_prompt()` at `visitor_flow.py:223`. The supervisor prompt is never loaded.

**Q2. Is the supervisor context included in the final prompt? Show every field.**
**Yes**, as a `SUPERVISOR` context section (prompt_builder.py:199-238). Fields emitted (when present): `Supervisor Name`, `Phone`, `Campaign ID`, `Campaign Name`, `Campaign Status`, `Current Campaign Version`, `Conversation State`, `Pending Draft`. It is **data**, not the system persona.

**Q3. Is the campaign snapshot injected? Show fields.**
There is **no separate CampaignSnapshot injection** in this path. Campaign info arrives only as scalar fields inside `SupervisorContext`: `campaign_id`, `campaign_name`, `campaign_status`, `current_campaign_version`. (Separately, a `CAMPAIGN KNOWLEDGE` section of supervisor-taught facts is injected via `_campaign_knowledge_section`.)

**Q4. Is conversation memory injected?**
**Yes.** `_conversation_memory_section()` (prompt_builder.py:285-324) emits `Current Topic`, `Conversation Summary`, `Last Edited Field`, `Pending Draft`, and up to 5 `Recent Messages`, sourced from `ConversationMemoryService.get_memory_for_prompt()` (conversation_memory_service.py:274).

**Q5. Does PromptBuilder discard any section?**
**No.** All non-empty sections are appended in fixed order; nothing is dropped (prompt_builder.py:355-393).

**Q6. Does Gemini receive the supervisor prompt, or is it overwritten?**
Gemini **never receives** the supervisor prompt. It is not overwritten — it is simply never loaded. Gemini receives the visitor system prompt (embedded in `full_prompt`), and `generate()` is called with `system_prompt=""`.

**Q7. Where does "أنا معين الزائرين" come from, and why does Gemini still use it?**
- **Exact source:** `backend/prompts/visitor_instructions.md` — line 1 (`# تعليمات التعامل مع الزائر — معين الزائرين`) and **line 7** (`- أنا **معين الزائرين**، أخدم زوار النبي محمد…`).
- **Why Gemini uses it:** because `handle_message_with_supervisor()` loads this file as the system prompt (visitor_flow.py:223), and the closing instruction (prompt_builder.py:418) tells Gemini to answer according to that system prompt. The SUPERVISOR block is only contextual data and does not override the persona.

**Q8. Is there any second PromptBuilder / VisitorFlow / GeminiClient in the path?**
**No.** A single `PromptBuilder.build_prompt()`, a single `VisitorFlow`, and a single `GeminiClient` are used. (The legacy `backend/supervisor_flow.py` is not referenced by the orchestrator.)

**Q9. All occurrences of "معين الزائرين":**
- `backend/prompts/visitor_instructions.md` (lines 1, 7) — **the persona source**.
- `backend/database.py` — default `bot_name`.
- `backend/main.py` — bot-name fallback.
- `backend/index.html` — web UI label.
- `backend/_visitor_source.txt` and verify artifacts — test/verify output.

**Q10. All call sites of `build_visitor_system_prompt`:**
- `backend/visitor_flow.py:127` (visitor path)
- `backend/visitor_flow.py:223` (**supervisor path — the bug**)
- `backend/_verify_task13.py` (verification script)
- `backend/tests/test_visitor_flow.py` (tests, mocked)

**Q11. All call sites of `build_supervisor_system_prompt`:**
- **None.** Only its definition at `backend/prompts/supervisor_prompt.py:20`. Zero runtime call sites.

---

## 9. One-paragraph Conclusion

The supervisor is correctly authorized and a rich `SupervisorContext` is built and injected into the prompt, but the pipeline routes the message through `VisitorFlow.handle_message_with_supervisor()`, which loads the **visitor** system prompt (`visitor_instructions.md`, "أنا معين الزائرين") at `visitor_flow.py:223` and calls Gemini with an empty `system_prompt`. The supervisor identity therefore appears only as a subordinate context block, while the dominant system instruction — reinforced by the closing line "Answer the user according to the System Prompt above." — is the visitor persona. The correct supervisor persona (`supervisor_instructions.md` via `build_supervisor_system_prompt()`) exists but is dead code with zero call sites. This is why Gemini answers as the Visitor Assistant despite recognizing the supervisor.
