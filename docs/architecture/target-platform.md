# Target platform architecture

Status: Phase 0 architecture decision. The current SQLite/subprocess runtime remains legacy until later roadmap phases replace it.

## System boundaries

```text
WhatsApp / Admin UI
        |
FastAPI transport validation
        |
group/private policy -> PostgreSQL authorization -> persisted state/intent
        |                                      |
scoped retrieval                         campaign commands
        |                                      |
     Chroma                              PostgreSQL + outbox
                                               |
                                         Redis worker
                                               |
                                      targeted Chroma refresh
```

- PostgreSQL is the sole transactional source of truth for active supervisors, campaign ownership, campaigns and immutable versions, drafts, conversations and memory, imports, audit events, outbox events, and idempotency keys.
- Redis is limited to queues, locks, deduplication, rate limits, and caches. Its loss cannot erase authoritative state.
- Chroma is a reconstructable, versioned retrieval projection. Approved campaign changes refresh only the affected campaign/version and activate atomically after validation.
- FastAPI applies transport policy and authorization before intent or model processing.
- The model proposes intent, extraction, and wording only. It cannot authorize actors, select hidden sources, confirm on a user's behalf, or write directly to storage.

## Invariants

1. Groups are knowledge-only; all campaign mutation is private or through an authenticated admin channel.
2. Runtime supervisor authority is an active PostgreSQL-imported record, never config or Excel.
3. Every campaign has one active owner.
4. Campaign mutation requires a complete structured draft and explicit `OK`.
5. Persistent state survives restarts; idempotency prevents replayed mutations.
6. Campaign and audit history is immutable.
7. Only approved, effective campaigns join RAG; refresh is campaign/version targeted.
8. Trusted system date/time and the configured IANA timezone control relative-date behavior.
9. Admin bypass is explicit RBAC and audited.
10. Deletion tombstones by default; regulated purge is a separate privileged workflow.
11. Source priority and prompt-injection boundaries apply before generated instructions or retrieved content.

Normative detail is in `docs/contracts/`.
