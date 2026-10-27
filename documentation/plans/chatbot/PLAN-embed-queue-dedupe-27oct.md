# PLAN: embedding_queue dedupe + cheap poll (EMBED-QUEUE-DEDUPE)

Status: in review. Track: standard (carries a migration). Backend only, no UI.

## Problem (prod, 27 Oct 2026)

`embedding_queue` holds about 1,175,503 pending rows, about 94% of them duplicates (the 20 Oct
clone had 852,900 pending rows over 54,296 distinct sources). The DB fallback processor takes
10 rows per run every 15-30 s. Each poll seq-scans the 2.5 GB table (a `count(*)` plus
`ORDER BY CASE source_type='mcp_tool' ..., created_at LIMIT 10`), so prod DB IO never stops.

Causes:
- `embedding_change_listener` queues one row per insert, update or delete of every tracked
  model. It does not dedupe, and it also queues on no-op updates: SQLAlchemy fires
  `after_update` for any flushed object, even one where no column value changed.
- The Order Tracking import bulk-queues every order it touched, changed or not.

## Decisions

- **Dedupe without a unique index** (crew agreed, 27 Oct). Deploy is blue/green, and the old
  colour keeps inserting duplicates while `CREATE UNIQUE INDEX CONCURRENTLY` runs, so that
  build would fail.
  - An enqueue that finds a pending row locks it `FOR SHARE` until its transaction ends, and
    inserts nothing.
  - The worker claims with `FOR UPDATE NOWAIT`. A busy row stays pending for the next poll, so
    the scheduler never waits on an import.
  - Supersede and backlog dedupe use `SKIP LOCKED`.
  - Row locks, not advisory locks (review B1): an advisory lock takes a slot in the shared lock
    table, and 20k of them in one transaction ran out of shared memory on Postgres defaults.
    Row locks live in the tuple.
  - The guarantee holds once both colours run this code. During the blue/green overlap, an
    old-colour worker still claims rows without the lock.
- **No data change in the migration** (owner, 27 Oct). Collapsing the backlog in a migration
  would write about 8 GB of WAL and take about 8 minutes. The scheduled task
  `embedding_queue_dedupe` does it instead.
- **Index builds never stall a release** (owner, 27 Oct). Each build is `CONCURRENTLY`, with a
  5s lock wait and a 90s cap per index. A failed build logs a WARNING and the release goes on.
  The hourly prune task retries.

## Changes

1. Enqueue dedupe in `embedding_change_listener.enqueue_pending` / `pending_queue_ids`, used by the listeners,
   `bulk_enqueue_embedding_events`, `EmbeddingEventService.queue_event` (which reuses the pending
   row and replaces its payload) and the product bulk import.
2. An update queues only when a column in `EMBEDDED_FIELDS` changed. Each model's list is taken
   from `embedding_worker._canonical_for_source`, plus `company_id`.
3. The Order Tracking import queues only orders that are new or had an embedded field change.
4. Worker claim: under the lock, it marks the source's other pending rows `skipped`
   ("dedup: superseded"). A failed run whose source already has a newer pending row goes to
   `skipped`, not back to `pending`.
5. `ix_embedding_queue_pending_poll_cov` (crew's definition, verbatim) and
   `ix_embedding_queue_pending_source`, both on the model and built by migration
   `eqd_0001_pending_idx_prune` through `app/services/embedding_queue_indexes.py`. The poll no
   longer runs `count(*)`.
6. Settings: `EMBEDDING_QUEUE_BATCH_SIZE` (default 10), `EMBEDDING_QUEUE_RETENTION_DAYS`
   (default 14), and the prune and dedupe batch knobs.
7. Scheduled tasks, both seeded by the migration:
   - `embedding_queue_prune` (hourly): rebuilds a missing index in its daily retry hour
     (19 UTC), then deletes completed and skipped rows older than 14 days, 1000 per batch, at
     most 100 batches per run.
   - `embedding_queue_dedupe` (every 5 min): skips superseded pending rows, keeping the newest
     per source, 10k per batch, at most 10 batches per run with a 1s pause between them. A
     no-op once the backlog is clean.

## Follow-up (crew OK, separate PR after this one)

Drop the line-level types `inbound_shipment_line`, `order_line` and `picking_line`. No in-app
reader uses them, and no n8n workflow calls `/external/rag/search` (crew checked; the 11 `zz-*`
harness workflows were unreadable).

The follow-up:
- removes their listeners and backfill entries
- deactivates their documents through the scheduled-task path
- writes its tests red-first

## Known, not fixed here

- The product bulk import still queues every product in the file, changed or not. Dedupe
  keeps that to one pending row per product.
- A VALID hand-built index with the right name is reused without comparing its definition.
  That is crew's instruction.

## Tests

UAC: `embed-queue-dedupe-27oct-acceptance-criteria.md`.


`tests/test_embedding_queue_dedupe.py` covers:
- field lists match the model columns
- no-op and same-value updates queue nothing
- one pending row per source
- `queue_event` reuses the pending row and takes the new payload
- the shared lock
- worker supersede and retry
- the import queues only changed orders
- poll order, batch size and index use
- prune
- backlog dedupe: keeps the newest, a second run is a no-op, a capped run resumes
- the index build fallback: lock timeout, failed build, INVALID rebuild, settings restored
