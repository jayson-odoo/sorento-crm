# PLAN - Order inquiry: Request CS to reserve stock (+ stock grid on OI lines and board list)

Status: **SHIPPED #1120 (9fc93c90a, 23 Sep 2026); round 3 (6d) built on PR #1149; round 4 (section 6e, AC-RS-76..90, line-by-line staging) BUILDING on the same branch.** UAC: `oi-request-cs-reserve-acceptance-criteria.md`.
Track: full three-phase lane (migration, new permission, email). One lane, one PR (R-E).
Lavish marks folded: same `CellStockTable` component; reserved mail carries BALANCE; board list view
opens the grid view's dialog from the row (Q3 accepted with the go). Branch `feat/oi-request-cs-reserve`.

## 0. Why

Today the post-inquiry path is rigid: CS raises ORDER rows, purchasing buys. Purchasing often
wants CS to cover part of a row from own or pool stock first (BRW has some, buy only the
balance). That happens by email today (Joey -> Eling, CC the raiser; Eling transfers in AutoCount
what she can, mails back; Joey buys the rest) and the system never learns the reserved quantity,
so Taken / Remaining lie until the next stock upload. Two smaller gaps ride along: the OI side has
no stock-by-location grid (purchasing opens the board to check BRW), and the fulfilment board's
LIST view lacks the grid its GRID view has.

## 1. Rulings (owner, 22 Sep 2026)

| # | Ruling |
| --- | --- |
| R1 | Only Eling (CS head) reserves. The person mailed is configured (Automation recipients); the person allowed to act is gated by a new permission `projects.order_inquiries.reserve`. |
| R2 | Eling enters a reserved qty per row; a reason is required on every row reserved short of the request, including zero. |
| R3 | Default location = the row location's pool warehouse (`BRW-BB` -> `BRW`, via `Warehouse.pool_warehouse_id`); Eling may change it to any location shown in the stock grid. |
| R4 | Reserved qty counts as Taken immediately on Eling's confirm. No transfer number captured now; AutoCount transfer automation is a later lane. |
| R5 | States: `Request to reserve` -> `Reserved`. The cycle repeats on the remaining qty (a row can be reserved 50, requested again on 89). No amend after confirm; repeat instead. Reversal = the existing Unlink. |
| R6 | Email both ways: request mail to Eling CC raiser + requester; reserved mail to the requester CC raiser. |
| R7 | Links require login; the OI detail page is the acting page. No token page. |
| R8 | No double count with the board's own-location cover: the reserved qty lowers the row's owed demand exactly as a PO link does, so the board plans the balance only. |
| R9 | ONE email per request, however many rows (never one per row). |
| R10 | Requested qty defaults to the row's remaining, editable down, never above. |
| R11 | Purchasing sees the board's stock grid on the OI Lines tab; the board LIST view gets the same grid. Both are slices of this lane, built first. |

## 2. What exists (measured 22 Sep on main 2280975f9)

- Rows `projects.order_inquiry_rows` (`app/models/project_so.py:987`) carry `stock_location`,
  `verb`, `state` (raised / partly_linked / placed / actioned / cancelled), `bundled_qty`.
- Cover source `OrderInquiryLink` (`project_so.py:1128`): `po_line_id` XOR `spo_allocation_id`,
  CHECK `ck_order_inquiry_links_one_target` (`:1204`), `document`, `qty`, `linked_by/at`, `auto`.
- Taken is never stored. `refresh_link_state` (`project_order_inquiry_service.py:5504`) is the one
  writer of row `state` from `sum(link.qty)`; worklist `_quantity_flow_by_so_line`
  (`order_inquiry_worklist_service.py:1678-1753`) sums links by `row_id` with no target filter;
  `_UNLINKED_QTY` (`:415`) likewise. Only `_PO_LINKED_QTY` / `_SPO_LINKED_QTY` (`:381-382`) filter
  on the target column.
- Demand view `scm.committed_v` (`app/services/scm/demand.py:531-534, 599-602`) nets
  `SUM(l.qty) ... WHERE l.row_id = oir.id`, no target filter. `scm.on_order_v` never reads links.
- Board `qty_free_remaining` etc. are supply-side only; the board reads the line's owed demand
  from `committed_v`, so a link on the row lowers what the board has to plan (R8 holds by
  construction; AC-RS-30 proves it).
- Stock grid: `CellStockTable.tsx` + `StockDocumentsPanel.tsx` under
  `project-sales/fulfilment-planning/components/`, fed by `useStockDetail(productId, warehouseId,
  lineIds, group)` (`_shared/hooks/useFulfilmentPlanning.ts:341`) ->
  `GET /api/v1/project-sales/fulfilment-planning/stock-detail?product_id&group|warehouse_id&line_ids`.
  Props: `locations`, `taken`, `lineIds`, `showGroupSubtotal`; no board object required.
  `FulfilmentBoardListView.tsx` has no reference to it.
- Group suffix: `group_of_warehouse_code` (`scm/sales_agent_service.py:311`, `BRW-BB` -> `BB`,
  bare pool code -> `None`). Pool of a location: `Warehouse.pool_warehouse_id`
  (`models/inventory.py:52`), resolver shape `_pool_code_for_core_line`
  (`planning_change_service.py:2975`).
- OI detail `OrderInquiryDetail.tsx` (`order-inquiries/[id]/components/`): tabs Lines / General /
  Related PO / Related SPO; `DetailActionsMenu` (`:328-392`) with Auto link, Choose document, Link
  selected, Unlink selected (deferred action `order_inquiry_row.unlink`), Reject selected,
  Unconfirm, Export. Row pills in `_shared/components/OrderInquiryVerbPill.tsx` (`STATE_LABEL`
  `:88`). Permission gate pattern `useHasPermission` (`OrderInquiryDetail.tsx:61-82`).
