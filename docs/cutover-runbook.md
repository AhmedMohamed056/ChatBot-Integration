# Production cutover runbook

Status: Phase 0 cutover contract. Commands, owners, and environment-specific values must be completed and rehearsed before production; this runbook does not authorize an early cutover.

## Entry criteria

- Routing, lifecycle, source, retention, timezone, RBAC, and prompt-injection contract tests pass.
- PostgreSQL migration reconciliation has zero unexplained count, identity, ownership, or hash differences.
- Every campaign has exactly one active owner and every authorized supervisor comes from an activated import.
- Backup restore and rollback have been rehearsed.
- Outbox/worker retries, targeted Chroma generation activation, idempotency, restart, concurrency, and group/private role-matrix tests pass.
- Readiness, logs, audit events, queue/index health, dashboards, and on-call ownership are verified.

## Cutover

1. Announce the controlled window and record release, schema, import, and index generation IDs.
2. Take and verify restorable backups of legacy stores, PostgreSQL, configuration, and required document assets.
3. Run the repeatable bulk import; quarantine malformed records.
4. Reconcile source IDs, counts, checksums, relationships, ownership, timestamps, and active versions.
5. Enable shadow reads and compare responses without changing user-visible results.
6. Enable controlled compatibility writes and reconcile idempotency and version outcomes.
7. Begin a brief legacy write pause; keep knowledge-only reads available where safe.
8. Apply and reconcile the final delta.
9. Switch transactional reads/writes to PostgreSQL and processing to the direct backend path.
10. Activate only validated Chroma generations; do not perform an unscoped rebuild during the switch.
11. Run smoke tests for group knowledge, blocked group mutation, private supervisor ownership, explicit `OK`, restart recovery, admin RBAC, deletion tombstone, date/time, and source priority.
12. Open the monitored rollback window and record the cutover decision.

## Abort and rollback

Abort on unexplained reconciliation differences, cross-owner access, any unconfirmed write, duplicate version, missing state, unhealthy queue/index, audit loss, or breached service objectives.

During the rollback window: stop new writes, preserve evidence and idempotency keys, drain or quarantine in-flight outbox work, restore the verified legacy path, reconcile post-cutover writes, and announce status. Never silently run two writable authorities.

## Exit criteria

- Service objectives remain healthy for the approved observation window.
- No unexplained migration, ownership, audit, queue, or retrieval discrepancy remains.
- Restore points and regulated-purge obligations are documented.
- The release owner signs off; legacy stores become read-only and are retained or purged only under the retention contract.
