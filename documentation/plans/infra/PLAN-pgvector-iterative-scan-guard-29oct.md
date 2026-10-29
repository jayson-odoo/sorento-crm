# PLAN: guard `SET LOCAL hnsw.iterative_scan` for pgvector < 0.8 (PGVECTOR-GUARD)

Status: in progress. Small fix track (no migration, no auth/RBAC change, no new ingest surface, diff well under 300 lines).

## Problem

#1967 (e86b459281) issues `SET LOCAL hnsw.iterative_scan = relaxed_order` unguarded at:

- `sorento_crm_backend/app/services/embedding_service.py` (`search_current`, single non-hot source)
- `sorento_crm_backend/app/services/entity_resolver.py` (`_iterative_scan_for`, used by tier-3 lookup and RAG phrase resolution)

The GUC exists only in pgvector >= 0.8. On an older extension Postgres rejects the SET
(`unrecognized configuration parameter`), which aborts the surrounding transaction: record search
fails outright and entity resolution loses its vector tier. Prod's pgvector version is unknown.

## Fix

One helper, `app/services/embedding_indexes.py::set_iterative_scan(db)`:

1. On first call per process, read `SELECT extversion FROM pg_extension WHERE extname = 'vector'`
   (a plain catalog read; cannot fail in a way the SET would) and cache whether the version is >= 0.8.
2. Supported: issue the `SET LOCAL` exactly as before.
3. Unsupported (older version, or extension row missing, or unparseable version): skip the SET, log
   ONE WARNING per process, and let the query run as before #1967 (no iterative scan).

Both call sites route through the helper. No SAVEPOINT probe is needed: the SET is never sent on an
unsupported server, so the transaction is never aborted.

## Acceptance criteria

See `pgvector-iterative-scan-guard-acceptance-criteria.md`.
