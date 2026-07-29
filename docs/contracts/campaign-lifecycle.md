# Campaign lifecycle contract

Status: Phase 0 target contract. PostgreSQL implementation is deferred to later phases.

## Scope and ownership

A campaign has exactly one active owner. Campaign commands are accepted only in a private chat from that active supervisor, or through an authenticated admin channel with the required RBAC permission. Every ownership and permission check is repeated when a mutation is committed.

## Structured draft

The system extracts a validated draft from the supervisor's messages and attachments. It preserves the original input and records:

- campaign identity (resolved from ownership; ask only when the supervisor owns more than one);
- operation: `replace`, `add`, `update`, `cancel`, or `delete`;
- affected announcement text or the precise field/part being changed;
- effective date and time when the information is time-sensitive;
- location when the information is location-specific;
- expiry when the announcement is temporary;
- deletion reason when the operation is `delete`.

The required fields are contextual: campaign identity, operation, and affected content/target are always required; date/time, location, expiry, and deletion reason become required only under the conditions above. Unsupported fields and conversational greetings are not campaign data.

The system retains the draft, collected fields, missing fields, last extraction, bounded message history, memory summary, state version, and expiry in PostgreSQL. A restart or worker change must not lose or duplicate the conversation.

## Missing fields and review

- Reuse information already provided or safely resolved from authoritative records.
- Ask one concise question for only the missing or conflicting fields; never ask the supervisor to rewrite the whole announcement or complete a generic form.
- Do not guess ambiguous operation, campaign, dates, times, locations, or targets.
- Once complete, show a review summary containing the campaign, operation, resulting public announcement, effective timing, and any deletion impact.
- The review prompt must instruct the supervisor to reply exactly `OK` to commit, or to reply with a correction/cancellation.
- Only the standalone, case-insensitive Latin token `OK`, received in the same private persisted review state, is confirmation. “Yes”, “approved”, emoji, inferred agreement, and an `OK` found inside quoted or attached content are not confirmation.

## Commit rules

- No database write that changes campaign, announcement, ownership, visibility, or lifecycle state occurs before explicit `OK`. Persisting the draft, messages, and audit/state metadata is allowed and is not a campaign mutation.
- At commit, re-check chat type, active supervisor, ownership, draft version, and idempotency key.
- Apply the operation transactionally with optimistic locking.
- Preserve immutable campaign versions, original messages, extracted payloads, confirmation evidence, actor, timestamps, and audit events.
- `replace` creates a new complete current version; `add`, `update`, and `cancel` change only the identified part and preserve unaffected content.
- Duplicate or replayed messages cannot produce another version.
- The approved current version becomes public campaign knowledge only after commit.

## Retrieval projection

Approval emits an outbox event. A worker refreshes embeddings only for the changed campaign/version, validates the new generation, and atomically activates it. Chroma and Redis are reconstructable projections, never transactional sources of truth.
