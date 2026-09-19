# PLAN - AutoCount pull + review (products and stock balance)

Status: in progress (2026-09-20, owner reviewed the plan page, rulings P11 to P13, "ok all good"; unattended build to a DRAFT PR authorised, no merge, no deploy)
UAC: `documentation/plans/autocount/autocount-pull-review-acceptance-criteria.md`
Branch: `feat/autocount-pull-review` (one lane, one PR; SR0 #1041 merges first)
Cross-repo contract: FoundryX plan 10 Appendix A1 to A10; fixtures `10-fixtures/` (commit 3deac4f7 in
`foundryx-shared-service`, branch `sprint-5/10-autocount-pull-review`)

## Journey

See the UAC. One sentence: the checker clicks Pull instead of uploading a file, reviews the pull on
three tabs (Changes, Excel view, Compare with my Excel), and Confirm applies it through the same
services the push and the manual stock upload use.

## Measured facts the design rests on (origin/main 1316bcd77, prod copy 0918)

- `import_jobs.job_type` is a free string and `metadata` is JSONB (`app/models/job.py:39,77`).
  `JobStatus` is a native PG enum of six values; `JobService.create_job` creates `pending` without
  enqueueing (`job_service.py:125`); `update_job_with_rq_id` only promotes pending to queued.
- The orphan sweep reads `queued` and `started` rows only (`scheduler/task_scheduler.py`
  `_reconcile_orphan_import_jobs`), so a long-lived `pending` pull is never failed by it.
- Every job route refuses a job the caller does not own (`api/v1/system/jobs.py:176-197`); the jobs
  list page is superadmin only; the detail page has no gate of its own and one action (Cancel).
- The generic job status hook polls every 2 s while pending, queued or started
  (`import-jobs/hooks/useImportJobs.ts:41-54`).
- `MasterIngestService.ingest(entity, records, *, dry_run=False)` (`master_ingest_service.py:687`):
  a dry run is a real run rolled back in a `finally`; `RecordResult.diff` exists only on a dry run;
  the service never stamps `created_by` / `updated_by` (the Excel path does,
  `product_service.py:1786,1859`). Constructor needs keyword `company_id`.
- Excel Desc 2 rule: `product_service.py:1647-1650` (raw truthiness, f-string join, `.strip()`).
- `bulk_import_stock(stock_data, user_id, validate_only=False, outcome=None)`
  (`inventory_service.py:1648`): resolves warehouses by code then name with NO active filter; zeroes
  every pair of an ACTIVE warehouse absent from the payload (:2086-2103, applied :2251-2277); a
  negative quantity lands as 0; unknown product is skipped with `PRODUCT_NOT_FOUND`.
- The Stock List attachment is written only by the browser
  (`StockBalanceGrid.tsx:226-243` -> `POST .../attachments/replace-latest-stock-list`,
  `api/v1/resources/attachments.py:1146-1280`); the chatbot and MCP read it
  (`inventory_service.py:2446-2490`, `mcp_tool_capability_service.py:585`).
- Neither Import button is permission gated in the FE; the stock route needs
  `inventory.stock.import`, the product route needs only a login. `master_data.products.import`
  exists in the registry (`rbac/permission_registry.py:194`).
- Single-company guard to copy: `api/v1/scm/outstanding_import.py:57-79 _require_single_company`.
- Outbound HTTP convention: sync `httpx.Client(timeout=...)` per call
  (`services/integration_service.py`, `services/webhook_service.py`); settings in
  `app/config.py:42 Settings`.
- xlsx builder + bytes response pattern: `project_so_delta_service.py:1042`,
  `api/v1/projects/sales_orders.py:936-954`, `app/utils/http.py:23 content_disposition`.
- Alembic head: `521_sales_report_month_fix`. Permission seed pattern:
  `alembic/versions/505_import_field_aliases_perms.py` (`_insert_permission`, `_sweep`).
- `companies.code` is SRT and MCH; `autocount_ref` is empty for both in prod.

## Design

### No staging table, two job rows per pull (P1, P2)

The snapshot is immutable on FoundryX for 24 h, so Sorento stores only its id. A pull is an
`import_jobs` row; Confirm creates a second one. No new status, no enum migration, no new table.

| Row | `job_type` | Lifecycle |
| --- | --- | --- |
| pull | `autocount_products_pull`, `autocount_stock_pull` | `pending` while FoundryX builds (no RQ job), then the preview task runs it `queued` -> `started` -> `finished` (or `failed`) |
| apply | `autocount_products_apply`, `autocount_stock_apply` | created by Confirm, ordinary `queued` -> `finished` |

Pull job `metadata`:

```json
{
  "autocount_pull": {
    "entity": "products",
    "company_code": "SRT",
    "snapshot_id": "8f1e...",
    "phase": "building | previewing | review | confirmed | failed | expired",
    "progress": {"pagesDone": 2, "pagesTotal": 4, "stage": "lookup:uom"},
    "header": { "...the FoundryX ready header, minus excludedRows and negativePairList; display only, the preview/apply task never reads it back..." },
    "counts": { "received": 0, "new": 0, "changed": 0, "unchanged": 0, "failed": 0,
                "left_out": 0, "price_to_zero": 0 },
    "confirm_blocked_reason": null,
    "compare": { "filename": "...", "compared_at": "...", "total": 0, "matched": 0,
                 "different": 0, "only_in_excel": 0, "only_in_pull": 0,
                 "qty_total_excel": null, "qty_total_pull": null },
    "apply_job_id": null,
    "warnings": []
  }
}
```

`warnings` is a list of string codes set by the preview/apply task; currently only
`content_hash_mismatch` (A5 recheck disagrees with the header, never a refusal). Absent or
empty means a clean match.

Stock `counts`: `received`, `fed`, `not_applied_inactive`, `not_applied_unknown`, `qty_changes`,
`set_to_zero`, `skipped_product_not_found`, `negative_in_autocount`.
Apply job metadata: `{"autocount_apply": {"pull_job_id": "...", "snapshot_id": "...", "entity": "..."}}`.

### Routes (new router `app/api/v1/integrations/autocount_pull.py`, prefix `/api/v1/autocount/pulls`)

| Route | Does |
| --- | --- |
| `POST /` `{entity}` | permission of the entity, single-company guard, reuse an open pull else FoundryX `POST /snapshots`, create the pending row. Returns `{job_id, phase}`, `job_id` is the `import_jobs.id` (never the RQ `job_id` column) |
| `GET /current?entity=` | the caller's own open pull for the active company + entity, else 404. Carries no permission check of its own: it can only ever return a pull the caller already owns, so there is nothing a permission gate would additionally protect |
| `GET /{job_id}` | owner only (404, not 403, for a job that exists but is not the caller's - existence is never revealed). While `building`: passthrough to FoundryX status, stores progress, on `ready` stores the header (display only, see Tasks) and enqueues the preview ONCE (conditional UPDATE on phase), on `failed` fails the job, past 60 min expires it. Always returns phase, progress, header facts, counts, compare summary, confirm_blocked_reason, apply_job_id, warnings |
| `GET /{job_id}/rows?page&limit&query` | Excel view rows, mapped from the snapshot page(s) |
| `GET /{job_id}/download.xlsx` | Excel view as a file (stock: the Stock List file) |
| `POST /{job_id}/compare` `{filename, rows}` | advisory compare, stores the summary only, returns summary + differences |
| `POST /{job_id}/confirm` | guards, creates + enqueues the apply job once, marks the pull confirmed |

Entity to permission: `products` -> `master_data.products.autocount_pull`, `stock_balances` ->
`inventory.stock.autocount_pull`; every route resolves the pull first and checks the permission of
ITS entity, except `GET /current` (above). Ownership reuses the jobs rule (P12).

Excel view paging: FoundryX pages are 1000 rows with stable ordering, so Sorento page N of size L maps
to FoundryX page `ceil` arithmetic with `pageSize=1000`; `query` (item code contains) and the stock
FED filter need the whole set, so for those the route pages the full snapshot (12 to 13 requests, a
database read on the FoundryX side) and filters in memory. Simplest thing that works; no cache. If
that proves slow in the browser pass, the named fallback is to cache the assembled rows in Redis under
the snapshot id for the snapshot's remaining life.

### FoundryX client (`app/services/foundryx_autocount_client.py`)

One small class, sync `httpx.Client`, `timeout=15` for build and status, `30` for a rows page. Methods
`build(company_code, entity)`, `status(snapshot_id)`, `rows_page(snapshot_id, page)`,
`all_rows(snapshot_id)` (pages until `totalPages`). Errors become one `FoundryxPullError(code,
message, status)`; the code is FoundryX's own stable code or `UNREACHABLE` / `NOT_CONFIGURED`. The key
is read from settings, sent only as `X-API-Key`, never logged. Settings: `foundryx_base_url`,
`foundryx_api_key` (`FOUNDRYX_BASE_URL`, `FOUNDRYX_API_KEY`) in `app/config.py`. Tests inject an
`httpx.MockTransport` that serves the committed fixtures (copied into
`sorento_crm_backend/tests/fixtures/autocount_pull/`).

A5 contentHash rule, implemented in `app/tasks/autocount_pull_tasks.py` (`_content_hash`): sha256 over
the concatenation, page-then-row order, of `json.dumps(row, sort_keys=True, separators=(",", ":")) +
"\n"` per row, utf-8. A mismatch against the fetched header's `contentHash` never refuses; it appends
the string code `content_hash_mismatch` to `metadata.autocount_pull.warnings` and logs a warning that
never includes row content.

### Tasks (`app/tasks/autocount_pull_tasks.py`, queue `imports`, `job_timeout=3600`)

Both tasks re-fetch the snapshot header ONCE at their own start, through the shared
`fetch_verified_snapshot(client, snapshot_id, company_code)`: `client.status(snapshot_id)`, then every
row via `all_rows`, then the AC-PP-1 guards (`complete`, assembled row count vs the header's
`recordCount`, `companyCode`) and the A5 contentHash check, all against THAT fetch. The header the
route stored on the job (`pull["header"]`, stripped of `excludedRows` / `negativePairList`, AC-BD-2)
is for the review page only and is never read back by a task - `excludedRows` itself, like every other
guard input, comes from the fresh fetch. FoundryX answering anything other than `ready` for the
snapshot (including 404 `UNKNOWN_SNAPSHOT` / 410 `SNAPSHOT_EXPIRED`) fails the job with a "pull again"
message, the same as a failed guard.

- `preview_autocount_pull(db_job_id)`: company scope from the job (`_apply_import_job_scope`),
  `fetch_verified_snapshot`, then
  - products: `MasterIngestService(db, company_id=...).ingest("products", rows, dry_run=True)`; map
    records to `import_job_rows` through `ImportOutcome` (updated + empty diff = unchanged = no row);
    excluded rows from the FETCHED header become `skipped` / `AUTOCOUNT_EXCLUDED`.
  - stock: classify rows by warehouse (one query for the company's warehouses, match on
    `upper(btrim(code))`), `bulk_import_stock(fed, user_id, validate_only=True)`, plus one query of
    current on hand for the fed pairs to list quantity changes.
- `apply_autocount_pull(db_job_id)`: `fetch_verified_snapshot` again (AC-PC-2: same guards, same
  snapshot), then
  - products: `MasterIngestService(db, company_id=..., stamp_user_id=<confirming user>)
    .ingest("products", rows)`.
  - stock: `bulk_import_stock(fed, user_id, outcome=...)`, then build the Stock List xlsx from the
    fed rows and archive it through the shared service function. The archive happens only after the
    import committed.

`stamp_user_id` is ONE optional keyword on `MasterIngestService.__init__`; when set, `_insert` for
products sets `created_by` + `updated_by` and `_update` sets `updated_by`. Push passes nothing.

### Stock List archive (P7)

Move the body of `replace_latest_stock_list` (archive every live Stock List attachment, upload the new
one through the storage router) into `app/services/stock_list_archive_service.py
replace_latest_stock_list(db, *, file_bytes, filename, user_id)`. The route keeps its macro-strip step
and calls it; the apply task calls it with the generated xlsx. No behaviour change on the route.

### Compare (P11)

`app/services/autocount_pull_compare.py`, two pure functions over lists of dicts, no database:
`compare_products(excel_rows, pull_rows)` and `compare_stock(excel_rows, fed_rows)`. The Excel-side
normalisation CALLS the manual import's own helpers where they are importable (Desc 2 join, price
clamp, Is Active parse) so the two cannot drift; if a rule lives inline in `bulk_import_products`,
lift it into a small function there and call it from both. Differences are returned to the browser
and never stored; only the summary goes into the metadata.

### Frontend

Layering as `PRINCIPLES.md`: UI -> hooks -> service -> `lib/api-client`.

- `app/(protected)/system-management/import-jobs/autocount-pull/` (new folder beside the page):
  `services/autocountPullService.ts`, `hooks/useAutocountPull.ts` (start, current, status with the
  10 s poll, rows via `buildDataGridParams`, compare, confirm), `components/AutocountPullReview.tsx`
  (header facts, counters, line tabs), `PullChangesTab` (wraps the existing `ImportJobRowsCard`),
  `PullExcelViewTab` (DataGrid, fixed layout, resizable), `PullCompareTab` (file drop, summary
  alert, differences grid, xlsx download through `lib/excel-utils`).
- `import-jobs/[id]/page.tsx`: when `job_type` starts with `autocount_` and ends `_pull`, render
  `AutocountPullReview` above the existing cards and skip the 2 s status poll while building; every
  other job type is untouched. Status pill through `Badge`. No UUIDs, no explanatory copy on screen.
- `ProductsList.tsx` and `StockBalanceGrid.tsx`: one more `secondaryActions` entry, gated by
  `useHasPermission`, label from `useCurrentPull(entity)` ("Pull from AutoCount" / "Review pull").
- File reading for Compare: the reader `TemplateUploadDialog` already uses, lifted to a shared helper
  only if it is not already importable.

Phase 1 mocks the service layer against the committed fixtures (a `?mock` free switch is NOT built;
the mock lives in the service module behind the existing Phase 1 convention and is deleted in SR2).

### Migration and permissions (P10, P13)

`522_autocount_pull_perms.py` on top of `521_sales_report_month_fix`: insert the two slugs, sweep
each from its import sibling (integration roles excluded), grant admin. Same helpers as 505.
Registry entries in `permission_registry.py`. Reparent with `./scripts/alembic-reparent.sh` at the
pre-PR gate.

## Slices

| Slice | Content | Tests first |
| --- | --- | --- |
| Phase 1 | Both screens and all three tabs against fixtures, button states, error toasts | none yet (repo rule) |
| SR1 | client, settings, migration, start / current / status routes, products preview task | AC-PL-2..7, AC-BD-1..5, AC-BD-7, AC-PP-1..6, AC-PM-1..2, AC-T-2 |
| SR2 | wire the FE to SR1, remove the mock | AC-PL-1, AC-PL-5, AC-BD-6, AC-RV-1, 2, 4, 6 |
| SR3 | rows + download routes, compare (products), confirm + apply (products), stamping, parity | AC-RV-3, 5, AC-CM-1..6, AC-PC-1..5 |
| SR4 | stock preview, compare (stock), confirm + apply, Stock List archive service | AC-SP-1..5, AC-SC-1..4, AC-CM-3 |
| Phase 3 | reviewer + security-reviewer (external HTTP client, secret handling, new routes, ownership) + browser AC-PC-6, AC-SC-5, in parallel, once | |

One `tester` writes the red tests per slice before the one `coder` (kept alive for the lane) makes
them green.

## Local stack for the browser pass

Backend + worker + FE from this worktree on the lane slot, DB a prod copy. The permission rows are
applied to the shared prod copy by running the migration's own idempotent INSERTs without stamping
alembic there (the shared copy is used by other lanes). FoundryX is a fake: a 40 line FastAPI app
under `sorento_crm_backend/tests/support/fake_foundryx.py` serving the fixtures, started only for the
browser pass, `FOUNDRYX_BASE_URL` pointed at it with a dummy key. The live rehearsal against the
FoundryX lane (:8009) waits for their gateway (their S4) and for the owner to place a real key.

## Accepted consequences and risks

- Preview and apply can differ when Sorento data changes in between; the apply job's rows are the
  record. The snapshot itself cannot change.
- A dry run over about 11,840 products takes one savepoint per record. Measured in SR1 on the prod
  copy; if it approaches the 3600 s job timeout the preview runs the ingest in chunks of 1,000
  inside the one task.
- The first SRT products pull needs SR0 live, else about 9,067 records fail as reference conflicts.
- Excel view search and the stock FED filter page the whole snapshot per request (see Routes).
- The pull page is reachable by its owner only; a non-superadmin reaches it from the button and the
  toast, never from the jobs list.
- `last_synced_at` on a code-wins product reference does not move (SR0 consequence); the review page
  shows no "last synced".
- Worker restart needed after deploy (new tasks). New env on prod: `FOUNDRYX_BASE_URL`,
  `FOUNDRYX_API_KEY`, placed by the owner.

## Definition of Done

1. Mock to real: the Phase 1 mock is deleted in SR2; grep proves no fixture import remains under
   `sorento_crm_frontend/app`.
2. Backfill: none.
3. New permission: two slugs, migration + registry + FE gate + route gate, AC-PM-1..2.
4. New column: none.
5. User's perspective: recorded browser run of AC-PC-6 and AC-SC-5 at 375px and 1280px.
6. User guide: `guide-writer` adds the pull flow to the master data and inventory guides.

## Files

Backend: `app/config.py`, `app/services/foundryx_autocount_client.py` (new),
`app/services/autocount_pull_service.py` (new: start, status, rows mapping, confirm),
`app/services/autocount_pull_compare.py` (new), `app/services/stock_list_archive_service.py` (new,
moved code), `app/tasks/autocount_pull_tasks.py` (new), `app/api/v1/integrations/autocount_pull.py`
(new) + mount in `app/api/v1/__init__.py`, `app/services/master_ingest_service.py` (`stamp_user_id`;
SR1 also fixed `_value_changed` to stringify a `uuid.UUID` before comparing - a raw `text()` SELECT
hands back a native UUID for any postgres `uuid` column regardless of the ORM's own `as_uuid=False`,
so an unchanged foreign key was reported as a diff on every dry run),
`app/services/import_outcome_codes.py` (new codes), `app/api/v1/resources/attachments.py` (call the
moved function), `app/rbac/permission_registry.py`, `alembic/versions/522_autocount_pull_perms.py`,
`worker.py` only if task modules are registered by name there.
Frontend: the files named under Frontend above.
Tests: `tests/test_autocount_pull_*.py`, `tests/fixtures/autocount_pull/*.json`,
`tests/support/fake_foundryx.py`; vitest beside each new component and hook.
