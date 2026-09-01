# PLAN: SPO document list + form view (investigation touch-up)

Status: DELIVERED 1 Sep 2026 - S1-S3 complete, PR open
Date: 2026-09-01
Domain: purchasing (procurement-management/spo-allocations)
Trigger: captain, 1 Sep 2026 - "the UI of spo allocations is very hard to use, very hard
for me to investigate ... any outstanding SPO, any SPO to this location, for this
product". Same day rulings: NO schema change (no header/lines split, no PO merge - the
merge trigger stays parked in memory), touch up the UI only; the page should read like
the Purchase Orders page (document rows, form view inside).

## Journey (step 1)

The actor is the captain (or a purchaser), arriving from a planning question - "why is
Use incoming empty?", "is anything still coming for SRTWCY7405-PJ?", "what is BRW-IB
owed?". They open Procurement > SPO Allocations from the sidebar.

The first screen is a DOCUMENT list in the Purchase Orders page's grammar, landing on
the **Outstanding** tab, newest SPO first: one row per SPO document with supplier,
status, earliest ETA, total qty, line count, outstanding balance and worst overdue days.

Steps, one decision each:

1. They type a product in the product select (server search) - the list narrows to
   documents holding a matching line.
2. They pick a warehouse - the screen now reads "outstanding for X at BRW-IB = 332,
   earliest ETA 1 Aug, 31 days overdue". The 1 Sep SQL investigation is these two
   selects.
3. They click the document. The form view opens read-only: title row (number, status,
   Back link, Edit, < 1 / 50 > pager), a **Header** tab with the document fields, and a
   **Lines** tab listing every allocation - matching lines highlighted -
   with balance, ETA, overdue, rejected qty, packing list and a Plan badge stating
   whether fulfilment planning can see that line (In plan / Pool / Off / No location).
4. Overdue-only toggle chases late suppliers; Export takes the current columns out.

They leave holding a number and a reason, not a query. Read surface - nothing here
notifies anybody. Everything is derived (balance, ETA, overdue, span); the user is only
ever asked WHAT (product) and WHERE (warehouse).

## Problem

The current page is a manage-list (group-by SPO number, checkboxes, delete, import). It
cannot answer: what is outstanding, what is coming to this warehouse for this product,
how late is it, and can planning see it. Answering those on prod took raw SQL (1 Sep).

The engine already answers all four through ONE rule -
`app/services/scm/spo_supply.open_incoming_clauses()` (+ balance > 0 per reader, + the
ETA coalesce `eta_delay_date -> estimated_arrival_date -> expected_date`, +
`overdue_days`). This plan makes the page the FIFTH reader of that rule, so the screen
and the ladder can never disagree.

## Grill rulings (1 Sep, Q1-Q16)

- Document list mirrors the PO page: header rows, All / **Outstanding** (default) /
  Completed tabs, newest first. NO separate line-grain view (Q12): filters find the
  document, the form view shows the lines.
- ETA renders AS IS - no TBA masking of 2029/2030 placeholder dates (Q3).
- Plan badge keeps four states: In plan / Pool / Off / No location (Q4).
- Overdue = toggle, not a tab (Q5); at document grain "any outstanding line past its
  ETA", showing worst overdue days (Q16).
- Export emits the grid's columns (Q6).
- Detail URL is the document number, path param, slash-encoded (Q7). No UUIDs on screen.
- Supplier on a header row = majority supplier + "+N more" when lines disagree (Q8 -
  surfaces the data smell, does not hide it).
- Header status = Outstanding while ANY line is outstanding, else Completed (Q9).
- Filters match LINES; list shows documents with >=1 matching line; the form view
  shows ALL lines with matches highlighted (Q10).
- Form view: header block + Lines tab; line edit/delete live there; Import + Create stay
  on the list toolbar; prev/next RecordNavigation per the CRUD standard (Q11).
- The standalone per-allocation detail page RETIRES: its fields (rejected qty, packing
  list, related documents, status, created at) become columns/affordances of the Lines
  tab (Q13, Q14).

### Lavish markup rulings (1 Sep, supersede anything above on conflict)

- NO totals strip on the list.
- Outstanding status pill is GREEN, matching the PO page.
- Toolbar: Columns | Export | one **Actions** dropdown (Import SPO, Delete selected) |
  primary Create SPO Allocation. Bulk select checkboxes STAY on the list - bulk delete
  happens there.
- Form view is READ-ONLY with an **Edit** button on the title row; deleting a line means
  Edit -> adjust -> delete -> Save (View = Edit same-layout principle). Title row also
  carries a "Back to SPO Allocations" link and the pager as a POSITION: < 1 / 50 >
  scoped to the list's filter + sort.
- Form view tabs: **Header | Lines** - the document fields (supplier + "+N more"
  click-to-expand, doc date, allocated, received, balance, line count) live in the
  Header tab.
- ETA column documents its source where the user can find it (tooltip/help): shipment
  eta_delay_date -> shipment estimated_arrival_date -> SPO line expected_date.
- **apple-design governs the build** (.claude/skills/apple-design + the Apple alignment
  feature): line-style tabs, page-scoped pager, destructive actions as deferred actions
  with undo where the S6 primitive has landed (else ConfirmDeleteDialog), reduced-motion
  respected, nothing clipped at 375px.

## Not in scope

- NO `spo_documents` header table; `spo_allocations` stays flat. Headers are synthesized
  by grouping on `spo_number` at read time.
- NO merge into `purchase_orders` (trigger parked: revisit when AutoCount round-trip
  needs one identity keyspace).
