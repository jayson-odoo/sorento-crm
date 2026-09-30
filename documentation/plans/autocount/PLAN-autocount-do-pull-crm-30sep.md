# PLAN: Delivery Orders, Pull from AutoCount (lane DO-PULL-CRM, BL-SS-286)

Status: **entity built (pull, preview, apply, review reuse, single-file compare); two-file
compare waiting on the owner's mock approval (1.8)** (full track: new permission slug + grant
migration, so not the small-fix track; no new external ingest surface, the apply reuses the
DO ingest). Branch `crew/do-pull-crm` (base `main`, cut at `90807ede`), PR #1383. UAC:
`autocount-do-pull-crm-30sep-acceptance-criteria.md` (AC-DP-01 onward).

Owner ask (30 Sep): the CRM Delivery Orders page (Dashboards > Delivery Orders, Actions menu:
Refresh / Import tracking / Import delivery order lines) gets **Pull from AutoCount** exactly like
Products (`ProductsList.tsx:184`) and Stock Balance (`StockBalanceGrid.tsx:92`):
`useAutocountPullAction` -> `POST /api/v1/autocount/pulls` -> FoundryX snapshot -> preview ->
the owner reviews and confirms. NOT a "run now" of the document feed. The shared-service snapshot
for DOs is lane DO-PULL-SS (its contract is relayed by the orchestrator; section 2 states what
this side assumes until it lands).

Paths: `be/` = `sorento_crm_backend/`, `fe/` = `sorento_crm_frontend/`.

## 0. What already exists (measured on `main` 90807ede)

| Thing | Where | State |
| --- | --- | --- |
| Pull lifecycle (start / current / status / rows / download / compare / confirm / discard) | `be/app/services/autocount_pull_service.py`, `be/app/api/v1/integrations/autocount_pull.py` | Two entities, dispatched by `ENTITY_PERMISSIONS` / `JOB_TYPES` / `APPLY_JOB_TYPES` (`:38-59`) and by `entity_of(job) == "products"` else stock in the four review routes (`:215-271`). |
| Preview / apply tasks | `be/app/tasks/autocount_pull_tasks.py` | `preview_autocount_pull` (`:119`) and `apply_autocount_pull` (`:182`) dispatch on entity and raise `UnsupportedPullEntity` otherwise. `fetch_verified_snapshot` (`:674`) is the shared guard. Outcome rows through `ImportOutcome`. |
| DO ingest | `be/app/services/autocount_doc_ingest_service.py` | `AutocountDocIngestService(db, integration_id, *, company_id, book).ingest("delivery_orders", records, dry_run=)` returns `IngestResult` with per-record `outcome` (`created / updated / unchanged / failed / retryable`), `warnings` (`adopted_by_doc_no`, ...) and `lines` (`created / updated / deleted / adopted / skipped / linked / unlinked`). Adoption by DocNo keeps tracking columns (`_find`, `:580`; `_write_lines`, `:975`); DocKey clash -> `failed` `errors.DocNo` (`:597,602`); unknown product / warehouse -> `retryable` (`_resolve_items`, `:624`). A dry run rolls the session back (`:514`). No progress callback. |
| Review page | `fe/app/(protected)/system-management/import-jobs/autocount-pull/` | `AutocountPullReview.tsx` (phase badge, counters, three tabs), `PullChangesTab` (the generic rows card), `PullExcelViewTab` (columns per entity), `PullCompareTab` (drop a file, server compare). Entity unions and labels are two-valued (`types/autocountPull.types.ts:8`, `AutocountPullReview.tsx:58`, `[id]/page.tsx:33-60,218-228`). |
| Button | `fe/.../products/components/ProductsList.tsx:184,999-1008` | `useAutocountPullAction(entity, slug)` -> a `secondaryActions` entry with `CloudDownload`, shown on `visible`. |
| Permissions | `be/app/rbac/permission_registry.py:201,278`; `be/alembic/versions/522_autocount_pull_perms.py` | One `.autocount_pull` slug per entity, swept onto every role holding the sibling `.import` slug plus `admin`, integration roles excluded. `order_management.orders.import` exists (`:96`). |
| Router gate | `be/app/api/v1/__init__.py:284-289` | `require_any_module_enabled("product", "inventory")`. The orders module key is `order` (`be/app/modules/order/bootstrap.py`). |
| FoundryX client | `be/app/services/foundryx_autocount_client.py` | `build(company_code, entity)`, `status(id)`, `all_rows(id)`; entity is a free string on the wire. |