- Permissions: `app/rbac/permission_registry.py:584-601` (`projects.order_inquiry.action`,
  `projects.order_inquiries.acknowledge`); `sync_permissions` seeds on startup, no migration.
- Email: Automation rows. `dispatch_event(trigger_type, context, source_kind, source_id)`
  (`automation_service.py:272`); `recipient_config` keys `user_ids, role_ids, include_actor,
  one_email, extra_emails` (`:389-410`); with `one_email` the resolved list goes out as ONE
  outbox row, first address To, rest Cc (`notification_tasks.py:251-281`). Trigger catalog
  `automation_triggers.py:506` (handover precedent). Seed precedent
  `alembic/versions/212_seed_pr_sponsorship_approved_automation.py`; template + row seeded by
  `PLAN-scm-oi-handover-email.md` 3.6. Post-commit drain precedent `_fire_pending_handover`
  (`project_order_inquiry_service.py:9494`, root commit only).
- OI number mint `next_inquiry_no` (`project_so.py:890`). Reserve requests get NO number: they
  are addressed as `OI-2609-0678 request #2` (ordinal within the inquiry, by `requested_at`).

## 3. Design (simplest thing that works)

Two tables, one new link target, one permission, two Automation rows, one reusable grid.

### 3.1 Schema (one migration, `<next>_oi_reserve_requests`, id <= 32 chars)

```
projects.order_inquiry_reserve_requests
  id uuid pk, order_inquiry_id fk, ordinal int (1..n within the inquiry),
  state text check in ('requested','reserved','cancelled'),
  requested_by fk users, requested_at tz, note text null,
  reserved_by fk users null, reserved_at tz null,
  cancelled_by fk users null, cancelled_at tz null
  unique (order_inquiry_id, ordinal)

projects.order_inquiry_reserve_request_rows
  id uuid pk, request_id fk (cascade), row_id fk order_inquiry_rows,
  qty_requested numeric > 0, warehouse_id fk warehouses (default = pool, R3),
  qty_reserved numeric null (>= 0, <= qty_requested), reason text null
  unique (request_id, row_id)
  partial unique index: one OPEN request row per OI row
    (row_id) where qty_reserved is null  -- enforced via state on the parent, see 3.3

projects.order_inquiry_links
  + reserve_request_row_id fk order_inquiry_reserve_request_rows null
  CHECK ck_order_inquiry_links_one_target widened to
    (po_line_id IS NOT NULL)::int + (spo_allocation_id IS NOT NULL)::int
      + (reserve_request_row_id IS NOT NULL)::int = 1
```

Downgrade drops the column, restores the two-target CHECK (deleting reserve links first), drops
both tables, removes the two seeded templates + automations.

### 3.2 Request (purchasing)

`POST /api/v1/project-sales/order-inquiries/{inquiry_id}/reserve-requests`
`{ rows: [{ row_id, qty_requested, warehouse_id? }], note? }` -> 201 request.

Rules (service `OrderInquiryReserveService`, new file, `app/services/order_inquiry_reserve_service.py`):

- Rows must belong to the inquiry, verb ORDER or ORDER_BACK, state raised / partly_linked,
  remaining > 0 (`row.qty - sum(links) - bundled_qty`), and have no open request row. Any
  violation -> 409 `AppException` naming the row.
- `qty_requested` <= remaining (R10) else 422 naming the row.
- `warehouse_id` defaults to the pool of `row.stock_location` (R3). When the location has no pool
  (it IS a pool, `group_of_warehouse_code` -> None) the default is the location itself.
- `ordinal` = max + 1 within the inquiry.
- Permission: same gate as the other purchasing actions on the page (`projects.order_inquiries.acknowledge`).
- Post-commit (root commit only, the handover drain pattern): ONE
  `dispatch_event("order_inquiry_reserve_requested", context, source_kind="order_inquiry_reserve_request", source_id=request.id)` (R9).

`POST .../reserve-requests/{id}/cancel` by the requester or anyone with the reserve permission,
only while `requested`. Exposed as the deferred action `order_inquiry_reserve_request.cancel`
(5 s reversible, `record_actions.py` registry) so the UI follows the standard countdown. No mail.

### 3.3 Reserve (Eling)

`POST .../reserve-requests/{id}/reserve`
`{ rows: [{ request_row_id, warehouse_id, qty_reserved, reason? }] }` -> 200 request.

- Gate: `projects.order_inquiries.reserve` (new registry entry, R1).
- Only while `requested`; every request row must be answered in the one call (all-or-nothing;
  partial answers are not a state).
- `0 <= qty_reserved <= qty_requested`; `reason` required (non-blank) when
  `qty_reserved < qty_requested` (R2) else 422 naming the row.
- `warehouse_id` must be an active warehouse. Eling's change is stored on the request row.
- For each row with `qty_reserved > 0`: insert `OrderInquiryLink(row_id, reserve_request_row_id,
  document="Reserved @ <warehouse_code>", qty=qty_reserved, linked_by=actor, auto=False)`,
  then `refresh_link_state(row)` (the existing writer moves the row to partly_linked / placed).
- Request -> `reserved`, `reserved_by/at`.
- Post-commit ONE `dispatch_event("order_inquiry_reserved", ...)`.
- Reversal: the existing Unlink (bulk deferred action, per-row action) deletes the link like any
  other; the request stays `reserved` as history. AC-RS-22.

### 3.4 Taken / Remaining / breakdown

Nothing to change in `refresh_link_state`, `_quantity_flow_by_so_line`, `_UNLINKED_QTY`,
`committed_v`: they sum by `row_id`. Add `_RESERVED_LINKED_QTY = _linked_qty(OrderInquiryLink.reserve_request_row_id.isnot(None))`
beside the PO / SPO twins and surface it as `reserved_qty` on the worklist row schema and the OI
header-lines schema, so the FE can print `Reserved 50` without a second query. Existing serializers
that print the first link's document (`po_ref` / `spo_ref` derivation) skip reserve links; the FE
reads `reserved_qty` instead.

