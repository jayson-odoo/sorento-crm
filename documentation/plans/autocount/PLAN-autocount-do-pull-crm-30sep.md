# PLAN: Delivery Orders, Pull from AutoCount (lane DO-PULL-CRM, BL-SS-286)

Status: **planned, building** (full track: new permission slug + grant migration, so not the
small-fix track; no new external ingest surface, the apply reuses the DO ingest). Branch
`crew/do-pull-crm` (base `main`, cut at `90807ede`). UAC:
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
  the ingest untouched (no mapping, one writer; `source_record` keeps `source_ref` exactly as
  the feed's own push does).

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
failed, retryable, lines_deleted}`. The confirming user is stamped as the audit actor for the
task's session (`app.audit_context.stamp_actor`), the way the request path stamps the caller,
so the `orders` audit rows name the person who confirmed, not "worker".

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