Nothing here needs a new table, a new route or a new page: the lane is a third entity in the
existing machinery, plus the DO-shaped preview / apply / rows / compare halves.

## 1. Design

### 1.1 Entity `delivery_orders`

| Map | Value |
| --- | --- |
| `ENTITY_PERMISSIONS["delivery_orders"]` | `order_management.orders.autocount_pull` (new registry slug, "Pull Delivery Orders from AutoCount") |
| `JOB_TYPES["delivery_orders"]` | `autocount_delivery_orders_pull` |
| `APPLY_JOB_TYPES["delivery_orders"]` | `autocount_delivery_orders_apply` |
| Router gate | `require_any_module_enabled("product", "inventory", "order")` |
| Migration | `do_pull_0001_perm`: insert the slug if absent, sweep onto roles holding `order_management.orders.import` (integration roles excluded), grant `admin`. Same three statements as 522. |

`start_pull`, `find_open_pull`, `refresh_pull_status`, `advance_building_pulls`, `confirm_pull`,
`discard_pull`, `serialize` and `_resolve_pull` are entity-agnostic already and change nothing.

### 1.2 Snapshot contract this side reads (DO-PULL-SS, relayed 30 Sep)

Contract of record: `foundryx-shared-service` branch `crew/do-pull-snapshot` (28c6f2f7),
`documentation/plans/sprint-5/16-autocount-do-pull-snapshot-contract.md`. Read here from the
orchestrator's relay (this sandbox cannot open that repo); the points this side builds on:

- `POST /api/v1/autocount/snapshots {"companyCode", "entity": "delivery_orders", ...scope}`
  with FLAT optional scope keys `fromDay`, `toDay`, `docNo`; no scope = the last 31 MYT days,
  `docNo` = that one document. Same build / status / rows calls, same `ready` header fields,
  same A5 contentHash rule. Cap 10,000 documents.
- Same scope while a build is in flight re-attaches; a DIFFERENT scope in flight is 409
  `BUILD_IN_FLIGHT`; the build cooldown applies to the same scope only.
- Each row is **the raw vendor DO dict verbatim** plus `source_ref` = `{book}:DO:{DocKey}`
  (the same ref the DO feed and ingest use). The **book is read off the rows' `source_ref`
  prefix** (header `book` accepted first when present); rows naming two books, or none ->
  the preview fails with "AutoCount snapshot names no book; pull again". Rows are handed to
  the ingest as the feed's own push sends them: the vendor record with the snapshot's
  `source_ref` key removed (review S1: the ingest stores and diffs the whole record as
  `source_record`, and the push carries no `source_ref`, so leaving it in would make every
  push-then-pull cycle read as `updated`). No other mapping, one writer.

