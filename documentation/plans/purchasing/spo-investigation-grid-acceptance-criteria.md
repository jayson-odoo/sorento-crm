# UAC: SPO document list + form view

Plan: PLAN-spo-investigation-grid.md
Status: APPROVED 1 Sep 2026 - GO; UAT batch (AC-21..AC-26) added 1 Sep evening

## Journey

See the plan's Journey section (contract copy): captain arrives with a planning
question, lands on the Outstanding document list, narrows by product + warehouse, reads
the balance/ETA/overdue/Plan answer from the document rows and the form view's Lines tab,
leaves with a number and a reason instead of a SQL session.

## Phase 1 - FE against mock

- AC-1 [FE] Given the sidebar, when I click Procurement > SPO Allocations, then I land
  on a DOCUMENT list (one row per SPO number) on the **Outstanding** tab, sorted newest
  SPO first, in the Purchase Orders page's toolbar grammar (tabs All/Outstanding/
  Completed, search, filters, Columns, Export).
- AC-2 [FE] Given the list, then each row shows: SPO No with doc date beneath, Supplier
  (majority + "+N more" when lines disagree), Status (Outstanding GREEN, matching the PO page), Earliest
  ETA (rendered AS IS - no TBA masking), Total qty, Lines, Balance, worst Overdue days
  (amber when > 0).
- AC-3 [FE] Given product and/or warehouse filters set, then only documents holding a
  matching line remain. No totals strip is rendered (markup ruling 1 Sep).
- ~~AC-4 [FE] Given the Overdue toggle on...~~ **RETIRED 1 Sep evening (UAT batch)**:
  the toggle comes off the list toolbar entirely - `worst_overdue_days` is already a
  sortable column and AC-25 widens `query` far enough that the standalone toggle is
  redundant. The backend `overdue_only` param stays for other callers; nothing
  FE-side sends it.
- AC-5 [FE] Given a row click, then the form view opens at
  `/procurement-management/spo-allocations/<spo_number>` (slash-encoded path param, no
  UUIDs on screen). The title row carries: a Back to SPO Allocations link, the status
  badge, an Edit button, and a POSITION pager `< 1 / 50 >` honouring the list's filter +
  sort.
- AC-6 [FE] Given the form view, then tabs are **Header | Lines** (line-style tabs per
  apple-design). Header tab: supplier (majority + "+N more" chip that EXPANDS ON CLICK),
  doc date, allocated, received, balance, line count. Lines tab lists EVERY line with:
  Product, Warehouse, Allocated, Received, Rejected, Balance, ETA, Overdue, Plan badge
  (In plan / Pool / Off / No location), Packing List, Status.
- AC-7 [FE] Given I arrived with product/warehouse filters, then matching lines in the
  Lines tab are visibly highlighted while all lines stay visible.
- AC-8 [FE] The form view is READ-ONLY until Edit is pressed; in edit mode lines can be
  adjusted and deleted, committed with Save (deferred/undo pattern where the apple S6
  primitive exists, else confirmation). On the LIST: bulk select + Delete selected and
  Import SPO live in one **Actions** dropdown; Create SPO Allocation stays primary.
- AC-9 [FE] The old per-allocation detail route is retired; anything that linked to it
  lands on the document form view.
- AC-10 [FE] List and form view are usable and non-clipped at 375px AND 1280px;
  DataGrid fixed layout, resizable columns, explicit sizes, truncate + title on long
  text; new columns are not exiled to the far right for users with saved column prefs.

## Phase 2 - backend, test-first

- AC-11 [BE] `GET /spo-allocations/documents` returns paged header rows grouped by
  `spo_number` with the AC-2 fields, filters `state` (default outstanding),
  `product_id`, `warehouse_id`, `overdue_only`, `query`; aggregation happens in SQL
  with paging over the grouped set (80k rows).
- AC-12 [BE][T] **One rule, fifth reader**: `outstanding` line membership =
  `spo_supply.open_incoming_clauses()` AND balance > 0, IMPORTED - grep proves no
  restated copy of the clauses in new code. Pytest seeds one line per exclusion reason
  (closed line, fully_received, landed shipment, zero balance) and asserts each is
  excluded from outstanding and present in completed.
- AC-13 [BE][T] Line computed fields are declared on the response schema and asserted
  present in a response test (drop-guard): balance, arrival_date (eta_delay ->
  estimated_arrival -> expected_date), overdue_days, supplier_name (shipment supplier
  else line supplier), planning_span.
