# PLAN: embedding_queue dedupe + cheap poll (EMBED-QUEUE-DEDUPE)

Status: in progress (Build). Track: standard (carries a migration), backend only, no UI.

## Problem (prod, 27 Oct 2026)

`embedding_queue` holds ~1,175,503 pending rows, ~94% duplicates (20 Oct clone: 852,900 pending
over 54,296 distinct sources). The DB fallback processor takes 10 rows per run every 15-30 s and
each poll seq-scans the 2.5 GB table (`count(*)` plus `ORDER BY CASE source_type='mcp_tool' ...,
created_at LIMIT 10`, `app/scheduler/task_scheduler.py`), giving constant DB IO.

Causes:
- `app/services/embedding_change_listener.py` queues one row per insert/update/delete of every
  tracked model, with no dedupe and also on no-op updates (SQLAlchemy `after_update` fires for a
  flushed object even when no column value changed).
- `OrderService` Order Tracking import bulk-queues every order the import touched, changed or not.

## Changes

1. Dedupe at enqueue. Partial unique index `uq_embedding_queue_pending_source` on
   `(source_type, source_id) WHERE status = 'pending'`; every enqueue path inserts with
   `ON CONFLICT DO NOTHING`. A pending row is processed by re-reading the source, so one pending
   row per source is enough. The migration first collapses existing duplicate pending rows
   (keeps the oldest per source, marks the rest `skipped`) so the unique index can be built.
2. Update events queue only when an embedded column changed (per-model field lists, the Project
   listener's `_changed` pattern).
3. Order Tracking import queues only orders whose embedded fields changed.
4. Line-level types (`inbound_shipment_line`, `order_line`, `picking_line`): evidence + proposal
   only, not removed without crew OK.
5. Poll index `ix_embedding_queue_pending_poll` on
   `((CASE WHEN source_type = 'mcp_tool' THEN 0 ELSE 1 END), created_at) WHERE status = 'pending'`;
   the poll's ORDER BY is the same expression. The `count(*)` is dropped from the poll.
6. `EMBEDDING_QUEUE_BATCH_SIZE` setting (default 10) and a scheduled prune of `completed` /
   `skipped` rows older than 14 days, deleted in small batches.

## Tests

`tests/test_embedding_queue_dedupe.py` (Postgres): dedupe on repeated enqueue, no-op update queues
nothing, embedded change queues one row, import queues only changed orders, poll uses the batch
size and ordering, prune removes only old terminal rows.
