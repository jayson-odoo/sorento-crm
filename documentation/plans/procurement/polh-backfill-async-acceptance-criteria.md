# UAC: polh_0001 backfill out of the deploy migration (lane POLH-BACKFILL-ASYNC)

Plan: `PLAN-polh-backfill-async-05nov.md`.

1. `alembic upgrade head` from `oiod_0001_backfill` writes no `scm.po_line.book_so_seen` row and finishes
   in under 60 s on a copy holding prod-clone volumes.
2. After the backend starts, a background process seeds one `scm.po_line.book_so_seen` event per PO line
   with a `from_so_line_ref` and no S/O link event, with the same columns, `changed_at` rule (earliest
   AutoCount claim read as Malaysian time and stored as UTC, else the line's `created_at`) and
   description the migration wrote.
3. Each batch commits on its own: a run that dies part-way keeps the batches it finished, and the next
   run seeds only the rest.
4. A second run seeds nothing.
5. Two backends starting together: only one runs the backfill; the other logs and exits.
6. The process never exits non-zero and never delays the health check.
7. While it runs, a PO line not yet seeded shows its S/O number with no history popover, as before the
   release.
