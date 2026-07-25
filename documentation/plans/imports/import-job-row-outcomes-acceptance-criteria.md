# UAC — Import job row-level outcome visibility

Status: **Approved — in implementation through Phase 3.**
Scope: every import job type in `sorento_crm_backend/app/tasks/import_tasks.py` (+ the services they call).

Locked decisions: migration `307` chains onto committed head `301_promo_expiry_rule_engine`
(second head, reconciled by an `alembic merge` when multi-company lands) · every row captured
including successes · retention 90 days via a **scheduled** prune · `identity` = the row's
mapped business columns only · legacy `result` keys kept one release.

## Problem statement

`delivery_order_detail_import` of 4231 rows reported `successful=203`, `failed=0`,
`skipped=4028`, and listed **11** reasons. The other **4017 skipped rows recorded nothing**
(`import_tasks.py:2406` bumps `skipped += 1` on the dedup path with no reason, no row,
no code). The operator cannot answer "what was skipped, and why?" — the central complaint.

The same class of blindness exists across every importer: silent counter bumps, no
aggregation, silent list truncation (`[:100]`, `[-50:]`), and a different `result` JSON
shape per job type so the FE can only dump raw JSON.

---

## A. Row-outcome capture (backend)

- **AC-A1** Every import job persists **one `import_job_rows` row per source row it
  considered**, with `outcome ∈ {created, updated, unchanged, skipped, failed}`, a stable
  `code`, a human `message`, the offending `value` (when there is one), and an `identity`
  JSON snapshot of the row's business keys.
- **AC-A2** It is **impossible to change a counter without a reason**: `successful` /
  `failed` / `skipped` are read from the recorder only. A bare `skipped += 1` /
  `failed += 1` anywhere in the import paths is a test failure (AC-G1).
- **AC-A3** The DO-detail dedup skip (the 4017) is recorded as
  `code=duplicate_line`, message "Identical line already exists on this order
  (same product, warehouse, qty, unit price, discount, total)", with the row's
  doc no / item code / location / qty in `identity`.
- **AC-A4** The GRN-lines grouping-phase silent `failed += 1` (missing header, two sites)
  is recorded as `code=grn_header_not_found`.
- **AC-A5** Successes carry detail too: `outcome=created|updated`, `identity` holding the
  business keys, and `entity_type`/`entity_id` of the row written when known.
- **AC-A6** Row capture uses a **separate DB session** from the import transaction, so a
  rolled-back or crashed import still leaves its per-row diagnosis behind.
- **AC-A7** Row capture never breaks an import: any recorder failure is caught, warned,
  and the import continues.
- **AC-A8** **No per-row INSERT.** Outcome rows are written only via buffered
  `bulk_insert_mappings` (1,000/flush + a final flush). Verified by measuring the real
  4,231-row file (`Order Listing - Macro Version …xlsm`) before and after the change on
  **both** profiles — insert-heavy (3,452 created / 779 skipped) and duplicate-heavy
  (4,231 skipped) — against the recorded baselines in PLAN §0. A run whose rows are
  *all* skipped or *all* failed does not count as proof: the measured run must contain
  successful, skipped **and** failed rows, because success rows are the expensive path.
  Target: ≤10% wall-clock regression.
- **AC-A10** A row that fails at DB level is **named**. The happy path keeps one bulk
  commit; on `IntegrityError` the batch is rolled back and replayed row-by-row inside
  savepoints solely to attribute the failure, so the job reports `failed=N` with the
  offending row numbers instead of collapsing to `status=failed` with zeroed counters.
- **AC-A9** Row persistence is capped (`max_rows`, default 200,000/job). Past the cap,
  rows stop persisting, `rows_truncated=true` is set — **but counts and the aggregated
  breakdown stay exact**, because aggregation is in-memory, not derived from stored rows.

## B. Aggregated breakdown (backend)

- **AC-B1** On completion, `import_jobs.result` carries a uniform envelope for **every**
  job type:
  `{message, counts:{total,processed,successful,failed,skipped}, breakdown:{successful[],skipped[],failed[]}, rows_truncated, rows_total}`.
- **AC-B2** Each breakdown entry = `{code, label, count, top_values:[{value,count}]}`,
  ordered by count desc. `count` is **exact and complete** — never truncated.
- **AC-B3** `top_values` lists up to 10 distinct offending values per code (e.g. the
  actual missing product codes), each with its own count.
- **AC-B4** `counts.successful + counts.failed + counts.skipped == counts.processed`, and
  the sum of every breakdown `count` equals `counts.processed`. Asserted in tests.
- **AC-B5** Reason codes come from one shared taxonomy module — the same code means the
  same thing across importers (`product_not_found` is never spelled two ways).
- **AC-B6** Validation-preview paths (`validate_spo_import`, `validate_grn_listing_import`,
  `validate_grn_lines_import`) emit the **same codes** as the real import, so preview
  matches outcome.
- **AC-B7** Legacy jobs (no breakdown in `result`) still render — FE falls back to the
  existing raw-JSON view without error.