- NO change to the engine, `open_incoming_clauses`, or its four existing readers.
- Import flow, create/edit/delete allocation endpoints: unchanged.

## Shape

### S1 - backend: document endpoints (new), computed fields (shared)

`app/api/v1/procurement/spo_allocations.py` + service:

- `GET /spo-allocations/documents` - paged header rows grouped by `spo_number`:
  `spo_number`, `doc_date` = `COALESCE(min(issue_date), min(created_at))` (review S4: issue_date is the document's own date; created_at is the import timestamp fallback), `supplier_name` +
  `supplier_extra_count` (majority + N), `status` (outstanding/completed rollup),
  `earliest_eta`, `total_allocated`, `total_received`, `balance` (outstanding lines
  only), `line_count`, `worst_overdue_days`.
  Filters: `state` (all|outstanding|completed, default outstanding), `product_id`,
  `warehouse_id`, `overdue_only`, `query` (SPO number / product contains).
  Response carries `total` for paging (no totals strip is rendered - markup ruling).
- `GET /spo-allocations/documents/{spo_number:path}` - the header (same rollup) + every
  line with computed fields. NO server-side prev/next (S1 deviation, accepted 1 Sep):
  the FE pager uses the established `useListPager` cache pattern every other detail
  page uses.
- Line computed fields (declared on the response schema - `response_model` drops
  undeclared fields, drop-guard test required): `balance`, `arrival_date` (the one
  coalesce, same order as `_spo_rows`), `overdue_days`
  (`spo_supply.overdue_days`), `supplier_name` (shipment supplier else line supplier),
  `planning_span` (`in_plan` | `pool` | `off` | `none`).
- `outstanding` = `open_incoming_clauses()` + balance > 0, IMPORTED from
  `app.services.scm.spo_supply` - never restated. `completed` = the complement.
- Bulk delete rides the EXISTING pending-actions registry (review ruling 1 Sep,
  reversing the ad-hoc endpoint): register `spo_document.delete` in
  `app/services/record_actions.py` (entity_id = spo_number, company-scoped delete of
  that document's lines in the handler - resolve ids under a scoped SELECT, delete by
  id, two-company test), and the list uses `useDeferredBulkAction` with that action key
  (server commits on lapse even if the tab closes, window from System Settings). No
  bespoke `DELETE /documents` endpoint and no hand-rolled client countdown.
- Existing endpoints (`/`, `/grouped-by-*`, CRUD, import) untouched; the two grouped
  list endpoints become dead code for the FE and are removed only if nothing else calls
  them (check MCP catalogue + n8n before deleting).

### S2 - frontend: document list + form view

- **List** (`SPOAllocationsList` rebuilt): PO-page grammar - tabs All/Outstanding
  (default)/Completed, `ListSearchInput`, product `SearchableSelect` (SERVER search - no
  capped dropdown, standing rule), warehouse `SearchableSelect` (clearable), overdue
  toggle, totals strip, Export. Columns: SPO No (+doc date under, like PO No) | Supplier
  (+N more) | Status | Earliest ETA | Total qty | Lines | **Balance** | **Overdue**
  (worst, amber). Row click -> form view. Group-by dropdown and checkbox bulk-select
  REMOVED from the list (bulk delete moves to the Lines tab if still wanted - confirm at
  review). Import SPO + Create SPO Allocation stay on the toolbar.
- **Form view** (new route `app/(protected)/procurement-management/spo-allocations/[spoNumber]/page.tsx`):
  header block (SPO number, status badge, supplier, doc date, totals), RecordNavigation
  prev/next, **Lines** tab: Product | Warehouse | Allocated | Received | Rejected |
  **Balance** | **ETA** (as-is dates) | **Overdue** | **Plan** badge | Packing List |
  Status | row actions (edit / delete via existing dialogs, ConfirmDeleteDialog). Lines
  matching the list's active product/warehouse filter arrive highlighted (filter carried
  in the URL query).
- **Retire** the old per-allocation detail page + its route; redirects or links that
  pointed at it go to the document form view.
- View = Edit layout rule: read-only metadata in the header, same order in both modes.
  Usable at 375px and 1280px; DataGrid fixed layout, explicit sizes, truncate+title.

### S3 - tests + browser evidence (Phase 2 discipline, test-first)

- pytest: `outstanding` rollup admits exactly what `open_incoming_clauses` + balance
  admits (seed one row per exclusion reason: closed line, fully_received, landed
  shipment, zero balance); computed fields present (drop-guard); `planning_span` all
  four values; majority-supplier rollup; document totals; prev/next respects filters;
  auth-denial per route.
- vitest: tabs drive `state`; overdue toggle; totals strip; highlight-on-filter; badge
  states.
- agent-browser evidence run, sidebar navigation from `/`, on the dev stack: the
  SO381895-era question answered on screen (filter product + warehouse, read balance +
  overdue, open the document, see the lines + Plan badges), at 375px and 1280px.

## S1 outcome (1 Sep)

Delivered in worktree branch `worktree-agent-ae2c28dfc5b7d7c84`; browser-verified at
375px + 1280px, tsc + eslint clean. Accepted deviations: (1) pager via `useListPager`,
no server prev/next; (2) document-grain bulk delete needs the new DELETE endpoint above
in S2; (3) Lines-tab edit covers Warehouse/Allocated/Received/Rejected, not Product.

## Order

Phase 1 FE-first against a mocked service (document list + form view shapes tuned),
verify in browser -> Phase 2 backend endpoints test-first, swap mock at the service
boundary -> Phase 3 /code-review -> DoD gate. One lane, one PR unless review splits it.
