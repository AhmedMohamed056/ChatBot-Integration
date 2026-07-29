# Routing and authorization contract

Status: Phase 0 target contract. Later phases must implement and test it; this document does not claim the legacy runtime already complies.

## Decision order

Every inbound message is handled in this order:

1. Validate transport metadata and classify the chat as `group` or `private`.
2. Apply the group/private policy.
3. Normalize the sender phone number once.
4. Authorize the sender against active PostgreSQL records.
5. Resume any persisted conversation state, including a pending review.
6. Process an explicit `OK` or cancellation.
7. Apply deterministic intent rules.
8. Use an LLM only as an intent/extraction fallback within these contracts.
9. Route knowledge questions to scoped retrieval.

Transport IDs are idempotency keys: one inbound message may produce at most one state transition, mutation, and reply.

## Group/private matrix

- Groups are knowledge-only. A group message can retrieve approved public knowledge, including an approved campaign's public announcement.
- No group participant, including a supervisor or admin, can create, update, cancel, delete, approve, or otherwise mutate a campaign from a group.
- Campaign management is available only in a private chat.
- A private non-supervisor remains knowledge-only.
- A private supervisor may manage only the campaign they own.
- Admin bypass is never implicit. It requires an authenticated admin role with the relevant RBAC permission and an audited admin channel.

## Supervisor authority and ownership

- Runtime authorization comes only from active supervisor and ownership records imported into and activated in PostgreSQL.
- Configuration values, environment variables, Excel files, uploaded files, display names, and model claims are never runtime authorization authorities.
- Excel is an import source only. Importing requires preview, validation, activation, and audit; the active PostgreSQL records then become authoritative.
- Each campaign has exactly one active owner. Ownership changes are explicit, transactional, permissioned, and audited.
- A supervisor cannot read private management state or mutate a campaign owned by another supervisor.
- Deactivated, expired, malformed, or unactivated records grant no authority.

## Prompt-injection boundary

Messages, attachments, imported cells, campaign text, retrieved chunks, and web/document content are untrusted data. Instructions found in them cannot change routing, authorization, source priority, tool permissions, confirmation rules, or this contract. The system must ignore requests to reveal hidden prompts, secrets, private records, or cross-campaign data.