CRM side of the scope: `PullStartBody` gains an optional `scope: {fromDay?, toDay?, docNo?}`
passed through flat to `client.build` and stored on the pull (`autocount_pull.scope`,
returned by `serialize`); the review header prints it ("Last 31 days" / "1 Sep to 30 Sep
2026" / "DO ZZDO-0001"). The button itself starts with NO scope (the 31-day default),
exactly the products click; a scope picker is new UI and waits for a mock + approval
(crew-ask). `BUILD_IN_FLIGHT` joins the FE start-error map ("Another AutoCount pull with a
different scope is still building. Try again shortly.").

**SO links (orchestrator ruling, 30 Sep, code read of `main` 90807ede):** adoption never nulls
a link (`_changes` skips NULL for `sales_order_id` / `sales_order_line_id`,
`autocount_doc_ingest_service.py:118-122,652-659`); Excel DO lines never had
`sales_order_line_id`; SO outstanding reads `SalesOrderLine.qty_ordered - qty_delivered`, not
DO lines; only sales achievement reads the DO -> SO line link. So: **the apply path is the
ingest as-is**; the review shows `sales_order_unresolved` / `so_line_unresolved` /
`line_without_item` (and `customer_unresolved`, `branch_unresolved`) as WARNINGS on the
record's row, never blockers, plus a `with_warnings` counter; every record row names its
lines created / adopted / updated / deleted. (Prod dry run for scale: `sales_order_unresolved`
435 of 948, `so_line_unresolved` 946 lines.)

### 1.3 Preview (`_preview_delivery_orders`)

1. `fetch_verified_snapshot` (unchanged guards), read `book` from the fetched header.
2. `AutocountDocIngestService(db, None, company_id=job.company_id, book=book).ingest(
   "delivery_orders", rows, dry_run=True, on_progress=...)`. `on_progress` is new on this
   service: the same `PROGRESS_REPORT_EVERY` / `_report_progress` shape `MasterIngestService`
   has (`master_ingest_service.py:823-921`), so the review page shows "N of M" (B3).
3. Per record, in snapshot order:

| Verdict | Counter | `import_job_rows` row |
| --- | --- | --- |
| `created` | `created` | `success`, value DocNo, identity `{doc_no, doc_key, lines}` |
| `updated` with `adopted_by_doc_no` | `adopted` | `updated`, message `DO adopted by number: {DocNo}: keeps tracking, +a lines, ~b, -c` |
| `updated` otherwise | `updated` | `updated`, message `DO updated: {DocNo}: +a lines, ~b, -c` |
| `unchanged` (incl. `stale_ignored`) | `unchanged` | none (AC-PP-3 rule) |
| `failed` | `failed` | `fail`, code = first error key (`DocNo` on a DocKey clash), message = the errors |
| `retryable` | `retryable` | `fail`, code `autocount_retryable`, message = the errors (`Details.N.ItemCode: product 'X' not found`) |

`lines_to_delete` = sum of `lines.deleted` over `updated` records (adopted included): the old
lines the adoption cannot match and the AutoCount lines the document no longer carries.
`received` = `len(rows)`; `with_warnings` = records carrying any warning other than
`adopted_by_doc_no`. Counts stored: `received, created, updated, adopted, unchanged,
lines_to_delete, failed, retryable, with_warnings`. Every record's warnings ride in the row
identity and, human-worded, at the end of its message ("warnings: sales order not found, SO
line not found").

`confirm_blocked_reason` stays `None`: a failed or retryable record is left out by the ingest's
own per-record SAVEPOINT and the rest lands, exactly as a push behaves. Nothing is written by
the preview (the ingest's own dry-run rollback, pinned).

### 1.4 Apply (`_apply_delivery_orders`)

Same `fetch_verified_snapshot`, same `book` rule, then the same service NOT dry-run, then
`db.commit()` (the route's own order: per-record SAVEPOINTs, one commit for the batch,
`ingest.py:937-940`). No GRN receipt hook applies to DOs. Outcome rows are written with the same
three writers as the preview. Apply summary: `{total, created, updated, adopted, unchanged,
failed, retryable, lines_deleted, with_warnings}`. Audit attribution needs nothing new:
`enqueue_job` writes the confirming request's actor onto the RQ job (`queue_service.py:135`)
and the work-horse runs the task inside `job_actor_scope` (`:73`), so the `orders` audit rows
already name the person who confirmed.

### 1.5 Rows, download, compare (the two other tabs)

- **Excel view**: one row per DO line, in the shape of the "Import delivery order lines" sheet
  the checker uploads today (`order_service.validate_delivery_order_detail_excel`: `Doc No`,
  `Item Code`, `Location` are its keys): `doc_no, doc_date, debtor_code, debtor_name,
  item_code, description, location, qty, uom, unit_price, sub_total`. A Details row with no
  ItemCode is left out (it is never a line). Search matches Doc No or Item Code, contains,
  case-insensitive. `map_delivery_order_rows(rows) -> list[dict]` in the pull service.
- **Download**: the same rows as `autocount-delivery_orders-pull.xlsx`, header `Doc No, Doc
  Date, Debtor Code, Debtor Name, Item Code, Description, Location, Qty, UOM, Unit Price, Sub
  Total`, through `_neutralize_formula_cells`.
- **Compare with my Excel**: `compare_delivery_orders(excel_rows, pull_rows)` in
  `autocount_pull_compare.py`, keyed by (`Doc No`, `Item Code`, `Location`) trimmed and
  case-insensitive, `Qty` compared as Decimal; `only_in_*` labels `DOCNO|ITEM|LOC`; summary
  shape unchanged (`qty_total_*` null). The Excel column names accepted are the DO lines
  import's own aliases (`doc no` / `doc number` / `order number`, `item code` / `product code`,
  `location` / `warehouse` / `warehouse code`, `qty` / `quantity`).

The three review routes dispatch on `entity_of(job)` three ways (`products` / `stock_balances`
/ `delivery_orders`) instead of products-else-stock.

### 1.6 Frontend (reuse, no new UI)

Every change is a third value in an existing two-valued switch, so no mockup is owed (the
brief's "genuinely new UI" clause does not fire):

- `AutocountPullEntity` gains `'delivery_orders'`; `DeliveryOrderPullCounts`,
  `DeliveryOrderExcelRow` types.
- `OrdersList.tsx`: `useAutocountPullAction('delivery_orders',
  'order_management.orders.autocount_pull')` and the same conditional `secondaryActions` entry
  as Products, after "Import delivery order lines".
- `[id]/page.tsx`: `AUTOCOUNT_PULL_JOB_TYPES`, `pullEntityFromJobType`, `JOB_TYPE_LABELS`
  ("AutoCount Delivery Orders Pull"), Back button "Back to Delivery Orders" ->
  `/order-management/orders`.
- `AutocountPullReview.tsx`: `ENTITY_LABEL`, `deliveryOrderCounters` (Received, New, Updated,
  Adopted by number, Unchanged, Lines to delete, Failed, Retry later), download label
  "Download xlsx".
- `PullExcelViewTab.tsx`: `DELIVERY_ORDER_COLUMNS` and listing key
  `order_management.orders.autocount_pull::excel-view`; `getRowId` includes doc no.
- `PullCompareTab.tsx` / `compareRows.ts`: listing key `::compare`, a Doc No column and the
  Location column for this entity, only-in labels split on `|`.

### 1.7 Not built, and the trigger

- Start parameters (a date window): the DO-PULL-SS contract naming one.
- A "lines to delete" detail list beyond the per-record row message: the owner asking for it
  after the first hand test.
- A GRN pull: the same lane shape, one more entity, when the owner asks.

## 1.8 Owner decision, 30 Sep: pull-on-request + two-file compare (plan delta)

Relayed by the orchestrator after the entity work above was built:

1. The DO feed stays pull-on-request; Push only after the pull is proven. Nothing in this
   lane changes for that: Confirm applies through the ingest exactly as a push would.
2. Flow: Pull from AutoCount (a DocDate window, the shared-service snapshot) -> the checker
   uploads the TWO macro files used today -> the CRM compares the snapshot against their
   rows -> ideally zero differences -> Confirm as on Products / Stock.
3. The two files (crew subagent, read-only): "Order Listing - Macro Version 2 ... .xlsm",
   sheet `Master` = DO item lines (`Doc No`, `Doc Date`, `Created Time`, `Cancelled`,
   `Item Code`, `Qty`, `Location`, `Unit Price`, `Discount`, `Total (Ex)`, `Total (Inc)`),
   rows selected by DocDate; "9. Macro Version Order Tracking ... .xlsm", sheets `Master` /
   `Raw Data` = one row per DO (`Doc. No.`, `Date`, `Created Time`, `Debtor Code`, `Debtor
   Name`, `Agent`, `Cancel`, `Remarks CS`, `Type`) plus `Overall Tracking` (the delivery
   log). Neither carries an SO reference or a last-modified column.
4. The compare is windowed to the pulled DocDate range (the files hold extra days), keyed by
   DO number + line; a DO missing from the pull is a difference, never a delete.
5. New UI, so a mock first: `documentation/mockups/do-pull/index.html` (this commit), owner
   approval before the compare UI is built.

**Verified importer gap (owner's item 3):** `process_delivery_order_detail_import` reads
headers lower-cased only (`import_tasks.py:2693-2700`) and looks for `total excluding tax` /
`total including tax` (`:2821-2822`), so the sheet's `Total (Ex)` / `Total (Inc)` columns are
never read by the existing DO lines import; `total` (`:2819`) matches neither either. Not
this lane's fix (the pull replaces that upload), recorded for the backlog.

**What changes against sections 1.5 and 1.6, once the mock is approved:**

- Start: `PullStartBody.scope` (built, 1.2) is what the new dialog posts (`fromDay` /
  `toDay`); the button opens the dialog for a delivery-orders pull, a plain click for the
  other two entities. `find_open_pull` still reuses the open pull.
- Compare route: `POST /{job_id}/compare` grows an optional `source` (`lines` = Order
  Listing `Master`, `headers` = Order Tracking `Master`) and windows both sides to the pull's
  `scope` (default window = the snapshot header's own `fromDay` / `toDay` when it carries
  them, else `extractedAt` minus 31 days to `extractedAt`). Lines compare stays keyed by
  (Doc No, Item Code, Location); a headers compare is keyed by Doc No. Field lists per
  Q3 below. The stored summary carries both sources.
- Compare tab: two dropzones, one headline, one grid grouped by source, "Only in your
  Excel" rows for DOs the pull did not bring back. `Overall Tracking` is not compared (Q6).
- The single-file compare built in this commit (`compare_delivery_orders`, Qty only) stays
  the lines half of the above; nothing of it is thrown away.

**Open product questions (recommendation in bold):** Q1 default window: **last 31 days,
prefilled**. Q2 per-document pull on the dialog: **no**. Q3 difference fields: **lines: Qty,
Unit Price, Discount, Total (Ex); headers: Doc Date, Debtor Code, Cancel; not compared:
Created Time, Debtor Name, Agent, Total (Inc)**. Q4 Confirm with differences: **allowed,
advisory (P11), the headline says the differences change nothing**. Q5 a DO only in
AutoCount still lands on Confirm: **yes**. Q6 `Overall Tracking` not compared: **yes, the
tracking upload stays the writer for those columns**.

## 1.9 Phase 3 security review (30 Sep, on 69c1f263) and what changed

Verdict "needs work", one blocker, all taken in the fix round (`TestSecurityFixRound`):

- **B1** the DO compare parsed a quantity into an unbounded `Decimal` and called `int()` on
  it; `"1e3000000"` pinned the API process under the GIL. Now bounded (`_MAX_QTY_EXPONENT`
  15, finite only), anything past it reads as 0.
- **S1** the entity permission check never looked at the module guard, while the router gate
  passes when ANY of product / inventory / order is enabled. `_require_entity_permission` now
  runs the same module check `dependencies.require_permission` runs (strict mode, admin and
  superadmin bypass). Products and stock gain the same check.
- **S2** the job rows CSV export wrote `value` / `message` raw; a DocNo shaped like a formula
  would run when opened. `_csv_safe` prefixes formula-shaped cells (a negative number stays
  a number).
- **S3** the snapshot book is checked against the ingest's `BOOK_PATTERN`, and a header book
  must agree with the rows'.
- **N1** scope days must be `YYYY-MM-DD`, `docNo` at most 50 characters, scope refused on
  products / stock. **N2** the rows view and workbook tolerate non-string, nested and
  non-finite vendor cells. **N3** a snapshot past 10,000 documents is refused CRM-side.
  **N5** tests added: company B's same-numbered DO never adopted, formula-shaped DocNo
  neutralised in the xlsx, the hostile quantities.
- **N4** (apply failure handler logs `exc_info`, shared with products and stock): left as
  is; the per-record SAVEPOINTs flush before the batch commit, so a commit-time driver
  message carrying a record is improbable. Recorded, not changed in this lane.

Clean: multi-company scoping (every ingest lookup filters `company_id`), owner-only routes,
the scope dict (allow-listed twice, JSON body only, never the URL), the migration's sweep.

## 1.10 Phase 3 correctness review (30 Sep, on 69c1f263 + 40884ec3) and what changed

Verdict "needs work"; kill tests 12 of 16 backend mutations killed, 1 of 6 frontend. Taken in
(`TestCorrectnessFixRound` + the frontend tests named):

- **Blocker 1** main gained `lsa_0001_show_all_counts` on the same parent: merged main,
  `scripts/alembic-reparent.sh` re-parented `do_pull_0001_perm`; the migration test now pins
  "the one head" (`ScriptDirectory.get_heads()`), never a literal parent.
- **Blocker 2** frontend kill gaps: `useAutocountPullAction` defaults its slug from
  `AUTOCOUNT_PULL_PERMISSION[entity]` and OrdersList passes the entity alone (pinned);
  `page.deliveryOrdersPull.test.tsx` renders the job page for the DO job type (review card,
  label, Back to Delivery Orders); `PullExcelViewTab.columns.test.ts` pins the DO columns.
- **S1** the pull's rows carry `source_ref`, the push's do not, and the ingest diffs the whole
  record: a push-then-pull cycle read every document as `updated`. `_ingest_rows` strips
  `source_ref` before the ingest (after the contentHash check); pinned push-then-pull =
  `unchanged`, `source_record` without `source_ref`. Plan 1.2 corrected.
- **S2** duplicate (Doc No, Item Code, Location) lines are summed on both sides of the compare.
- **S3** `with_warnings` counts only documents that write a row, `stale_ignored` excluded.
- **S4** row identity: warnings in words, non-zero line counters only, no `source_ref`, no
  `errors` dict.
- **S5 / N2** the Excel view shows a quantity at its own precision and the document date as
  dd/MM/yyyy. **S6** compare tab DO column and three-part only-in split pinned. **N1** UAC
  says nine counters. **N4** `_csv_safe` prefixes any leading dash (OWASP). **N5** adoption
  never appears in the warnings suffix, pinned.
- **N3** (an open pull is reused whatever scope the second click names): left as is; the
  trigger is the scope dialog (1.8), where the click will name a window.

## 1.11 Built after the mock approval (owner "okay" on Q1 to Q6, 30 Sep)

- **Start dialog** `PullScopeDialog` (From day / To day prefilled to the last 31 MYT days, no
  document field); OrdersList opens it unless the caller has an open pull;
  `useAutocountPullAction.onSelect(scope)` posts `scope` (the `PullStartBody.scope` built in
  1.2). Products and Stock never see it.
- **Compare route** `source` (`lines` default, `headers`), rows cut to `pull_window(pull)`
  (scope, else the header's `fromDay`/`toDay`, else the 31 days ending on the snapshot's MYT
  day) by `_excel_day` (serials, dd/MM/yyyy, ISO, yyyyMMdd). Lines fields per Q3: `qty` and
  `total_ex` (SubTotalExTax, else SubTotal) summed per key, `unit_price`, `discount` (text,
  `5%` and `5` read the same, zero as blank). Headers (`compare_delivery_order_headers`):
  `doc_date`, `debtor_code`, `cancel`. Not compared: Created Time, Debtor Name, Agent, Total
  (Inc), Overall Tracking (Q6). Per-file summaries in `compare_sources`, `compare` = both
  added up (one headline). `serialize` adds `compare_sources`, `window`,
  `confirm_requires_match`.
- **Q4 switch** `settings.autocount_do_pull_confirm_requires_match` (env
  `AUTOCOUNT_DO_PULL_CONFIRM_REQUIRES_MATCH`, default False = advisory). On:
  `match_gate_reason` fills `confirm_blocked_reason` (read-time, never stored) and
  `confirm_pull` refuses 409 until both files compared with zero differences and only-ins.
  One switch, one sentence, the FE needs nothing beyond the existing disabled Confirm +
  reason line. Crew is confirming the owner's intent; flipping it is an env change.
- **Compare tab** two dropzones, the window line, per-file "N in the window, M outside it
  ignored", one headline (advisory sentence), one grid with a Source column ("Lines" /
  "Headers") instead of the mock's group rows (the shared DataGrid has no group-row
  primitive; same information, one column).
- Not changed: Q5 (a DO only in AutoCount still lands on Confirm, it is the ingest's
  behaviour); the Changes and Excel view tabs.

## 2. Build order (tests first)

1. This plan + UAC, first commit, draft PR (`crew-lane: DO-PULL-CRM`).
2. Red pytest `be/tests/test_autocount_pull_delivery_orders.py` (reuses SR1's `env`, `task_db`,
   `_FakeFoundryX`, `_seed_pull_job`, `_run_preview`, SR3's `_run_apply` / `_seed_apply_job`,
   and the DO ingest test's master seeding) + vitest for the FE switches.
3. Backend: maps + registry slug + migration + router gate; `on_progress` on the DO ingest;
   `_preview_delivery_orders` / `_apply_delivery_orders`; rows / download / compare halves.
4. Frontend: the switches in 1.6.
5. Reviewer + security-reviewer (permission slug, so it runs) + hand-test script.

## 3. Open questions for DO-PULL-SS (recommendation in bold)

1. Where does the book travel? **Header `book`** (one book per snapshot); a per-row `book` key
   would also be accepted only if the header has none. Pinned by the "no book -> failed" test.
2. Scope of the snapshot (DocDate window vs everything)? **Shared service's setting**, like the
   push; the CRM shows `recordCount` and whatever `docDateFrom` / `docDateTo` the header carries.
3. Row shape: **the vendor record verbatim**, so `AutocountDocIngestService` is the one writer.
