# UAC - AutoCount pull + review (products and stock balance)

Plan: `documentation/plans/_archive/autocount/PLAN-autocount-pull-review.md`
Slices SR1 to SR4 of the AutoCount pull + review work. SR0 (contract 2.4, #1041) is its own PR.
Owner rulings R1 to R11 confirmed 2026-09-20. Plan review rulings the same day: P11 (three tabs,
compare is advisory), P12 (the same person pulls and confirms), P13 (the new permissions go to every
role that already holds the matching import permission).
Cross-repo contract: FoundryX plan 10, Appendix A1 to A10
(`foundryx-shared-service`, `documentation/plans/sprint-5/10-autocount-pull-review.md`), fixtures in
`documentation/plans/sprint-5/10-fixtures/`.

## Journey

Actor: the Sorento checker, a staff member who today exports items and stock from AutoCount, runs the
macro workbook and uploads the result through Import.

1. With ONE company selected, the checker opens Products (or Stock Balance) and clicks
   **Pull from AutoCount**, next to Import. No file is chosen.
2. Sorento asks FoundryX to build a frozen snapshot of that book. The checker lands on the pull's
   page and sees it building, with a progress bar when FoundryX reports one. A Mocha build can take
   half an hour. The checker may leave; coming back, the button reads **Review pull** and opens the
   same pull.
3. When the snapshot is ready, Sorento reads it and works out what Confirm would do. Nothing in
   Sorento has changed yet.
4. The checker reviews on three tabs:
   - **Changes**: what Confirm will do (new, changed field by field, failed, left out by AutoCount;
     for stock: quantities that move, pairs set to 0, rows not applied and why).
   - **Excel view**: the whole pull laid out exactly like the manual template, same columns in the
     same order, to read side by side with the macro workbook. Downloadable as xlsx.
   - **Compare with my Excel**: the checker drops the very file they would have uploaded by hand.
     Sorento lines it up with the pull and answers either "100% match" or the list of differences.
     The answer stays on the page beside Confirm. It never blocks Confirm.
5. The checker clicks **Confirm**. Sorento re-reads the SAME snapshot, re-checks the guards and
   applies it: products through the ingest service, stock through the same import the manual upload
   runs, fed only rows for warehouses active in Sorento. A stock Confirm also saves the applied rows
   as the latest Stock List attachment, so the chatbot keeps answering from a current file.
6. The pull's page links to the apply job, which shows the real outcomes. The existing "import
   completed" notification reaches the checker. Nobody else is told anything.

Manual Import stays exactly as it is, as the fallback.

## Acceptance criteria

`[BE]` = pytest on Postgres through the real route or service, seeding its own chain, FoundryX
replaced by a fake transport serving the committed fixtures. `[FE]` = vitest. `[E2E]` = recorded
agent-browser run on the dev server, entered by sidebar clicks, at 375px and 1280px.

### Pull button and starting a pull

- **AC-PL-1 [FE]** Products list and Stock Balance grid show **Pull from AutoCount** beside Import
  only when the user holds `master_data.products.autocount_pull` / `inventory.stock.autocount_pull`.
- **AC-PL-2 [BE]** `POST /api/v1/autocount/pulls {entity}` without the entity's permission is 403.
  With more than one company in scope it is 400 with the same single-company message the order book
  upload uses, and no job row is created and FoundryX is not called.
- **AC-PL-3 [BE]** A successful start calls FoundryX `POST /snapshots` with
  `{"companyCode": <companies.code>, "entity": "products"|"stock_balances"}` and header `X-API-Key`,
  creates ONE `import_jobs` row (`job_type` `autocount_products_pull` or `autocount_stock_pull`,
  status `pending`, `company_id` the active company, `user_id` the caller, metadata holding
  `snapshot_id`, `entity`, `company_code`, `phase: "building"`), and returns its id.
- **AC-PL-4 [BE]** While the caller has an open pull for the same company and entity (phase
  `building`, `previewing` or `review`, not expired, not confirmed), a second start returns THAT job
  and makes no FoundryX call. `GET /api/v1/autocount/pulls/current?entity=` returns it, else 404.
- **AC-PL-5 [FE]** With an open pull the button reads **Review pull** and navigates to it.
- **AC-PL-6 [BE]** FoundryX error ladder on start, each mapped to a stable Sorento error the FE
  toasts, with no job row left behind: 409 `PULL_NOT_ENABLED`, 409 `PUSH_ACTIVE`, 429
  `TOO_MANY_BUILDS`, 401/403/404 (one "connection is not set up" message; the API key never appears
  in a response or a log line), transport failure or timeout.
- **AC-PL-7 [BE]** `FOUNDRYX_BASE_URL` or `FOUNDRYX_API_KEY` unset: start answers the same
  "connection is not set up" error and calls nothing.

### Building, without holding a worker

- **AC-BD-1 [BE]** `GET /api/v1/autocount/pulls/{job_id}` on a building pull fetches FoundryX
  `GET /snapshots/{id}` and returns `phase`, and `progress {pagesDone, pagesTotal, stage}` when
  FoundryX sent one. No RQ job exists for the pull during this phase.
- **AC-BD-2 [BE]** When FoundryX answers `ready`, the header facts are stored in the job metadata,
  the preview task is enqueued EXACTLY ONCE on the `imports` queue and the phase becomes
  `previewing`. Two concurrent status reads enqueue one task (row lock or conditional update).
- **AC-BD-3 [BE]** FoundryX `status: "failed"` sets the job `failed` with the error code and message
  (`SOURCE_PAGE_FAILED`, `ENRICH_FAILED`, `EMPTY_EXTRACT`, `ROW_LIMIT`, `BUILD_ABANDONED`; an
  unknown code is shown as is).
- **AC-BD-4 [BE]** A pull still building 60 minutes after it was created becomes phase `expired`
  (job `failed`, message "pull again"); the status route stops calling FoundryX for it.
- **AC-BD-5 [BE]** A pending pull is never failed by the orphan import job sweep (pinned by a test
  that runs `_reconcile_orphan_import_jobs` over a pending pull older than 3 minutes).
- **AC-BD-6 [FE]** The pull page polls the pull status every 10 seconds while building or
  previewing, shows the progress bar when progress is present and a plain spinner otherwise, and
  stops polling on review, failed or expired. The 2 second generic job poll is not used for a
  building pull.
- **AC-BD-7 [BE]** Only the pull's owner can read it (existing job ownership rule, P12); another
  user holding the permission gets 404.

### Products preview

- **AC-PP-1 [BE]** The preview task pages `GET /snapshots/{id}/rows` until `totalPages`, and refuses
  (job `failed`, reason stored) when: `complete` is false, the assembled row count differs from the
  header `recordCount`, or the header `companyCode` differs from the job's company code.
  `contentHash` is recomputed by the A5 rule; a mismatch is recorded as a warning, not a refusal.
- **AC-PP-2 [BE]** The rows go through `MasterIngestService.ingest("products", rows, dry_run=True)`
  anchored to the job's company. Afterwards no product, reference, embedding queue row or default
  supplier link has changed (row counts and a sampled product compared before and after).
- **AC-PP-3 [BE]** `import_job_rows` for the pull hold one row per product that is `created`,
  `updated` with a non-empty diff (one line per changed field: field, current, incoming), `failed`
  (with the errors) and one row per header `excludedRows` entry (outcome `skipped`, code
  `AUTOCOUNT_EXCLUDED`, its reason and message). An `updated` record with an empty diff writes NO
  row.
- **AC-PP-4 [BE]** Job metadata counts: received, new, changed, unchanged, failed, left out, and
  `price_to_zero` = records whose diff moves `list_price` from a non-zero value to 0. Header
  `zeroListPriceCount` and `negativeListPriceCount` are stored alongside.
- **AC-PP-5 [BE]** With the committed products fixture (10 rows) against an empty company: 10
  created, 0 failed. The MCH row has no `brand_code` key and is created with no brand. Prices arrive
  as JSON strings and land as decimals; `"0.0"` is stored as 0, not treated as missing.
- **AC-PP-6 [BE]** On success the job is `finished` and the phase is `review`.

### Review page (products and stock)

- **AC-RV-1 [FE]** For the two pull job types the import job detail page shows: a status pill
  (Building, Preparing, Awaiting confirm, Confirmed, Failed, Expired), the snapshot time and its
  valid-until time in the header, the counters, three line tabs (Changes, Excel view, Compare with my
  Excel), Download and Confirm. Other job types render exactly as before.
- **AC-RV-2 [FE]** Changes reuses the existing rows card (filters, search, CSV export); a changed row
  shows field, current and incoming.
- **AC-RV-3 [BE]** `GET /api/v1/autocount/pulls/{job_id}/rows?page=&limit=&query=` returns the pull
  in template shape from the snapshot. Products: Item Code, Description, Desc 2, Item Group, Item
  Brand, Price, Is Active, where Description is the row's `name` and Desc 2 is the remainder of
  `description` after `name` (empty when they are equal). Stock: Item Code, Item Description,
  Location, On Hand Qty, FED rows only (AC-SP-2). `query` filters by item code.
- **AC-RV-4 [FE]** Excel view is a DataGrid with those columns in that order, fixed layout,
  resizable, long text truncated with a title, usable at 375px and 1280px.
- **AC-RV-5 [BE]** `GET /api/v1/autocount/pulls/{job_id}/download.xlsx` returns the same rows as one
  sheet with exactly the template's header row (products add a trailing blank UOM column). Stock's
  file is the Stock List file of AC-SC-4.
- **AC-RV-6 [FE]** No UUID is shown anywhere on the page; the snapshot id is not displayed.

### Compare with my Excel (advisory)

- **AC-CM-1 [FE]** The Compare tab reads the chosen file in the browser with the same reader the
  Import dialog uses (xlsx, xls; stock also xlsm, its Template sheet) and posts the parsed rows to
  `POST /api/v1/autocount/pulls/{job_id}/compare`.
- **AC-CM-2 [BE]** Products compare, keyed by Item Code trimmed and case-insensitive: Description
  (file's Description and Desc 2 joined by the manual import's own rule, compared to the pull's
  `description`), Item Group, Item Brand, Price (file's negative read as 0, compared as numbers) and
  Is Active (the manual import's own truthy rule). Result: `matched`, `different` (one entry per
  differing field with both values), `only_in_excel`, `only_in_pull`.
- **AC-CM-3 [BE]** Stock compare, keyed by (Item Code, Location) trimmed and case-insensitive,
  against the FED rows only: On Hand Qty compared as integers, plus the two quantity totals.
- **AC-CM-4 [BE]** A file identical to the pull answers `matched == total`, no differences, and the
  FE shows "100% match" with the counts and the file name.
- **AC-CM-5 [BE]** The summary (file name, time, the four counts, totals) is stored in the pull job's
  metadata and returned by the pull status route; the uploaded rows and the difference list are NOT
  stored. Nothing from the file is applied to any table.
- **AC-CM-6 [FE]** The summary line stays beside Confirm after a reload. The difference list can be
  downloaded as xlsx from the browser. Confirm is enabled with no compare and with differences.

### Products Confirm

- **AC-PC-1 [BE]** `POST /api/v1/autocount/pulls/{job_id}/confirm` by the owner, on a pull in phase
  `review`, creates a SECOND `import_jobs` row (`autocount_products_apply`, metadata pointing back at
  the pull and carrying the same `snapshot_id`), enqueues it on `imports`, and marks the pull
  `confirmed` with the apply job's id. A second Confirm returns the same apply job and enqueues
  nothing.
- **AC-PC-2 [BE]** The apply task re-reads the SAME snapshot and re-checks the AC-PP-1 guards.
  FoundryX 410 `SNAPSHOT_EXPIRED` or 404 `UNKNOWN_SNAPSHOT` fails the apply job with "snapshot no
  longer available, pull again" and changes no product.
- **AC-PC-3 [BE]** It then runs `MasterIngestService.ingest("products", rows)` for real. Per-record
  outcomes are written to the apply job's `import_job_rows`; its counters match the ingest summary.
- **AC-PC-4 [BE]** Products created by a pull Confirm carry `created_by` and `updated_by` = the
  confirming user; products updated carry `updated_by` = that user. A FoundryX PUSH through
  `/external/ingest/products` still stamps neither (unchanged).
- **AC-PC-5 [BE] Parity gate (R10).** The 10 fixture items fed through the manual Excel path
  (`ProductService.bulk_import_products`, template rows) into scratch company X and through the pull
  path into scratch company I give identical `product_code`, `product_name`, `description`, category,
  brand, `list_price`, `is_active`, `is_discontinued`, length, width, height and default supplier
  link for every item. The `****` item is discontinued on both; the dimensions item carries the same
  L/W/H on both; the double-space Desc 2 join is byte-equal on both; the `-1.0` and `0.0` price items
  store 0 on both; the trailing-space code matches on both. Named, asserted differences: the blank
  brand row (Excel clears, pull leaves), UOM (Excel stamps the default, pull leaves it).
- **AC-PC-6 [E2E]** On the lane stack with the fake FoundryX serving the fixture: Products, Pull from
  AutoCount, review shows 10 rows in Excel view, compare a matching file shows 100% match, Confirm,
  the apply job finishes, and the products exist with the confirming user as creator.

### Stock preview

- **AC-SP-1 [BE]** Guards as AC-PP-1, plus refusal of Confirm (not of the preview) when header
  `excludedNonzeroCount > 0`; the page then shows Confirm disabled with that reason.
- **AC-SP-2 [BE]** Every pulled row is classified by its `location_code` matched to
  `warehouses.warehouse_code`, trimmed and case-insensitive, inside the company: FED (warehouse
  active), `not applied, inactive warehouse`, `not applied, unknown location`. Only FED rows ever
  reach `bulk_import_stock`, in preview and in Confirm.
- **AC-SP-3 [BE]** Preview runs `bulk_import_stock(fed_rows, validate_only=True)` and stores its
  summary: would create, would update, would set to 0, would skip. Stock rows are unchanged
  afterwards.
- **AC-SP-4 [BE]** `import_job_rows` for the pull hold: each not-applied row with its reason, each
  would-skip row (product not found), each header `negativePairList` entry, and each FED pair whose
  quantity differs from the current on hand (current, incoming). Counts for all eight counters on the
  page are in the metadata.
- **AC-SP-5 [BE]** Would-skip rows warn and never block Confirm.

### Stock Confirm

- **AC-SC-1 [BE]** Confirm creates the second job (`autocount_stock_apply`) exactly as AC-PC-1 and
  refuses with 409 when a Confirm guard fails (expired, incomplete, count mismatch, company mismatch,
  `excludedNonzeroCount > 0`).
- **AC-SC-2 [BE]** The apply task re-reads the snapshot, re-checks the guards, and runs the same
  `bulk_import_stock` the manual upload runs with the FED rows (columns Item Code, Item Description,
  Location, On Hand Qty). A pair in an ACTIVE warehouse absent from the FED rows is set to 0; a pair
  in an INACTIVE warehouse is untouched, whether or not AutoCount sent it.
- **AC-SC-3 [BE]** The Stock List archive logic is one service function used by BOTH the existing
  `replace-latest-stock-list` route (behaviour unchanged, its tests still green) and the pull
  Confirm.
- **AC-SC-4 [BE]** After a successful stock apply the latest Stock List attachment is an xlsx whose
  rows are exactly the FED rows (including ones the import skipped as product not found), header
  Item Code, Item Description, Location, On Hand Qty; the previous Stock List is archived the same
  way the manual route archives it; `current-stock-list` returns the new one. A failed apply
  replaces nothing.
- **AC-SC-5 [E2E]** Stock Balance, Pull from AutoCount, review counters and Excel view render,
  Confirm, the apply job finishes, the Stock List toolbar link opens the new file.

### Permissions and migration

- **AC-PM-1 [BE]** One migration after the current head adds `master_data.products.autocount_pull`
  and `inventory.stock.autocount_pull`, registered in `permission_registry.py`, idempotent up and
  down, revision id 32 characters or fewer. Each is granted to every role that already holds
  `master_data.products.import` / `inventory.stock.import` (integration roles excluded), plus admin.
- **AC-PM-2 [BE]** Every pull route checks the permission of ITS entity: a user holding only the
  products permission cannot start, read rows of, compare or confirm a stock pull.

### Regression and hygiene

- **AC-T-1 [T]** Existing import job pages, the Excel product and stock imports, their Test flows and
  `replace-latest-stock-list` behave as before; their existing tests are green.
- **AC-T-2 [T]** The FoundryX client sends the API key only in the `X-API-Key` header, to the
  configured base URL only, with a timeout on every call; no test or log output contains the key.
- **AC-T-3 [T]** The worker needs a restart after this lane (new RQ tasks); said in the PR body.

## Out of scope

- SR0 (contract 2.4). A `stock_balances` ingest entity (contract 2.5). The flip to automatic push.
- Anyone other than the puller confirming a pull (P12).
- Making Compare a gate on Confirm (P11).
- Showing unchanged products as rows.
- Fixing the stale stock frozen in inactive warehouses (issue #1042).
- Any change to the manual Import, its dialog or its Test.
