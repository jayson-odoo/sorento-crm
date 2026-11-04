# PLAN: move the polh_0001 "first seen" backfill out of the deploy migration (lane POLH-BACKFILL-ASYNC)

Status: Build. Track: small fix (S): release fix, no new revision, no DDL, no auth/RBAC change.
UAC: `polh-backfill-async-acceptance-criteria.md` (alongside).

## Why

Prod deploy run 41872253783 (main 42d1a56c, 5 Nov 01:00 MYT) failed: blue ran
`oiod_0001_backfill -> polh_0001_seen_backfill`, never became healthy inside
`HEALTH_WAIT_TICKS=120` (`scripts/blue_green_deploy.sh:90`, 240 s), was stopped, and the single
migration transaction (`alembic/env.py:119-123`) rolled all five pending revisions back. Prod still
serves 9c6b581e6a. polh_0001 never committed on prod, so it is edited in place.

## Measured (sorento_prod_1020, read-only EXPLAIN ANALYZE, 5 Nov)

- 57,876 PO lines carry a `from_so_line_ref` (152,486 lines); 63,554 `scm.order_link_claim` rows.
- One polh_0001 batch (5,000 lines, the SELECT without the NOT EXISTS, since this copy already holds
  the seen rows): **18.7 s**. 99% is SubPlan 1, the correlated `min(claimed_at)`: a Seq Scan of
  `scm.order_link_claim` per line (5,000 loops x 63,554 rows; there is no index on `po_line_id`).
  12 batches = ~225 s before the inserts, so prod (more rows than the 20 Oct copy) passes 240 s.
- Same batch with the claims pre-aggregated once (`GROUP BY po_line_id`, merge left join): **101 ms**.
- Steady state (every line already seeded, the NOT EXISTS anti join drops all): 0.55 s.
- Other pending revisions on the same copy: tinv_0001 adds a CHECK over 93 `sales.targets` rows;
  cer_0001 creates an empty table + one permission row; ptag_0014 updates 182
  `price_tag_request_lines`, touches 4 `product_tag_template` rows, creates an empty table;
  oiod_0002's `_SWALLOWED` select takes 95 ms (161 candidate rows). None needs moving.

## Architecture

- Layer: service (`app/services/scm/po_link_history.py`) + a start-time background script
  (`scripts/backfill_po_link_seen.py`), the `scripts.ensure_goods_chain_indexes &` pattern
  (`start.sh:44-47`). No worker job: the worker image runs `start.sh` with an override command and
  never reaches the migration block, and one cheap idempotent pass per backend start needs no queue.
- `po_link_history.backfill_seen(db, batch=5000) -> int`: the polh_0001 SELECT moved verbatim (private
  Core `Table`s, so a test's `schema_translate_map` applies and the ORM company-scope filter, which is
  fail-closed with no scope set, never touches it), except the claim time comes from ONE pre-aggregated
  `order_link_claim` subquery joined per batch. Keyset by line id, one INSERT ... SELECT per batch,
  `db.commit()` after each batch, one INFO log line per batch and a total. Resumable: a killed run keeps
  its committed batches, and the next run's NOT EXISTS skips them.
- `scripts/backfill_po_link_seen.py`: one dedicated connection, `pg_try_advisory_lock(<own key>)`; a
  backend that does not get it logs and does nothing (blue and green starting together). Every outcome,
  an import error included, exits 0 (gunicorn reaps it like a worker after `start.sh` execs).
- `start.sh`: `python -m scripts.backfill_po_link_seen &` right after `alembic upgrade head`.
- polh_0001: `upgrade()` does nothing; the docstring points at the script. Revision id and chain stay.

## While the backfill runs (seconds on prod at 101 ms/batch)

Only reader: `latest_by_line` (PO detail `book_so_link`) and the PO History tab. A line not yet seeded
has no event: `BookSoCell.tsx:50` renders no popover, the S/O cell shows the number exactly as before
this release, the History tab lists no seen row. Nothing reads the events as a count or as truth.
Race with the live ingest: a line whose link the ingest moves before the backfill reaches it already
has a change event, so it is skipped (correct: its current ref is no longer the pre-release one).

## Tests (red first)

`tests/test_po_link_history.py` (Postgres, scratch schema):
- the existing backfill tests drive `backfill_seen` instead of the migration;
- the polh_0001 migration inserts nothing;
- `backfill_seen` commits per batch: with batch=1, a failure in batch 2 leaves batch 1's row, and a
  rerun completes the rest (resumable);
- the script does nothing while another session holds its advisory lock, and never raises;
- `start.sh` runs the script in the background after `alembic upgrade head`, before gunicorn.

## Proof

Copy of the clone at `oiod_0001_backfill` (copy built from the relevant tables only: the full clone is
28 GB against 34 GB free): `alembic upgrade head` < 60 s; the script seeds 57,876 rows; a second run
seeds 0.
