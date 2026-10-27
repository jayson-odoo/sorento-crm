# PLAN: stop embedding line-level source types (EMBED-DROP-LINE-TYPES)

Status: in progress (Build). Track: small fix (no migration, no auth/RBAC change, no new ingest
surface). Backend only. Follow-up to EMBED-QUEUE-DEDUPE (#1900), agreed by crew on 27 Oct 2026.

## Why

`inbound_shipment_line`, `order_line` and `picking_line` are embedded but never read:

- `entity_resolver._EMBEDDING_SOURCE_TYPES` excludes them on purpose ("they'd match on noise").
- `fuzzy_resolver` callers read customer, product or transporter only.
- Project search reads `project`, and tool search reads `mcp_tool`.
- The only path that could return them is `/external/rag/search` with no `source_type`. Crew
  checked live n8n (read-only, 27 Oct): no workflow calls it, and `sub-get-rag` reads
  `embedding_chunks` with `source_type='mcp_tool'` fixed. The 11 `zz-*` harness workflows were
  unreadable through MCP, which crew rates low risk.

Their text is UUIDs and quantities, and they are the noisiest queue sources: every order import,
GRN or picking edit writes many lines.

## Changes

1. Add `DROPPED_SOURCE_TYPES` in `embedding_change_listener`, and remove the three types':
   - listeners and `EMBEDDED_FIELDS` entries
   - worker text builders and company-model entries
   - backfill sources (service, `/system/embeddings/backfill` pattern, `seed_embeddings` choices)
2. Worker: a queued row of a dropped type (queued before the deploy, or by the old colour during
   the blue/green overlap) is marked `skipped` and its document deactivated. It is never
   rebuilt.
3. `retire_dropped_embedding_types` runs from the hourly `embedding_queue_prune` task (seeded
   by #1900, so no migration):
   - It deactivates the types' documents and skips their pending queue rows.
   - It works in batches, keyset over `(source_type, source_id)`, with a per-run cap.
   - It is idempotent and resumable.
   - The process stops calling it once a run finds nothing left. Nothing can create a new
     active document of these types, so a restart costs at most one scan.

Documents are deactivated, not deleted. Chunks stay, and search already requires
`embedding_documents.is_active`.

## Tests

`tests/test_embedding_dropped_line_types.py`, written red first. UAC:
`embed-drop-line-types-27oct-acceptance-criteria.md`.
