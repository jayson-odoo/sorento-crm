# PLAN — Import job row-level outcome visibility

Status: **Approved — in implementation (through Phase 3).**
UAC: `documentation/plans/imports/import-job-row-outcomes-acceptance-criteria.md`

## 0. Measured baseline (before any change)

Real file: `Order Listing - Macro Version New JULY 2026 24.07.2026 10AM 2PM 5PM.xlsm`
(sheet `Template`, 4,231 data rows, 1,611 doc nos, 1,260 item codes), run through
`process_delivery_order_detail_import` exactly as the worker calls it, against the local
prod-copy DB. Every created row was removed afterwards by id-set diff, so each run starts
from identical state.

| Profile | Outcome mix | Wall clock |
|---|---|---|
| Insert-heavy | 3,452 created · 779 skipped · 0 failed | **4.98s · 6.17s · 6.42s** |
| Duplicate-heavy (the reported screenshot's shape) | 0 created · 4,231 skipped · 0 failed | **6.89s** |

### Result after the change

| Profile | Outcome mix | Before | After | Verdict |
|---|---|---|---|---|
| Insert-heavy | 3,452 created · 779 skipped | 4.98 · 6.17 · 6.42s | **5.25 · 4.91 · 5.75s** | within run-to-run noise |
| Duplicate-heavy | 4,231 skipped | 6.89s | **5.73s** | within noise |
| **Mixed (acceptance run)** | 3,447 created · 779 skipped · **5 failed** | — | **2.92s** | all three outcomes present |

Row capture costs ~5 bulk inserts for 4,231 rows (buffer 1,000), which is why the numbers
do not move. The mixed run is the one that counts (AC-A8): an all-skip or all-fail run is
cheap and would have hidden the cost of writing 3,447 success rows.

The mixed run also proves AC-A10 end to end. Five rows carried a quantity that overflows
`Numeric(15,4)`, so the bulk commit failed; the replay attributed **exactly those five**
and the job still finished with 3,447 successes. Before this change the same file produced
`successful=0, failed=0, skipped=779, status=failed` — counters describing a job that never
happened, and no way to find the offending rows.

What that run revealed about the real data, none of which was visible before:

| outcome | code | count |
|---|---|---|
| created | `created` | 3,447 |
| skipped | `order_not_found` | **751** |
| skipped | `product_not_found` | 15 |
| skipped | `warehouse_not_found` | 13 |
| failed | `row_error` | 5 |

751 rows reference a delivery order that does not exist in the system. That is a data
finding the operator could not previously have made.

Harness: `scratchpad/bench_do_import.py` (insert-heavy) and `bench_do_dup.py`
(two-pass duplicate-heavy). Both must register `register_company_scope_listeners()` — the
worker does this at boot, and without it every owned insert fails on a NULL `company_id`.

## 1. Diagnosis (why the screenshot is blind)

Job `delivery_order_detail_import`: 4231 rows → 203 ok / 0 failed / **4028 skipped**,
**10** reasons listed — so **4,018** skipped rows carry no reason at all.

| Finding | Location | Effect |
|---|---|---|
| Dedup skip records nothing | `app/tasks/import_tasks.py:2406-2409` | 4,018 of the 4,028 skips have **no** row, code, or reason |
| Skips written into the `errors` key | `import_tasks.py:2436` | FE renders `skipped_rows_detail` specially; DO-detail doesn't emit it → falls into the raw JSON dump (exactly the screenshot) |
| Silent truncation | `errors[:100]`, `[-50:]`, `[-200:]` throughout | No "showing 100 of 4028" anywhere |
| Result shape differs per job type | all 9 importers | FE can't render generically |
| Skip vs failure conflated | DO-detail: `failed_rows=0` while the list is titled "errors" | Misleads triage |

Other silent sites found: `import_tasks.py:1918` and `:1926` (GRN lines,
`failed += 1; continue` when the header is missing at group stage) and the
`skipped=len(warnings)` proxy in order-tracking (`import_tasks.py:435`).

### 1.1 Two findings surfaced while benchmarking

**(a) `failed` is effectively unreachable in DO-detail — a bad row kills the whole job.**
The insert loop does `db.add(new_line)` per row and a single `db.commit()` at the end
(`import_tasks.py:2425-2431`). The per-row `except` only catches errors raised while
*constructing* the `OrderLine`; any real DB error (constraint, FK, numeric overflow) surfaces
at commit, so the whole job flips to `failed` and **no** row is identified as the culprit.
Confirmed live: a missing `company_id` auto-stamp raised `NotNullViolation` at commit and the
job reported `successful=0, failed=0, skipped=779, status=failed` — the counters describe a
job that never happened.
→ Plan: keep the single fast commit on the happy path, and on `IntegrityError` **roll back and
replay the batch row-by-row inside savepoints purely to attribute the failure**. Zero cost when
nothing fails; exact `row + code + message` when something does.

**(b) `Total (Ex)` / `Total (Inc)` never map.** The sheet's headers are `Total (Ex)` and
`Total (Inc)`, but the importer looks up `"total excluding tax"` / `"total including tax"`
(`import_tasks.py:2210-2211`), so `total_excluding_tax` / `total_including_tax` are silently
written NULL on every imported line. Out of scope for this plan (it is an import-correctness
bug, not a logging one) — **flagged for a separate decision**, and newly visible once outcomes
carry the row's mapped values.

Per-importer state today:

| Importer | reason for every skip? | success detail? | breakdown? |
|---|---|---|---|
| DO detail | **no** | no | no |
| GRN lines | partial | yes (`successful_rows_detail`) | no |
| GRN listing | yes | no | no |
| SPO | yes | no | no |
| Order tracking | partial | no | no |
| Product / Stock / Warehouse | errors only | counts only | no |
| Attachment ZIP | free-text strings | yes | collision counters only |

## 2. Design

### 2.1 `import_job_rows` (new table)

| column | type | note |
|---|---|---|
| `id` | UUID pk | |
| `import_job_id` | UUID FK → `import_jobs.id` ON DELETE CASCADE | resolved once at recorder init |
| `row_number` | Integer, null | source row (Excel row / ZIP entry index) |
| `outcome` | String | `created` / `updated` / `unchanged` / `skipped` / `failed` |
| `code` | String | stable taxonomy slug |
| `message` | Text | human sentence |
| `value` | String, null | offending token (product code, doc no, filename) — powers `top_values` |
| `identity` | JSONB, null | business keys of the row (doc no, item code, location, qty…) |
| `entity_type` / `entity_id` | String, null | what got written, when known |
| `created_at` | DateTime | |

Indexes: `(import_job_id, outcome)`, `(import_job_id, code)`, `(import_job_id, row_number)`,
`created_at` (retention sweep). Job-tracking infra like `ImportJob` → **not**
`CompanyScopedMixin`, never auto-filtered.

Volume: the DO macro is ~4.2k rows × 3 uploads/day ≈ 12.7k rows/day ≈ 4.6M/yr → retention
(§2.6) is mandatory, not optional.

### 2.2 `ImportOutcome` recorder — `app/services/import_outcome.py`

```python
class ImportOutcome:
    def __init__(self, import_job_id, *, buffer=1000, max_rows=200_000): ...
    def success(self, *, row=None, code="created", message=None, value=None,
                identity=None, entity_type=None, entity_id=None): ...
    def skip(self, *, row, code, message, value=None, identity=None): ...
    def fail(self, *, row, code, message, value=None, identity=None): ...
    @property
    def counts(self) -> dict: ...     # successful / failed / skipped / processed
    def flush(self) -> None: ...
    def finalize(self, message: str) -> dict: ...   # the result envelope
```

- **Only** way to move a counter (AC-A2). Tasks read `recorder.counts` when calling
  `complete_job`; no local `successful`/`skipped` ints survive.
- **Separate `SessionLocal()`** (AC-A6) so row detail commits independently of the import
  transaction — survives rollback, avoids interfering with the GRN-lines savepoints.
  `set_company_scope(session, None)` (job infra, unscoped).
- **Never a per-row INSERT.** Rows accumulate in a list and are written with a single
  `bulk_insert_mappings` per 1,000-row buffer (and once at `flush()`), so a 4,231-row import
  costs ~5 extra round trips, not 4,231. This is a hard requirement, not a tuning knob (AC-A8).
- **In-memory aggregation**: `Counter[(outcome, code)]` plus `Counter[value]` per code
  (distinct values tracked up to 1,000/code, `top_values` emits 10). Aggregation never
  reads back from the table → exact even when row persistence is capped (AC-A9).
- Every method wrapped best-effort: log + continue, never raise into the import (AC-A7).
- `dry=True` mode for the `validate_*` preview paths: aggregate only, no writes (AC-B6).

### 2.3 Reason taxonomy — `app/services/import_outcome_codes.py`

`{code: label}` constants shared by importers, validators, and the FE labelling:

`missing_doc_no`, `missing_item_code`, `missing_location`, `missing_quantity`,
`invalid_quantity`, `missing_container`, `order_not_found`, `product_not_found`,
`warehouse_not_found`, `grn_header_not_found`, `packing_list_not_found`,
`order_not_in_master`, `duplicate_line`, `unchanged`, `already_received_guard`,
`filename_collision`, `renamed_copy`, `replaced`, `extension_not_allowed`,
`file_too_large`, `not_found_in_zip`, `upsert_error`, `row_error`, `db_error`,
`created`, `updated`.

### 2.4 Result envelope (`import_jobs.result`, every job type)

```json
{
  "message": "Delivery order detail import completed",
  "counts": {"total": 4231, "processed": 4231, "successful": 203, "failed": 0, "skipped": 4028},
  "breakdown": {
    "successful": [{"code": "created", "label": "Order line created", "count": 203, "top_values": []}],
    "skipped": [
      {"code": "duplicate_line", "label": "Identical line already exists on this order", "count": 4017, "top_values": []},
      {"code": "product_not_found", "label": "Product not found", "count": 11,
       "top_values": [{"value": "SRTWC8354-SH-UF-150", "count": 4}, {"value": "SRTWC8354-SH-UF-P", "count": 3}]}
    ],
    "failed": []
  },
  "rows_truncated": false,
  "rows_total": 4231
}
```

Job-specific extras (`allocations_created`, `attachments`, `import_session_id`, …) stay
alongside; the envelope keys are additive so nothing existing breaks.

### 2.5 API — `app/api/v1/system/jobs.py`

- `GET /jobs/{job_id}/rows` — `outcome`, `code`, `q`, `page`, `limit`, `sort`, `dir`.
- `GET /jobs/{job_id}/rows/export` — `StreamingResponse` CSV of the filtered set,
  keyset-paginated generator (AC-D5), `import-job-{job_id}-rows.csv`.
- Same RBAC + module guard as the existing job-detail route.

### 2.6 Retention

- `system_settings.import_job_rows_retention_days`, default 90 — added to **both** the
  settings GET dict builder and `SystemSettingUpdate` (known gotcha: inheriting the field
  is not enough).
- **Scheduled** prune (registered on the existing background scheduler, daily) deletes
  `created_at < now - N days`, keyset-batched. Not an on-demand script — the whole point is
  that it runs without anyone remembering to run it.
- Detail page distinguishes "no rows captured" from "row detail pruned" (AC-F4).

### 2.7 Migration

New `307_import_job_rows.py`. **Open question (§5.1):** the committed alembic head is
`301_promo_expiry_rule_engine`; `302`–`306` (multi-company) are untracked WIP in the
working tree. Chaining onto `306` couples this to unmerged work; chaining onto `301`
forks two heads and needs an `alembic merge`.

## 3. Phased execution (three-phase loop)

### Phase 1 — FE prototype (mocks, no backend)

1. `__mocks__/importJobRows.ts` — a 4231-row-shaped fixture mirroring the real screenshot
   (203 created, 4017 duplicate_line, 11 product_not_found).
2. `OutcomeBreakdownCard` — three groups, reason rows, expandable top values, click-to-filter.
3. `ImportJobRowsCard` — DataGrid (fixed layout, resizable, explicit sizes, truncate+title),
   outcome/reason/search filters, Download CSV button.
4. Wire both into `import-jobs/[id]/page.tsx` behind stubbed hooks; keep the
   `Full result (JSON)` block.
5. Verify via Playwright MCP through the sidebar (System Management → Import Jobs → a job):
   loading / empty / error / data / truncated / pruned states + 375px width.
6. Freeze the API contract at the top of `services/importJobService.ts`.

### Phase 2 — Backend + tests (test-first)

1. **Red first** (tdd skill): AC-G3 regression test — re-upload a DO-detail file, assert
   every skip is attributed and `duplicate_line == N`. It must fail against today's code.
2. Model + migration `307_import_job_rows`, `ImportJobRow`.
3. `import_outcome.py` + `import_outcome_codes.py` (+ unit tests for buffering, cap,
   in-memory aggregation exactness, best-effort swallow).
4. Rewire importers in this order — riskiest/most-reported first:
   DO detail → GRN lines → GRN listing → SPO → order tracking → product → stock →
   warehouse → attachment ZIP. Thread the recorder into
   `bulk_import_products` / `bulk_import_stock` / `bulk_import_warehouses` /
   `import_excel_tracking` as an optional arg (AC-C2).
5. Validators (`validate_spo_import`, `validate_grn_*`) switch to the shared codes in dry mode.
6. Endpoints + schemas; retention setting + prune task.
7. AC-G1 guard test (counter mutation outside the recorder = failure).
8. FE off mocks onto the real hooks/services; vitest + playwright per AC-G5/G6.

### Phase 3 — Review

`/code-review` on the full diff, PR checklist, then PR.

## 4. Files touched

**Backend** — `app/models/job.py` (+`ImportJobRow`), `alembic/versions/307_*.py`,
`app/services/import_outcome.py` (new), `app/services/import_outcome_codes.py` (new),
`app/tasks/import_tasks.py` (all 9 importers + validators),
`app/services/{order,product,inventory}_service.py` (recorder arg),
`app/api/v1/system/jobs.py`, `app/schemas/job.py`, `app/services/system_settings*`,
scheduler prune task, `tests/`.

**Frontend** — `app/(protected)/system-management/import-jobs/[id]/page.tsx`,
`.../components/OutcomeBreakdownCard.tsx` (new), `.../components/ImportJobRowsCard.tsx` (new),
`.../services/importJobService.ts`, `.../hooks/useImportJobs.ts`,
`.../types/importJob.types.ts`, vitest specs, `e2e/`.

## 5. Decisions

1. **Migration chaining — DECIDED:** `307_import_job_rows.down_revision =
   "301_promo_expiry_rule_engine"` (the committed head). This forks a second head against
   the untracked `302`–`306` multi-company stack so this work ships independently; an
   `alembic merge` migration reconciles the two heads when multi-company lands.
   Deploy guard: `alembic heads` must be re-checked before any deploy that carries both
   chains (known gotcha — a dual head fails `upgrade head` at revision resolution).
2. **Success rows — DECIDED:** capture **every** row, successes included. Full symmetry —
   "was line X imported?" is always answerable from the table. Makes retention (§2.6) load-
   bearing rather than housekeeping; `max_rows` (AC-A9) stays as the runaway backstop.
3. **Retention default — 90 days**, DB-configurable. Reassess once real volume is observed
   (successes included, the DO macro alone is ~12.7k rows/day).
4. **Identity payload — bounded**: the row's mapped business columns only (doc no, item
   code, location, qty, unit price, filename, …) — not an arbitrary full-row blob. Answers
   "what was in that line?" without unbounded JSONB growth.
5. **Back-compat — keep** `skipped_rows_detail` / `successful_rows_detail` / `errors` in
   `result` for one release alongside the new envelope; the FE reads the envelope, the old
   keys are removed in a follow-up once nothing else reads them.

### Working-tree caveat

The tree currently carries the uncommitted multi-company change set (~40 files) plus
untracked migrations `302`–`306`. This work must be committed **selectively** (only the
files listed in §4) so it stays independently shippable, per decision 1.