### 3.5 Row chip

Derived per row, no new column: `reserve_state` in the lines serializer =
`requested` when an open request row exists, else `reserved` when `reserved_qty > 0`, else null.
`OrderInquiryVerbPill.tsx` gains `ReservePill` (`Request to reserve` amber, `Reserved N` green),
rendered beside the state pill in `orderInquiryHeaderLinesColumns.tsx` and the worklist columns.

### 3.6 Emails (two Automation rows, seeded in the same migration)

Context, both triggers:

```
{ "reserve": { "inquiry_no", "ordinal", "so_number", "customer", "project",
               "requested_by": {name, email}, "requested_at",
               "rows": [{ item_code, delivery_date, qty, remaining, qty_requested, location,
                          qty_reserved, reason }],
               "row_count", "state", "link" },
  "actor": {name, email}, "raiser": {name, email}, "requester": {name, email}, "today" }
```

`link` = `<FRONTEND_BASE_URL>/project-sales/order-inquiries/<id>?reserve=<request_id>` (login
required, R7). `raiser` = inquiry `raised_by`; `requester` = `requested_by`.

Recipient config gains two bools beside `include_actor`: `include_raiser` and `include_requester`
(context keys `raiser.email` / `requester.email`), one checkbox each in `RecipientPicker.tsx`
("Cc the person who raised the inquiry", "Cc the person who requested"). Same
`_normalize_recipient_config` / `resolve_recipients` mechanism; dedupe applies.

| trigger | seeded name | recipient_config | subject |
| --- | --- | --- | --- |
| `order_inquiry_reserve_requested` | `Order inquiry: request CS to reserve` | `user_ids: []` (owner adds Eling after deploy), `include_actor: true` (= requester), `include_raiser: true`, `one_email: true` | `Reserve request: {{ reserve.inquiry_no }} #{{ reserve.ordinal }} - {{ reserve.so_number }}` |
| `order_inquiry_reserved` | `Order inquiry: reserved by CS` | `include_requester: true`, `include_raiser: true`, `one_email: true` | `Reserved: {{ reserve.inquiry_no }} #{{ reserve.ordinal }} - {{ reserve.so_number }}` |

Because `one_email` puts the FIRST resolved address in To: for the request mail `user_ids`
resolve first (Eling To, requester + raiser Cc); for the reserved mail `include_requester`
resolves before `include_raiser` (requester To, raiser Cc). AC-RS-16 pins the order.

Bodies: one table. Request mail: ITEM CODE, DELIVERY DATE, QTY, REMAINING, REQUESTED, LOCATION.
Reserved mail: ITEM CODE, QTY, REQUESTED, RESERVED, BALANCE (row remaining after this reserve =
what purchasing still buys, owner mark 22 Sep), LOCATION, REASON. Footer with the acting person and
the link. `rows[].balance` joins the context for the reserved trigger. Inline
`border` / `padding` on every cell (mail clients have no stylesheet).

### 3.7 Purchasing UI (OI detail, Lines tab)

- Row selection -> `DetailActionsMenu` gains **Request CS to reserve** (enabled when every
  selected row is requestable; disabled items keep a tooltip naming the first reason).