- AC-14 [BE][T] `planning_span` yields all four values from seeded warehouses: flagged
  -> `in_plan`; is somebody's `pool_warehouse_id` -> `pool`; active unflagged -> `off`;
  line without warehouse -> `none`.
- AC-15 [BE][T] Header rollups: status Outstanding iff any line outstanding; balance
  sums outstanding lines only; worst_overdue_days = max over outstanding lines;
  majority supplier + extra count when lines disagree.
- AC-16 [BE][T] `GET /spo-allocations/documents/{spo_number}` returns header + all
  lines; unknown number -> 404 via AppException. (No server prev/next - S1 deviation
  accepted; the FE pager is cache-based.)
- AC-16b [BE][T] Bulk delete = pending-actions registry action `spo_document.delete`
  (entity_id = spo_number): the handler deletes that document's allocation lines for the
  CALLER'S COMPANY ONLY (two-company pytest proves the other company's identically
  numbered document survives); the list uses `useDeferredBulkAction` with that key -
  cancel never deletes, the server commits on lapse even if the tab closes, and the
  window comes from System Settings.
- AC-17 [BE][T] Auth: both routes deny without the module permission (happy +
  auth-denial + validation per route). Tests on Postgres only.
- AC-18 [FE] Mock swapped for the real service at the service boundary
  (`lib/api-client`, `extractApiError`, `buildDataGridParams`); Export emits the grid's
  visible columns from the real endpoint.

## Phase 3 - review + DoD

- AC-19 [E2E] agent-browser evidence run, sidebar navigation from `/`: filter product +
  warehouse on Outstanding, read the balances, open the document, see highlighted lines with
  Plan badges - recorded at 375px and 1280px against real data (the 1 Sep prod
  question answerable on screen).
- AC-20 [T] /code-review pass + PR-CHECKLIST; DoD gate: real data verified, no new
  permission needed (existing spo-allocations view slug) or grant sweep run if one is
  added; no orphaned references to the retired route.

## UAT batch (1 Sep evening) - AC-21..AC-26, AC-4 retired

- AC-21 [FE] Given the form view, then Back sits on the page-level header row, top
  right - the same placement/markup as the Purchase Order form view
  (`PageHeader`'s `actions` slot, `BackToList`) - not on the record's own title card.
- AC-22 [FE] Given I am on the Lines tab and step to the next/previous document via
  the pager, then I land on the Lines tab there too (`?tab=lines` carried in the
  pager's own link); a document opened fresh from the list (no `tab` param) starts
  on Header.
- AC-23 [FE] Given the Lines tab, then a Columns visibility control (same affordance
  the list uses) is present; Rejected and Overdue are hidden by default and
  reachable through it; every other Lines column keeps its explicit size + truncate.
- AC-24 [FE][BE][T] Given Edit on the form view, then:
  1. the Warehouse combobox renders cleanly at its column width (no clipped/doubled
     label) - the fixed-height override that fought `SearchableSelect`'s wrap
     behaviour is gone from every combobox in this grid.
  2. Product is editable via a server-searched `SearchableSelect`
     (`ProductComboboxSearchable`, the same `getProducts` pattern the list's own
     product filter uses) and persists through the existing update mutation.
  3. ETA (the line's own `expected_date`) is editable via a date input and persists
     through the same mutation; a pytest asserts the round trip
     (`PUT /spo-allocations/{id}` -> `GET .../documents/{spo_number}`).
  4. Supplier is editable per line via a server-searched `SearchableSelect`
     (`SupplierCombobox`, reused - no per-feature `getSuppliers` duplicate) and
     persists through the same mutation; a pytest asserts the round trip.
     `SPOAllocationUpdate` and `SPODocumentLine` both declare `expected_date` and
     `supplier_id` (drop-guard test for the response fields).
- AC-25 [BE][T] `GET /spo-allocations/documents`'s `query` filter also matches a
  line's warehouse CODE and its packing list's shipment/container number, in
  addition to SPO number and product; pytest seeds one document findable only by
  its warehouse code and another findable only by its packing-list/container
  number.
- AC-26 [FE][T] Given the form view's title row, then a gear icon dropdown offers
  "Delete document"; selecting it parks the SAME `spo_document.delete` pending
  action the list's bulk delete uses (single `entityId` = the spo_number, no
  confirm dialog, D7) and routes back to the list on commit; vitest pins the wiring
  (action key, entity, `start()` call) and that Cancel/no-selection deletes nothing.