## C. Coverage — all import types

- **AC-C1** Rewired and verified for: `delivery_order_detail_import`, `grn_lines_import`,
  `grn_listing_import`, `spo_import`, `order_tracking_import`, `product_import`,
  `stock_import`, `warehouse_import`, `attachment_bulk_import`.
- **AC-C2** Where the work lives in a service (`bulk_import_products`, `bulk_import_stock`,
  `bulk_import_warehouses`, `import_excel_tracking`), the recorder is threaded in as an
  optional argument; non-job callers keep working unchanged.
- **AC-C3** Attachment ZIP import records per-file outcomes including
  `filename_collision` (skip), `renamed_copy`, `replaced`, `extension_not_allowed`,
  `file_too_large`.
- **AC-C4** Order-tracking records Master-sheet row errors AND the "order not in Master"
  tracking-sheet warnings as skips with codes, plus created/updated successes.

## D. API

- **AC-D1** `GET /api/v1/system/jobs/{job_id}/rows` returns a paginated list filterable by
  `outcome`, `code`, and free-text `q` (matches message / value / identity), sortable by
  row number. Follows the standard list response shape.
- **AC-D2** `GET /api/v1/system/jobs/{job_id}/rows/export` streams CSV of the **filtered**
  set (all matching rows, not a page), filename `import-job-{job_id}-rows.csv`,
  columns: row, outcome, code, reason, value, identity, entity_id.
- **AC-D3** Both endpoints enforce the same RBAC/module guard as `GET /jobs/{job_id}`.
- **AC-D4** Unknown job id → 404; a job with no captured rows → empty list, not an error.
- **AC-D5** Export of a 200k-row job streams without loading all rows into memory
  (keyset-paginated generator).

## E. Frontend — job detail page

- **AC-E1** "Result Details" is replaced by an **Outcome breakdown** card: three groups
  (Successful / Skipped / Failed), each listing `label — count`, expandable to show the
  top distinct values with counts. Raw JSON stays available in the collapsed
  `Full result (JSON)` block.
- **AC-E2** Clicking a breakdown reason filters the Rows grid to that `code`.
- **AC-E3** A **Rows** card renders a DataGrid (`tableLayout: {width:'fixed',
  columnsResizable:true}`, `columnResizeMode:'onChange'`, explicit `size` per column,
  `truncate` + `title` for long text) with columns: Row #, Outcome badge, Reason, Detail,
  Identity. Server-side pagination via `buildDataGridParams`.
- **AC-E4** Filters: outcome select, reason select (populated from the breakdown), search
  box. Filters drive the API, not client-side slicing.
- **AC-E5** "Download CSV" button hits the export endpoint with the active filters.
- **AC-E6** Every section always renders with an explicit empty state (per ADR product
  standards) — never hidden on missing data.
- **AC-E7** No UUIDs shown in the UI: identity renders business keys (doc no, item code,
  location, filename), never raw ids.
- **AC-E8** Loading / empty / error / truncated states all render; when
  `rows_truncated` is true the card says "showing first N of M rows captured".
- **AC-E9** Works at ~375px width (mobile) without horizontal page overflow.

## F. Retention

- **AC-F1** `import_job_rows` older than the retention window are pruned by a scheduled
  job, batched by keyset (no unbounded DELETE).
- **AC-F2** Retention days is DB-configurable (`system_settings.import_job_rows_retention_days`,
  default 90) and appears in both the settings GET builder and the update schema.
- **AC-F3** Pruning removes row detail only — `import_jobs` counts and the stored
  breakdown survive forever.
- **AC-F4** The detail page states when row detail has been pruned rather than showing an
  empty grid that looks like "nothing happened".

## G. Tests

- **AC-G1** pytest guard: scanning the import task/service modules for counter mutations
  outside the recorder fails the suite.
- **AC-G2** pytest per importer: a fixture file producing at least one of every outcome
  asserts exact counts, exact breakdown codes, and AC-B4's arithmetic identity.
- **AC-G3** pytest regression for the reported bug: a DO-detail re-upload of an already
  imported file yields `skipped == N` with **all** N attributed to `duplicate_line` and
  zero unattributed skips.
- **AC-G4** pytest for the API: filtering, pagination, CSV export content, 404, RBAC deny.
- **AC-G5** vitest: breakdown card + rows grid across loading / empty / error / data /
  truncated.
- **AC-G6** playwright: import job detail → filter to skipped → reason chip → grid shows
  matching rows → CSV request fires with the filter params (`browser_network_requests`).
- **AC-G7** Test cleanup is scoped to marker rows only — never an unscoped
  `DELETE FROM import_job_rows` (the local DB is a copy of production data).

## H. Non-goals

- Re-running / repairing skipped rows from the UI (separate feature).
- Changing any import's business behaviour — dedup stays dedup; this work only makes the
  existing outcome legible.
- Backfilling row detail for jobs already completed (impossible; historical jobs keep
  their legacy `result`).