- `ReserveRequestDialog`: one line per selected row: item code, delivery date, remaining, **Requested**
  (number input, default remaining, max remaining), **Location** (`SearchableSelect`, default the
  pool, options = the row's stock-grid locations), a chevron opening the stock grid for that row
  (3.9), optional note. Primary **Send request**. Toast `Request #2 sent to <name>` (name of the
  first To recipient, from the response).
- Lines tab header area: `ReserveRequestsCard` above the grid: the open request (rows, requested,
  location, who / when, **Cancel request** countdown for the requester), and a collapsed history of
  reserved / cancelled ones (rows with reserved qty + reason). Empty when none (card hidden, not an
  empty state, since the grid is the page's content).

### 3.8 Reserving UI (same page, Eling)

- With `?reserve=<id>` or when an open request exists and the viewer holds the reserve
  permission, `ReserveRequestsCard` renders the open request in **act mode**: per row **Location**
  (`SearchableSelect`, prefilled), **Reserved** (number input, default `min(requested, available at
  the chosen location, 0 floor)`, max requested), **Reason** (required when short, shown inline
  as soon as the value drops below requested), stock-grid chevron (3.9). Primary **Confirm
  reserved** (disabled until every short row has a reason). Toast `Reserved, <requester> notified`.
- A viewer without the permission sees the same card read-only.
- Detail header gets a `Request to reserve` badge while a request is open.

### 3.9 Stock grid (slice 1, no backend)

`OrderInquiryStockGrid({ productId, location })` in `_shared/components/`: resolves
`group = group_of(location)` (client twin of `group_of_warehouse_code`, split on first hyphen;
no hyphen -> `warehouse_id` lookup by code via the existing warehouse select service), calls
`useStockDetail(productId, undefined, [], group)` (or `warehouseId` for a pool), renders
`CellStockTable` with `showGroupSubtotal` and the expandable `StockDocumentsPanel`, exactly as
`BoardCellBreakdownDialog`'s Stock tab. Used in:

- OI Lines tab: row expander column (chevron) -> grid inline under the row.
- `ReserveRequestDialog` and `ReserveRequestsCard` rows (3.7 / 3.8).
- `FulfilmentBoardListView.tsx`: the expanded decision panel already holds buy / borrow /
  reasoning (owner mark 3, 22 Sep), so the grid is NOT lifted into it. The list row opens the
  grid view's own `BoardCellBreakdownDialog`, unchanged, from a `Stock` icon-button on the row
  and from the "To plan" figure. Pending owner answer Q3 on the Lavish page (dialog vs inline
  below the decision block).

No new endpoint: `stock-detail` already accepts `product_id` + `group` / `warehouse_id`. The OI row
needs `product_id` in its serializer if absent (verify item 1 in section 6).

## 4. Slices (one lane, one PR)

| slice | content | phase |
| --- | --- | --- |
| S1 | 3.9 grid on OI Lines tab + board list view | Phase 1 FE against the live endpoint (no mock needed, endpoint exists); vitest |
| S2 | 3.1 migration, 3.2 request endpoint + cancel, 3.4 reserved figure, 3.5 chip, 3.7 dialog + card, 3.6 request mail | Phase 1 mock of dialog + card, then Phase 2 tester-first |
| S3 | 3.3 reserve endpoint, 3.8 act mode, 3.6 reserved mail, permission | Phase 2 tester-first |
| S4 | guide, journey evidence, Phase 3 review (reviewer + security-reviewer on Opus: new permission + link CHECK) | Phase 3 |

Phase 1 mock for S2 / S3 goes on the Lavish page first (owner markup), then the coder builds it
against `msw`-free stubs in the service layer, swapped for real once S2's endpoint lands.

## 5. Captain's test list (for the tester)

| AC | test | assertion in words |
| --- | --- | --- |
| RS-1 | `test_request_creates_request_and_rows_one_dispatch` | 3 rows, one call: one request `ordinal 1`, 3 request rows, `dispatch_event` mocked called ONCE after commit with `row_count 3` |
| RS-2 | `test_request_default_location_is_pool` | row at `BRW-BB` -> request row `warehouse_id` = BRW's id; row at a pool code -> itself |
| RS-3 | `test_request_qty_capped_at_remaining` | qty 100, link 40 -> requested 61 rejected 422, 60 accepted |
| RS-4 | `test_request_rejects_open_duplicate_and_wrong_state` | second open request on a row 409; actioned / cancelled / DELAY row 409 |
| RS-5 | `test_second_request_after_reserved_allowed` | reserve 50 of 139, new request on 89 -> ordinal 2, allowed |
| RS-6 | `test_reserve_writes_links_and_refreshes_state` | reserved 50 -> one link with `reserve_request_row_id`, `document "Reserved @ BRW"`, row `partly_linked`; reserved full -> `placed` |
| RS-7 | `test_reserve_zero_needs_reason` | 0 without reason 422; with reason ok, no link written |
| RS-8 | `test_reserve_short_needs_reason_full_does_not` | 30 of 50 without reason 422; 50 of 50 no reason ok |
| RS-9 | `test_reserve_all_rows_or_422` | missing one request row -> 422, nothing written |
| RS-10 | `test_reserve_requires_permission` | user without `projects.order_inquiries.reserve` -> 403; requester without it 403 |
| RS-11 | `test_reserve_only_once` | second reserve on a reserved request 409 |
| RS-12 | `test_taken_remaining_include_reserved` | worklist `_quantity_flow_by_so_line`: taken = PO 40 + reserved 50, remaining 49; `reserved_qty` 50; PO card 40, SPO card 0 |
| RS-13 | `test_committed_v_owed_nets_reserved_link` | owed for the row drops by the reserved qty (R8) |
| RS-14 | `test_unlink_reserve_link_restores_remaining` | unlink -> remaining back, request stays `reserved`, chip clears |
| RS-15 | `test_request_context_shape_and_link` | keys per 3.6, `link` ends `?reserve=<id>`, dates dd/mm/yyyy |
| RS-16 | `test_recipient_order_request_and_reserved` | request: Eling first then requester, raiser; reserved: requester first then raiser; `include_raiser` / `include_requester` resolve + dedupe |
| RS-17 | `test_seed_migration_idempotent` | two templates, two automations, `one_email`, downgrade removes; CHECK widened and restored |
| RS-18 | `test_link_check_exactly_one_target` | link with two targets or none raises IntegrityError |
| RS-19 | `test_cancel_request_only_while_requested` | cancel open ok (`cancelled`), cancel reserved 409, deferred action registered |
| RS-20 | `test_reserve_state_derived` | serializer: open -> `requested`; reserved link -> `reserved`; none -> null; reserved then requested again -> `requested` |
| RS-21 | `test_rollback_discards_pending_dispatch` | request inside a rolled-back transaction dispatches nothing |
| RS-22 | vitest `ReserveRequestDialog.test.tsx` | defaults = remaining + pool, cannot exceed remaining, Send posts the contract shape |
| RS-23 | vitest `ReserveRequestsCard.test.tsx` | act mode: reason input appears when reserved < requested, Confirm disabled until filled; read-only without permission |
| RS-24 | vitest `OrderInquiryStockGrid.test.tsx` | `BRW-BB` -> `group=BB`; pool code -> `warehouse_id`; renders `CellStockTable` with subtotal |
| RS-25 | vitest `FulfilmentBoardListView.stock.test.tsx` | expanded row shows Stock tab with the grid |
| RS-26 | vitest `RecipientPicker.include_raiser.test.tsx` | both new checkboxes round-trip |

## 6. Verify while building (coder reports, does not guess)

1. Whether the OI lines serializer already carries `product_id` (the grid needs it; item code
   alone is not a key). If not, add it in the header-lines schema and the worklist row.
2. Whether `stock-detail` with `group=<suffix>` includes the pool row for that site (the dialog
   shows it under `Where = site_pool`). If not, a second call with the pool `warehouse_id`.
3. Whether `BoardLineDecisionPanel` already knows the cell's `productId` + `warehouseId`; the
   list-view Stock tab needs the same inputs the dialog gets.
4. `dispatch_event` dedupe by `source_id` (handover item 3 found none; re-confirm for two
   triggers sharing `source_kind`).

## 6b. Review round 1 (22 Sep, reviewer + security-reviewer on Opus): NOT READY, one fix round

Blockers: B1 the FE computed remaining from `linked_qty` (which excludes reserve links since
S2) without subtracting `reserved_qty`, so the second R5 cycle prefilled a qty the server 422s;
B2 (= SF-4) the reserve-requests GET was gated on acknowledge, locking a reserve-only CS head
out of her own card. Should-fix taken into the round: SF-1 cancel restricted to requester or
reserve holder (route + deferred action aligned); SF-2 duplicate `request_row_id` in a reserve
payload; SF-3 `warehouse_id` must be an active own-company warehouse on both writes; SF-5
reserve re-checks the row's live remaining; `po_ref` / `spo_ref` derivation skips reserve
links; act-mode inputs survive a parent re-render (AC-RS-28); no warehouse UUID as Location
text; duplicate `row_id` in a create payload and malformed body ids are 422 not 500; ordinal
mint tolerates a collision; migration names its constraints like the ORM; `stock_detail.locations`
and both templates get tests; dialog and card go through the mutation hooks; `notified_name`
comes from the service; nits (pill green, dd/mm/yyyy in the dialog, min 1, pool resolution
page size, downgrade deletes only the seeded automations, note <= 5000 / reason <= 2000).

Recorded, not built: DB-level guard for one open request row per OI row (app check + unique
per request today; trigger: a real double-open); subject CR/LF collapse belongs in
`EmailTemplateService.render` for every template (own small fix); admin / superadmin bypass
the reserve gate by repo convention; request / cancel spam by an authenticated insider.

## 6c. Review round 2 (owner hand test on :3080 after round 1, 22 Sep evening): five rulings

Owner words: "list all the site pool with this BRW (configurable as default)"; reserve at the line,
popup opens automatically, the reserve icon must be very clear; logs per line, in the same popup's
history tab; date-time like every other component; "unlink is unlink, unreserve is unreserve ...
unlink on a reserve link does nothing, unlink means unlink PO / SPO, cause the one doing the job
different so dangerous if they are the same".

**F1 Location = every site pool, configurable default.** Today `useReserveRowOptions` offers the
row's own group members plus its site pool (AC-RS-22), so a row at `BRW-IR` shows `BRW` alone.
New: options = every active own-company POOL warehouse (a code with no group suffix, the
`group=pools` axis of stock-detail), each labelled `<code>  available N` from one stock-detail
pools read for the row's product. Default = new `system_settings.oi_reserve_default_pool_warehouse_id`
(nullable FK, seeded to the `BRW` pool by code in the lane migration, editable on the System
Settings page as a clearable `SearchableSelect` of pools; null = the row's own site pool). Both
manual settings dict builders carry the field (lessons). SF-3 server check unchanged.

**F2 Reserve lives on the line.** `ReserveRequestsCard` (open-request card + "Earlier reserve
requests") is deleted. The Lines grid gets a **Reserve** cell: an icon-button (lucide `Bookmark`,
aria-label + tooltip "Reserve"), amber when `reserve_state = requested`, green when `reserved`,
absent otherwise; visible to every viewer, actionable only with `projects.order_inquiries.reserve`.
Click opens `ReserveRowDialog` for THAT row, tabs **Reserve** and **History** (F3). Reserve tab:
the open request line (Request #n, requested N by <name> on <date>, note), **Location** (F1),
**Reserved** (default `min(requested, available at the chosen pool)` floor 0, max requested),
**Reason** (required when short, inline as soon as the value drops), primary **Confirm reserved**;
**Cancel request** (requester or CS, countdown, existing endpoint) in the dialog header. A row
already reserved with no open request shows net reserved + pool and the **Unreserve** control (F5).
Without the permission the tab is read-only. `?reserve=<request_id>` auto-opens the dialog on
that request's first open row; closing drops the param, the icon stays. Header badge unchanged.
Backend: `POST .../reserve-requests/{id}/rows/{row_id}/reserve { warehouse_id, qty_reserved,
reason? }` answers ONE request row (3.3 validation per row); the request stays `requested` while
any row is unanswered and becomes `reserved` when the last one is; the `order_inquiry_reserved`
email fires ONCE, on completion, listing every row (R6). The all-rows endpoint of 3.3 is deleted
(one seam). Section 7 "partial answers" is superseded by this ruling.

**F3 History per line** = the dialog's History tab, newest first: `Requested N by X on <date>`
(from the request row), `Reserved N @ <pool> by Y on <date>  <reason>`, `Unreserved N by Z on
<date>  <note>`, `Request cancelled by X on <date>`. Storage: new table
`projects.order_inquiry_reserve_events` (id, company_id, reserve_request_row_id FK cascade, kind
`reserved` | `unreserved`, qty, warehouse_id, note, actor_id, created_at), written by reserve and
unreserve; requested / cancelled lines derive from the request row (no second copy). Net reserved
on the request row = sum(reserved) - sum(unreserved) = the reserve link's qty.

**F4 Dates** in the dialog, the history and the mails via the shared `formatDateTime` helper every
other component uses; no raw ISO text anywhere.

**F5 Unreserve is its own action; Unlink never touches a reserve.** `POST
.../reserve-requests/{id}/rows/{row_id}/unreserve { qty, note? }`, gate
`projects.order_inquiries.reserve`, `1 <= qty <= net reserved` else 422 naming the limit; reduces
the reserve link qty by `qty` (deletes the link at 0), `refresh_link_state`, one `unreserved`
event, no email. Unlink (bulk deferred action and per-row) SKIPS reserve links: the per-row Unlink
is not offered on a reserve link and the bulk action ignores them; 3.3 "Reversal" is superseded.
Section 7 "amend a reserved qty" is superseded: top-up = new request, reduce = Unreserve.

## 6d. Round 3 (owner hand test after #1120 shipped, 23 Sep): five asks, one fix lane

Branch `fix/oi-reserve-round3` off main 7c2c8e342 (no migration, no auth change). Owner words:
"the link only opens 1 popup ... can't it open all the items here?"; "after reserved it is called
On PO/SPO which is kinda sus, it should be called reserved"; "combine the reserve icon with the
state ... adding too many columns also not good"; "after confirmed the product should have a
ticked icon"; the grip on the expand header; "the location column too big, can we resize this and
make it remembered"; "I can't scroll horizontally when I place my cursor here and shift scroll".

**G1 Email link opens every row of the request.** `?reserve=<request_id>` opens ONE
`ReserveRowDialog` carrying every still-open row of that request (`rows: [...]`, one section per
row: item code, Location, Reserved, Reason-when-short, its own **Confirm reserved**), not the first
open row alone. Each Confirm still calls the per-row endpoint (AC-RS-56 unchanged); a confirmed
section flips to a read-only `Reserved N` line with the tick; the dialog closes itself once the
last section is confirmed. The line-click path passes ONE row and keeps the History tab; the
multi-row path has no History tab (history lives on the line). One component, `rows` length 1..N.

**G2 State column carries the reserve state; the Reserve column goes.** In
`orderInquiryHeaderLinesColumns.tsx` the `state` cell renders, in this order: `reserve_state ===
'requested'` -> amber pill `Request to reserve`; `reserve_state === 'reserved'` -> green pill
`Reserved N` with a lucide `Check` icon (the owner's tick); else `OrderInquiryStatePill` as today.
Both reserve pills are the click target (`role=button`, aria-label `Reserve`) opening the dialog
for that row, replacing the `reserve` column, which is deleted. `ReservePill` in
`OrderInquiryVerbPill.tsx` gains `onClick?` (rendered as a button when set) and the tick on
`reserved`; the worklist keeps its read-only usage. `STATE_LABEL` untouched (one map, AC-B5-2).

**G3 No grip on fixed utility headers.** `DataGridTableDndHeader` renders no `GripVertical` and
passes `disabled: true` to `useSortable` when `columnDef.meta?.draggable === false` OR the column
carries `meta.expandedContent`; the shared select column (`data-grid-select-column.tsx`) sets
`meta.draggable = false`. `ColumnMeta` gains `draggable?: boolean`. Not keyed on `enableHiding`
(real data columns use it in 12 grids).

**G4 Expanded content stays inside the viewport and the page scrolls sideways over it.** Two
causes, both measured on origin/main. (a) `DataGridTableBodyRowExpandded` puts the content in a
`<td colSpan=all>` as wide as the whole fixed-layout table, so on a grid wider than its scroll
container the inner `CellStockTable` (Location = `w-full` slack column) stretches past the right
edge and its number columns sit off-screen: fix = the expanded `<td>` wraps content in a
`sticky left-0` div whose `max-width` is the DataGrid scroll container's clientWidth (a CSS
variable set by one `ResizeObserver` on the container; every `expandedContent` site benefits, the
nested-inventory tests enumerate them). (b) `CellStockTable`'s wrapper is `overflow-x-auto
overscroll-x-contain`: an `overflow:auto` box is a scroll container even without overflow, and
`overscroll-behavior: contain` on it stops wheel / trackpad chaining to the parent grid's
scroller, so shift-wheel and two-finger swipes over the stock table do nothing (the same trap
`data-grid-table.tsx:171` records for the grid itself). Fix = drop `overscroll-x-contain` there.

**G5 Location column resizable, remembered per browser.** `CellStockTable` Location `<th>` gets a
drag handle (same `cursor-col-resize` affordance as `DataGridTableHeadRowCellResize`); the width
(px, floor 120) is held in component state, applied to the Location cells (`truncate` + `title`
on the code), and remembered in `localStorage` key `cellStockTable.locationWidth` (read/write in
try/catch; absent = today's slack behaviour). One column, one key: no column-config API row.

**G6 Multi-row dialogs are tables, not stacked cards (owner, 23 Sep on :3080: "more tabulated to
save space, later I got 10 products to request to reserve, then gg, we should use standard
datagrid table in the system").** Both multi-row dialogs render one DataGrid row per product
(`tableLayout: { width: 'fixed', columnsResizable: true }`, `columnResizeMode: 'onChange'`,
explicit `size` per column, no pagination, no sort, no column config):

- `ReserveRowDialog` (CS acting, `rows.length > 1`): columns Product | Requested | Location
  (`SearchableSelect`) | Reserved (number `Input`) | Reason (`Input`, enabled the moment Reserved <
  Requested) | action (`Confirm reserved` per row). A confirmed row's Reserved cell reads
  `Reserved N` with the tick and its inputs are gone. Footer: `Confirm all` (enabled when every
  still-open row is valid, i.e. reason present wherever short) posting the per-row endpoint row by
  row, top to bottom, stopping on the first failure (rows already confirmed stay confirmed; the
  failed row shows the error toast). Dialog width `sm:max-w-4xl`; at 375px the grid scrolls
  sideways inside the dialog body.
- `ReserveRequestDialog` (purchasing raising): columns Product | Delivery date | Remaining | Requested
  (number `Input`) | Location (`SearchableSelect`). Note stays below the grid. Same width.
- The single-row `ReserveRowDialog` keeps its form + History tabs (one row, nothing to tabulate).
- `AC-RS-74`, `AC-RS-75`. Existing behavioural tests (AC-RS-22, 65..67, 66b, R1/R2, N1/N2) stay
  green: same props, same callbacks, same endpoint calls; only the layout changes.

Coder verifies G4 live on :3080 before writing the fix (a screenshot of the expanded row on a
grid wider than the viewport, then the same after) and reports if either cause is not the one
measured. Tests: AC-RS-65..72 below, tester-first.

**Fix round 1 (23 Sep, per-row pool resolution).** G1's first pass resolved Location options /
availability / default off the PRIMARY row alone and shared that one set across every section of
a multi-row dialog - wrong the moment two rows name different products. `useReserveRowOptions`
already resolves N entries through `useQueries` (`useReserveRowOptions.ts` L90), so this is
wiring only: `ReserveRowDialogRow` gains optional per-row `locationOptions` /
`availableQtyByLocation` / `defaultLocationId` (falling back to the dialog's own top-level prop
when absent); `OrderInquiryDetail.tsx`'s `reserveRowOptionsEntries` covers every id in
`reserveDialogRowIds` (not just the primary), and each row's own resolved entry is threaded into
its own `ReserveRowDialogRow`. History / Cancel request / Unreserve stay off the primary row only
(single-row mode). AC-RS-65b/AC-RS-66b.

## 6e. Round 4 (owner hand test of round 3 on :3080, 24 Sep): CS reserves line by line, like the board

Owner words: "I shouldn't need to confirm line by line, just enter the quantity I want to reserve and
confirm all ... the decision is not committed until I click confirm at the bottom, and I can always
revise my decision, be it unreserve or change quantity ... can our experience be similar to
fulfilment planning because the one doing is CS ... at each line it writes request to reserve, then
once I click a tick icon it pops up the location and quantity ... I can undo also before I click the
CTA ... when CS clicks the link it just sees those that require reserving, so we should have a
filter ... for CS they see 'Reserve' ... after clicking Reserve the button should be grayed out."

**Rulings (owner, 24 Sep):** R4-1 the reserved mail goes out on every `Reserve` click, naming the
lines committed in that click; the request stays open for untouched lines. R4-2 icons on a
requested line: **tick** = reserve the full requested qty at the default pool (no form); **pencil**
= form (Location, Reserved 0..requested, Reason required when short; 0 = no reserving at all);
**undo** drops the staged decision. R4-3 amend after commit is allowed: pencil on a reserved line
stages a new qty (0..requested, location locked), committed by the same CTA. R4-4 no header
badge, no multi-row dialog, no `Confirm all`: the Lines grid is the surface.

### 6e.1 Backend: one commit call per `Reserve` click

`POST /api/v1/project-sales/order-inquiries/{inquiry_id}/reserve-requests/{request_id}/commit`
(permission `projects.order_inquiries.reserve`), payload

```
{ "reserves":   [{ "row_id", "warehouse_id", "qty_reserved", "reason" }],   // open rows
  "amendments": [{ "row_id", "qty_reserved", "reason" }] }                   // answered rows
```

One transaction. `reserves` reuse `reserve_row` (validation per 3.3 / AC-RS-56, `dispatch=False`);
`amendments` set the row's net reserved to `qty_reserved` (0..qty_requested; location locked to
the answered row's `warehouse_id`): a decrease reuses `unreserve_row` for the delta, an increase
raises the reserve link qty by the delta (re-creating the link when it was deleted at 0) and writes
one `reserved` event for the delta; `reason` required whenever the new qty is short of requested.
Empty payload = 422. Any invalid row = 422 naming it, nothing written. After the batch: request
`state = reserved` when every row is answered, else stays `requested`; ONE
`order_inquiry_reserved` dispatch per call whose `reserve.rows` are the rows touched in this call
(reserved / amended, each with `qty_reserved`, `balance`, `reason`), plus `reserve.row_count` for
the request and `reserve.open_row_count` remaining. The per-row `.../rows/{row_id}/reserve` and
`.../unreserve` routes are retired (404); the deferred action `order_inquiry_reserve_row.unreserve`
is removed from the registry; `history` and the request GET stay. The reserved-mail template gets
a line `N line(s) still to reserve` when `open_row_count > 0`.

### 6e.2 Frontend: staged decisions on the Lines grid, one `Reserve` CTA

- `ReserveRowDialog.tsx` (multi-row grid, `Confirm all`, single-row tabs) is deleted. Two small
  pieces replace it: `ReserveLineForm` (dialog: item code title, Location `SearchableSelect`,
  Reserved number, Reason shown when short; primary **Stage**, nothing posted) and
  `ReserveLineHistoryDialog` (the former History tab content, read-only).
- Lines grid State cell (AC-RS-68 kept): `Request to reserve N` (N = qty_requested) amber,
  `Reserved N` + tick green. The pill is no longer a button.
- New `reserve` action cell (after State; only rendered when the viewer holds the reserve
  permission AND the inquiry has an open request or a reserved line; icon buttons with
  aria-labels): requested line -> **Reserve** (tick: stages `{qty: requested, warehouse: default
  pool}`) and **Edit reserve** (pencil: opens `ReserveLineForm`); reserved line -> **Amend reserve**
  (pencil: form with location locked, qty prefilled net) and **History** (info). A staged line
  shows a dashed outline chip `Reserve N @ BRW` (or `Reserve 0`, or `Amend to N`) in place of the
  icons plus **Undo** (drops it). Staged state lives in `OrderInquiryDetail` (`Record<rowId,
  StagedReserve>`), cleared on commit; a reload loses it (trigger for server drafts: CS asks to
  stage across sessions).
- Header CTA: beside `Confirm`, a **Reserve** button (visible with the reserve permission while a
  request is open or anything is staged; enabled only when staged count > 0; label `Reserve (N)`).
  Click -> POST commit with the staged rows split into `reserves` / `amendments`; toast
  `Reserved, <requester> notified`; invalidate lines + requests; staged cleared; button greys.
  `Cancel request` (deferred countdown, requester or permission holder) moves to the Actions menu.
- Filter: a `SearchableMultiSelect` **State** filter beside the product search on the Lines tab
  (options = `STATE_LABEL` values + `Request to reserve` + `Reserved`, clearable). `?reserve=<id>`
  no longer opens anything: it preselects `Request to reserve` in the filter and is removed from
  the URL on the first filter change; the header badge is gone.
- Purchasing `ReserveRequestDialog` grid (G6) stays; it gets `columnsDraggable: false`, loses the
  inert outer `overflow-x-auto` wrapper, and the `data` identity comment is corrected (review 24 Sep).
- Deleted with the dialog: `useReserveOrderInquiryRow`, `unreserveOrderInquiryRow`,
  `reserveRequestCompletes` (the server decides), the `?reserve=` latch, AC-RS-65..67, 73, 74 and
  the round-2/3 dialog tests (superseded rows marked in the UAC).

### 6e.3 Tests (tester-first)

Backend `tests/test_order_inquiry_reserve_commit.py`: AC-RS-76..82. Frontend: AC-RS-83..90 in
`OrderInquiryDetail.reserveStaging.test.tsx`, `ReserveLineForm.test.tsx`,
`orderInquiryHeaderLinesColumns.test.tsx`, `OrderInquiryLinesTab.test.tsx`.


### 6e.4 Review round (24 Sep, reviewer + security-reviewer on Opus): NOT READY, one fix round

Rulings folded (captain):

- **Route keyed by inquiry, rows resolved server-side.** `POST /api/v1/project-sales/order-inquiries/{inquiry_id}/reserve-commit` replaces `.../reserve-requests/{request_id}/commit`. `reserves[].row_id` resolves to the OI row's OPEN request row (unique by the partial index), `amendments[].row_id` to its LATEST answered request row, both within `inquiry_id` (404 otherwise). One transaction; one `order_inquiry_reserved` dispatch per REQUEST touched (normally one), each naming only its own touched rows. Reason: a line from a finished request is amended while another request is open (reviewer B2), and the URL's `inquiry_id` was validated then ignored (security S1).
- **Amend-up cap** = `min(qty_requested, current_link_qty + live remaining of the row)`; 422 naming the row (reviewer B1 / security B2: links exceeded row qty with a PO covering the balance).
- **Duplicate `row_id`** across `reserves + amendments` = 422 before any read; the reserve link insert keeps its IntegrityError -> 409 wrapper (security B1 / reviewer S3).
- **Locks**: `with_for_update()` on the request(s) in commit and in `cancel_request`; row locks ordered by id (security S2 / reviewer S6).
- **Cancel semantics** (security S3): cancel stays allowed on a partly answered request and withdraws only the still-open rows; answered rows keep their links and may still be amended (`amendments` accepted on a cancelled request, `reserves` 409).
- **Declined lines**: a row whose latest answered request row has `qty_reserved = 0` reads `reserve_state = declined`; pill `Not reserved` (neutral), actions Amend + History, so the "0 -> up" path is reachable (reviewer S5). Reserve 0 writes a `reserved` event with qty 0 so History shows the decision (security N3).
- **No-op amendment** (delta 0) is skipped: not touched, no event, no mail, reason untouched (security N2).
- `_open_request_row_ids` gains `qty_reserved IS NULL` (reviewer S4); `_OPEN_REQUEST_QTY` takes `.limit(1)`.
- `reserve_row` is deleted; `commit_request` owns validation through one shared validator; tests that called it move to `commit_request` (reviewer S9).
- Frontend: amend prefill = the anchor request row's own qty, clamped to its requested (B3); form reason rule = `qty < requested`, in both modes (S1); the form renders after the pool options load so the prefill is never 0 (S2); a staged reserve without a warehouse is sent without one (server defaults) (S8); the action column only renders when the inquiry has an open request or a reserved / declined line, and its header carries no grip (nit); the State filter drops `Cancelled` and its empty state reads `No line matches the filter.`; `?reserve=` removal gets its own test (B5).
- Measured while building (coder, 24 Sep): the events table's `ck_order_inquiry_reserve_events_qty_positive` was `qty > 0`, so the Reserve 0 event needed one migration, `oirs_0004_reserve_event_zero` (`qty >= 0`). There is no DB constraint behind "one open request row per line" (the parent state lives on another table); `create_request`'s `_open_request_row_ids` is the rule, and the readers take the newest open row.
- **Amend edits the LINE's net (re-review S1, captain ruling 24 Sep).** The pill shows the line's net reserved across every request; the Amend form edits that same number. `amendments[].qty_reserved` = the new net for the line: a decrease releases reserve links newest first (the old `unreserve_row` order), one `unreserved` event per link touched; an increase raises the latest answered request row's link (re-created at 0), one `reserved` event; cap = `current net + live remaining of the row`; a reason is required whenever the new net is below T = net held by every answered request row except the latest + the latest answered row's `qty_requested`, capped at the line qty (a balance request is counted once, not on top of the shortfall it re-asks). The form prefills the net and states `Requested T across N requests` when N > 1. The State filter gains `Not reserved`. The duplicate-row 422 names the item code.
- Evidence rerun of the AC-RS-90 script in full (request three lines, follow the link, preselect shown); the Next dev "1 Issue" badge in two captures is explained or fixed; outbox rows are never sent from the lane (`ENABLE_SCHEDULER=false`, 0 sent, captain-verified 24 Sep).

## 7. Out of scope (recorded, not built)

- AutoCount stock transfer creation / transfer number on the reserve row. Trigger: the FoundryX
  gateway gains a write path.
- Partial answers to one request (answer some rows now, others later). Trigger: Eling asks.
- Amend a reserved qty. Reversal is Unlink; top-up is a new request.
- A `StockTransfer` paper row for the reserve. Trigger: the warehouse asks for the paper trail on
  OI-driven reserves like it has for board decisions.
- Taken / Remaining columns on the OI Lines tab + worklist with footer sums: already ruled in
  `PLAN-board-oi-mechanical-22sep.md`; this lane only adds `reserved_qty` to those figures.

## 8. After merge

Owner adds Eling to the request automation's users, ticks nothing else (seed already sets the Cc
options). Guide: "Ask CS to reserve stock" section in the purchasing OI guide + "Reserve for
purchasing" in the CS guide; Outline push by the owner.
