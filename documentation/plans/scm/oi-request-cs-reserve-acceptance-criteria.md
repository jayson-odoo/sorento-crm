# UAC - Order inquiry: Request CS to reserve stock (+ stock grid on OI lines and board list)

Plan: `PLAN-oi-request-cs-reserve.md`. Rulings R1-R11, owner, 22 Sep 2026.

## Journey

**Purchasing (Joey).** Opens `OI-2609-0678` from the order inquiries list. On the Lines tab she
expands `B2155-NL-BLUE` and sees the same stock grid the board shows (BRW-NTC -1777 available,
MWH-NTC 335, WH3-NTC 142, NTC group subtotal). She ticks three rows, Actions -> **Request CS to
reserve**. The dialog lists the three rows with Requested = remaining and Location = BRW (the pool
of BRW-BB). She lowers one, presses **Send request**. Toast: `Request #1 sent to Eling`. The rows
now wear `Request to reserve`; a card above the grid shows the open request with a Cancel
countdown. ONE email leaves: To Eling, Cc Joey and the raiser, subject
`Reserve request: OI-2609-0678 #1 - SO402757`, with a link.

**CS head (Eling).** Clicks the link, logs in, lands on the OI detail page with the request card
in act mode. For each row: Location (prefilled BRW, changeable), Reserved (prefilled with what
BRW can give, capped at requested), the stock grid a chevron away. Where she reserves less than
asked a Reason box appears and blocks Confirm until filled. **Confirm reserved**. Toast
`Reserved, Joey notified`. One email leaves: To Joey, Cc the raiser, subject
`Reserved: OI-2609-0678 #1 - SO402757`, the table now with RESERVED and REASON.

**Joey again.** Rows read `Reserved 50`; Taken includes the 50, Remaining is the balance she buys
by PO or SPO as today. Later she can request again on the remaining. The board plans only the
balance because the row's owed demand already dropped by 50.

**Board planner.** On the fulfilment board LIST view, expanding a line shows the same Stock /
Contributing lines tabs the grid view's dialog shows.

## Slice 1 - stock grid (FE, live endpoint)

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-RS-40 | [FE] | Given the OI Lines tab, when the user clicks a row's chevron, then a stock grid renders inline under the row with columns Location, Where, On hand, SO qty, SPO qty, Available, Available for Project, PO qty, Taken, the `<group> group subtotal` row, and each location expandable into the documents panel (Type, Document, Customer / supplier, Agent, Delivery / expected, Bin, Quantity, Balance). |
| AC-RS-41 | [FE] | Given a row at location `BRW-BB`, then the grid is fetched with `group=BB`; given a row at a bare pool code (`BRW`), then with that pool's `warehouse_id`. Product = the row's product id (never the item code string). |
| AC-RS-42 | [FE] | Given the fulfilment board LIST view, then each line row carries a `Stock` icon-button (labelled) and its "To plan" figure is clickable; either opens the grid view's `BoardCellBreakdownDialog` for that line, unchanged (Stock + Contributing lines tabs). The expanded decision panel is untouched. (Pending Q3: if the owner prefers inline, the grid renders below the decision block inside the expanded row instead.) |
| AC-RS-43 | [FE] | Given 375 px and 1280 px, then the inline grid scrolls horizontally inside the row and never clips the page. |

## Slice 2 - request

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-RS-1 | [BE] | Given three requestable rows on one inquiry and one `POST .../reserve-requests`, then one request (`ordinal 1`, `state requested`, `requested_by/at` = actor / now) and three request rows are written, and `dispatch_event("order_inquiry_reserve_requested", ...)` is called exactly ONCE, after commit, with `reserve.row_count = 3` (R9). |
| AC-RS-2 | [BE] | Given a row at `BRW-BB` and no `warehouse_id` in the payload, then the request row's `warehouse_id` = BRW (its `pool_warehouse_id`); given a row whose location is itself a pool, then the location itself (R3). |
| AC-RS-3 | [BE] | Given a row qty 100 with 40 linked, then `qty_requested` 61 is rejected 422 naming the row and 60 is accepted; 0 or negative is rejected 422 (R10). |
| AC-RS-4 | [BE] | Given a row that already has an open request row, or whose verb is not ORDER / ORDER_BACK, or whose state is actioned / cancelled / placed, or that belongs to another inquiry, then the call is rejected 409 naming the row and nothing is written. |
| AC-RS-5 | [BE] | Given a row reserved 50 of 139 on request #1, then a new request on the 89 remaining is accepted as `ordinal 2` (R5). |
| AC-RS-19 | [BE] | Given an open request, when the requester (or a holder of the reserve permission) cancels it, then `state cancelled`, `cancelled_by/at` set, no email; cancelling a `reserved` request is 409. The action is registered as deferred action `order_inquiry_reserve_request.cancel` (reversible window). |
| AC-RS-20 | [BE] | The lines serializer (header lines + worklist) returns `reserve_state` per row: `requested` while an open request row exists, else `reserved` when `reserved_qty > 0`, else `null`; and `reserved_qty` = sum of the row's reserve links. A row reserved then requested again reads `requested`. |
| AC-RS-21 | [BE] | Given a request written inside a transaction that rolls back, then nothing is dispatched and the pending queue is empty for the next commit. |
| AC-RS-15 | [BE] | The request context is `{ reserve: { inquiry_no, ordinal, so_number, customer, project, requested_by {name,email}, requested_at, rows [{item_code, delivery_date, qty, remaining, qty_requested, location, qty_reserved, reason}], row_count, state, link }, actor, raiser, requester, today }`; dates dd/mm/yyyy, quantities without trailing decimals, `link` = `<FRONTEND_BASE_URL>/project-sales/order-inquiries/<id>?reserve=<request_id>`. |
| AC-RS-16 | [BE] | Given the seeded request automation with `user_ids [Eling]`, `include_actor true`, `include_raiser true`, `one_email true`, then ONE outbox row is enqueued with To = Eling and Cc = requester + raiser (deduped when the same person). `include_raiser` / `include_requester` are normalised as bools and resolve from `raiser.email` / `requester.email`. |
| AC-RS-17 | [BE] | The migration creates both tables, widens `ck_order_inquiry_links_one_target` to three targets, seeds templates `order_inquiry_reserve_requested_default` and `order_inquiry_reserved_default` and two automations (`Order inquiry: request CS to reserve`, `Order inquiry: reserved by CS`, both enabled, `one_email true`, recipient configs per plan 3.6), idempotently. Downgrade removes the seeds, the reserve links, the column, both tables, and restores the two-target CHECK. |
| AC-RS-18 | [BE] | Given a link with two targets set, or none, then the insert fails with an integrity error; a link with only `reserve_request_row_id` inserts. |
| AC-RS-30 | [BE] | Given the seeded request template rendered with a fixture context, then subject `Reserve request: OI-2609-0678 #1 - SO402757`, an HTML table with ITEM CODE, DELIVERY DATE, QTY, REMAINING, REQUESTED, LOCATION, every cell with inline `border` and `padding`, the requester's name and the link in the footer; text body carries the same table. Null prints blank, never `None`. |
| AC-RS-22 | [FE] | Given rows selected on the Lines tab, when Actions -> **Request CS to reserve** opens, then each row shows item code, delivery date, remaining, Requested = remaining (max remaining, min 1), Location = the pool (SearchableSelect, clearable off since required, options = the row's stock-grid locations), a chevron opening the stock grid, and an optional note; Send posts `{ rows: [{row_id, qty_requested, warehouse_id}], note }` and toasts `Request #<ordinal> sent to <first To name>`. |
| AC-RS-23 | [FE] | Given a selection containing a non-requestable row (open request, remaining 0, wrong verb / state), then the menu item is disabled with a tooltip naming the first reason. |
| AC-RS-24 | [FE] | SUPERSEDED by AC-RS-61 + AC-RS-62 (card retired; Cancel request lives in the dialog header). Was: Given an open request, then the Lines tab shows `ReserveRequestsCard` above the grid: rows with requested qty + location, who / when, and for the requester (or a reserve-permission holder) a **Cancel request** button that becomes the standard reversible countdown; the card lists earlier reserved / cancelled requests collapsed with reserved qty + reason. No open or past request -> no card. |
| AC-RS-25 | [FE] | Rows with `reserve_state requested` show an amber `Request to reserve` pill beside the state pill; `reserved` shows a green `Reserved <qty>` pill; on both the Lines tab and the worklist lines view. The detail header shows a `Request to reserve` badge while a request is open. |

## Slice 3 - reserve

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-RS-6 | [BE] | SUPERSEDED by AC-RS-56 (per-row reserve, round 2). Was: Given an open request and `POST .../reserve` with reserved 50 on a row asking 139, then one `OrderInquiryLink` is written with `reserve_request_row_id`, `document "Reserved @ BRW"`, `qty 50`, `linked_by` = actor, `auto false`, `refresh_link_state` moves the row to `partly_linked`; reserving the full requested qty on a row with nothing else linked moves it to `placed`; the request becomes `reserved` with `reserved_by/at`, and `dispatch_event("order_inquiry_reserved", ...)` fires ONCE after commit. |
| AC-RS-7 | [BE] | SUPERSEDED by AC-RS-56 (same rule, per row). Was: Given a row answered 0 without a reason, then 422 naming the row and nothing written; with a reason, accepted, no link written, `qty_reserved 0` stored (R2). |
| AC-RS-8 | [BE] | SUPERSEDED by AC-RS-56 (same rule, per row). Was: Given 30 reserved of 50 requested without a reason, then 422; 50 of 50 without a reason is accepted; 51 of 50 is 422. |
| AC-RS-9 | [BE] | SUPERSEDED by AC-RS-56 + AC-RS-57 (rows answered one call each). Was: Given the payload omits one of the request's rows, then 422 and nothing written (all rows answered in one call). |
| AC-RS-10 | [BE] | SUPERSEDED by AC-RS-56 (gate unchanged, per-row route). Was: Given a user without `projects.order_inquiries.reserve` (the requester included), then 403; the slug is present in `PERMISSION_REGISTRY` and seeded by `sync_permissions`. |
| AC-RS-11 | [BE] | SUPERSEDED by AC-RS-56 (409 on an already-answered row). Was: Given a request already `reserved` or `cancelled`, then a second reserve call is 409. |
| AC-RS-12 | [BE] | Given a row qty 139 with a PO link 40 and a reserve link 50, then the worklist quantity flow reads Taken 90, Remaining 49, `reserved_qty 50`; the PO breakdown reads 40 and the SPO breakdown 0 (reserve links never leak into the PO / SPO figures); `po_ref` / `spo_ref` derivation skips reserve links. |
| AC-RS-13 | [BE] | Given the same row, then `scm.committed_v` owed for it drops by the reserved 50 exactly as it does for the PO 40 (R8); `scm.on_order_v` is unchanged. |
| AC-RS-14 | [BE] | SUPERSEDED by AC-RS-58 + AC-RS-59 (Unreserve is its own action; Unlink never touches a reserve). Was: Given a reserve link, when it is unlinked through the existing unlink path (bulk deferred action or per-row), then Remaining rises by the qty, `reserve_state` clears, and the request stays `reserved` as history. |
| AC-RS-31 | [BE] | Given the seeded reserved automation (`include_requester true`, `include_raiser true`, `one_email true`), then ONE outbox row with To = requester, Cc = raiser; the rendered subject is `Reserved: OI-2609-0678 #1 - SO402757` and the table reads ITEM CODE, QTY, REQUESTED, RESERVED, BALANCE, LOCATION, REASON, where BALANCE = the row's remaining after this reserve (qty - all links - bundled), the figure purchasing still buys. |
| AC-RS-32 | [BE] | Eling's `warehouse_id` change is stored on the request row and printed as `location` in the reserved mail and in the link `document`. |
| AC-RS-26 | [FE] | SUPERSEDED by AC-RS-61 + AC-RS-62 + AC-RS-55 (dialog replaces act mode; toast wording kept). Was: Given `?reserve=<id>` on the OI detail URL, or an open request while the viewer holds the reserve permission, then `ReserveRequestsCard` renders in act mode: per row Location (SearchableSelect, prefilled), Reserved (number, default `min(requested, available at the chosen location)` floored at 0, max requested), the stock-grid chevron; a Reason input appears inline the moment Reserved < Requested and **Confirm reserved** stays disabled until every such row has a non-blank reason. Confirm posts `{ rows: [{request_row_id, warehouse_id, qty_reserved, reason}] }` and toasts `Reserved, <requester> notified`. |
| AC-RS-27 | [FE] | SUPERSEDED by AC-RS-62 (read-only dialog). Was: Given a viewer without the reserve permission, then the same card renders read-only (no inputs, no Confirm). |
| AC-RS-28 | [FE] | Given the Location on a row is changed, then the Reserved default recomputes from that location's available figure only if the user has not edited Reserved yet. |
| AC-RS-29 | [FE] | Automation form: the recipient picker shows "Cc the person who raised the inquiry" (`include_raiser`) and "Cc the person who requested" (`include_requester`) beside "Cc the person who raised it"; each round-trips on edit. |
| AC-RS-33 | [FE] | The dialog and the card are usable and unclipped at 375 px and 1280 px; the dialog body scrolls on mobile with the footer fixed. |

## Slice 4 - review + guide + evidence

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-RS-50 | [E2E] | agent-browser evidence run, navigated from `/` by sidebar: Joey requests (3 rows, one lowered), one outbox row appears; Eling (second user with the permission) opens the link, reserves 50 / 0 with reason / full, confirms; Joey's page shows `Reserved 50`, `Request to reserve` cleared, Taken / Remaining updated; second request on the balance accepted. Screens saved under `documentation/plans/scm/evidence/oi-request-cs-reserve/`. |
| AC-RS-51 | [E2E] | Board list view: the Stock button on a line opens the cell dialog with the grid; grid view dialog unchanged. |
| AC-RS-52 | [DoD] | reviewer (Opus) with kill tests on AC-RS-1, AC-RS-8, AC-RS-13; security-reviewer (Opus) on the new permission gate, the widened CHECK and the email context (no UUID or secret in the mail beyond the request id in the link); guide sections written; alembic single head re-gated on every push. |

### Round 2 (plan 6c, owner rulings 22 Sep evening)

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-RS-53 | [BE] | Given pools BRW, DC1, WH3 active and a group warehouse BRW-IR, When the reserve dialog's location options are read for a row at BRW-IR, Then every active own-company pool is offered (BRW, DC1, WH3) with its available qty for the row's product, and no group warehouse; an inactive pool is absent. |
| AC-RS-54 | [BE] | `system_settings.oi_reserve_default_pool_warehouse_id` exists after the migration, seeded to the BRW pool by code; it is present in BOTH settings payload builders; PUT accepts a pool id or null and refuses a non-pool warehouse with 422. |
| AC-RS-55 | [FE] | The dialog's Location defaults to the configured pool; when the setting is null it defaults to the row's own site pool; changing it recomputes the Reserved default from that pool's available qty (AC-RS-28 kept). |
| AC-RS-56 | [BE] | `POST .../reserve-requests/{id}/rows/{row_id}/reserve` answers one row: validation per 3.3 (qty bounds, reason when short, active own-company warehouse), 404 on a row of another request, 409 on an already-answered row; the request stays `requested` with one row unanswered and turns `reserved` on the last answer; `order_inquiry_reserved` dispatches exactly once, on completion, with every row in the context. |
| AC-RS-57 | [BE] | The former all-rows reserve endpoint no longer exists (404 / 405). |
| AC-RS-58 | [BE] | `POST .../rows/{row_id}/unreserve { qty, note? }`: needs `projects.order_inquiries.reserve`; `qty` 0 or above net reserved is 422 naming the limit; success reduces the reserve link qty, deletes the link at 0, refreshes the row state, writes one `unreserved` event, sends no email; Taken / Remaining on the row follow. |
| AC-RS-59 | [BE] | Unlink (bulk deferred action and per-row) leaves reserve links untouched: unlinking a row that holds a PO link and a reserve link removes the PO link only; a per-row Unlink against a reserve link id is refused. |
| AC-RS-60 | [BE] | History for a request row lists, newest first: requested, reserved (qty, pool, reason), unreserved (qty, note), cancelled, each with actor name and timestamp; net reserved equals reserved minus unreserved. |
| AC-RS-61 | [FE] | Lines grid: a Reserve icon-button with aria-label "Reserve" appears on rows with `reserve_state` requested (amber) or reserved (green) and on no other row; click opens `ReserveRowDialog` for that row with tabs Reserve and History; `ReserveRequestsCard` and "Earlier reserve requests" no longer render. |
| AC-RS-62 | [FE] | `?reserve=<request_id>` auto-opens the dialog on that request's first open row; closing it removes the param and the icon remains; without the reserve permission the Reserve tab is read-only and the Unreserve control is absent. |
| AC-RS-63 | [FE] | Every date-time in the dialog and the history renders through the shared `formatDateTime` helper (no `T`-separated ISO text, no microseconds). |
| AC-RS-64 | [E2E] | agent-browser on :3080, from `/` by sidebar: Eling opens the OI from the email link, the dialog opens on the first open row, she reserves at DC1 with a reason; the row shows `Reserved N`; she unreserves part, History shows reserve then unreserve, net matches; Unlink on that row is unavailable for the reserve. Screens saved under the evidence dir. |

### Round 3 (plan 6d, 23 Sep, owner hand test after #1120 shipped)

| # | Layer | Given / When / Then |
| --- | --- | --- |
| AC-RS-65 | [FE] | Given `?reserve=<request_id>` on the OI detail URL and the request has two open rows and one already-reserved row, then ONE `ReserveRowDialog` opens with two sections (one per open row: item code, Location, Reserved, Confirm reserved) and no History tab; supersedes the "first open row" clause of AC-RS-62. Closing removes the param. |
| AC-RS-66 | [FE] | Given the multi-row dialog, when one section's Confirm reserved posts (per-row endpoint, payload as AC-RS-56), then that section reads `Reserved N` with the tick and its inputs are gone, the other section stays editable; when the last open section confirms, the dialog closes and the reserved toast shows once per confirm. |
| AC-RS-67 | [FE] | Given the dialog opened from a line (one row), then it renders tabs Reserve and History exactly as before (AC-RS-61 dialog contents unchanged). |
| AC-RS-68 | [FE] | Lines grid: no column with id `reserve` exists; the `state` cell of a row with `reserve_state requested` renders an amber `Request to reserve` pill that is a button (aria-label `Reserve`), a row with `reserve_state reserved` renders a green `Reserved <qty>` pill with a `Check` icon that is a button (aria-label `Reserve`), and a row with `reserve_state null` renders the plain `OrderInquiryStatePill` (`On PO/SPO` for `placed`, etc.) with no button. Clicking either reserve pill calls `onReserveClick` with that row. |
| AC-RS-69 | [FE] | `DataGridTableDndHeader`: a column with `meta.draggable === false` or with `meta.expandedContent` renders no `GripVertical` and no `aria-label="Drag column to reorder"` wrapper (sortable disabled); a normal column still renders both. The shared select column sets `meta.draggable = false`; the OI Lines `expand` column header therefore shows no grip. |
| AC-RS-70 | [FE] | `DataGridTableBodyRowExpandded` wraps `expandedContent` in an element with `position: sticky; left: 0` whose `max-width` tracks the DataGrid scroll container's clientWidth (CSS variable set by a ResizeObserver on the container; jsdom: the variable is set from `clientWidth` on mount and on observer callback). `CellStockTable`'s wrapper carries `overflow-x-auto` and NOT `overscroll-x-contain`. |
| AC-RS-71 | [FE] | `CellStockTable` Location header renders a resize handle; dragging it (pointerdown / pointermove / pointerup) sets the Location column width in px, never below 120; the width is written to `localStorage['cellStockTable.locationWidth']` and read back on the next mount; with no stored value the column keeps today's `w-full` slack class; a throwing `localStorage` leaves the table rendering. |
| AC-RS-73 | [FE] | Given an open reserve request, then the detail header's `Request to reserve` badge is a button (aria-label `Open reserve request`) that opens the multi-row `ReserveRowDialog` carrying every still-open row of that request, exactly as the `?reserve=` link does (no URL param written); after the dialog closes the badge reopens it; with no open request the badge is absent. Owner ask 23 Sep: "after I close the dialog, how do I reopen it back?". |
| AC-RS-74 | [FE] | Given `ReserveRowDialog` with three open rows, then the body is ONE DataGrid (`role="table"`, `tableLayout` fixed + resizable, every column with an explicit `size`) with one row per product and column headers Product, Requested, Location, Reserved, Reason, and a per-row `Confirm reserved` button; each row's Location / Reserved / Reason inputs are independent; a confirmed row's Reserved cell reads `Reserved N` with the tick and carries no inputs; the footer `Confirm all` is disabled while any open row is short without a reason and, when clicked, calls `onReserve` once per open row in table order (stopping after a rejected call, earlier rows stay confirmed); the dialog closes after the last row. No stacked per-row cards remain. |
| AC-RS-75 | [FE] | Given `ReserveRequestDialog` with three selected rows, then the body is ONE DataGrid with columns Product, Delivery date, Remaining, Requested (number input, default remaining, max remaining, min 1), Location (`SearchableSelect`); Note stays below the grid; Send posts the same payload as AC-RS-22. At 375px both dialogs' grids scroll sideways inside the dialog body without clipping the page. |
| AC-RS-72 | [E2E] | agent-browser on :3080, from `/` by sidebar: on an OI whose Lines grid is wider than the viewport, expand a row: the stock table's number columns are visible without scrolling and shift-wheel over the stock table scrolls the grid sideways; the expand header shows no grip; a reserved row's State reads `Reserved N` with a tick and opens the dialog on click; an email-style deep link with two open rows opens one dialog with two sections. Screens under `documentation/plans/scm/evidence/oi-request-cs-reserve/round3/`. |

### Round 3 fix round 1 (per-row pool resolution, 23 Sep)

| # | Layer | Given / When / Then |
| --- | --- | --- |
| AC-RS-65b | [FE] | Given the multi-row dialog (AC-RS-65) with two open rows naming DIFFERENT products, then `useReserveRowOptions` resolves once per distinct `product_id` (`getStockDetail` called once per product, not once per row and not only for the first row), and each section's Location dropdown / Reserved default read that row's OWN pool options and availability. |
| AC-RS-66b | [FE] | `ReserveRowDialogRow` carries optional per-row `locationOptions`, `availableQtyByLocation`, `defaultLocationId`; each falls back to the dialog's own top-level prop when absent, so a single-row caller (or an older multi-row caller that has not moved to per-row resolution) renders unchanged. |

### Round 4 (plan 6e, 24 Sep, CS reserves line by line with one Reserve CTA)

Superseded by round 4: AC-RS-56/57/58 (per-row reserve + unreserve routes, retired), AC-RS-61/62 (dialog from the icon / deep link), AC-RS-65/66/67/73/74 (multi-row dialog, Confirm all, header badge), AC-RS-64/72 E2E walks (rerun as AC-RS-90).

| # | Layer | Given / When / Then |
| --- | --- | --- |
| AC-RS-76 | [BE] | `POST .../order-inquiries/{inquiry_id}/reserve-commit` (rows resolved server-side, plan 6e.4) with `reserves` for two of three open rows (one full, one short with reason) writes two reserve links, two request rows answered, two `reserved` events, the third row stays open, the request stays `requested`, `refresh_link_state` ran for both rows (Taken / Remaining follow), and `dispatch_event("order_inquiry_reserved", ...)` fires exactly ONCE after commit with `reserve.rows` = the two rows (qty_reserved, balance, reason), `reserve.open_row_count = 1`. |
| AC-RS-77 | [BE] | Committing the last open row flips the request to `reserved` with `reserved_by/at`; committing again with an already-answered row in `reserves` is 409 naming it; a row of another request is 404; an empty payload is 422; a short row without a reason is 422 and NOTHING in the batch is written. |
| AC-RS-78 | [BE] | `amendments` on a reserved row: lowering 50 -> 30 reduces the link to 30 and writes one `unreserved` event of 20; raising 30 -> 45 (<= requested) raises the link to 45 and writes one `reserved` event of 15; setting 0 deletes the link and writes `unreserved` of the net; above `qty_requested` is 422; a reason is required whenever the new qty is short of requested; an amendment on an OPEN row is 422. The row's Taken / Remaining follow. |
| AC-RS-79 | [BE] | The commit route needs `projects.order_inquiries.reserve` (403 otherwise); `POST .../rows/{row_id}/reserve` and `.../unreserve` answer 404; the deferred action `order_inquiry_reserve_row.unreserve` is no longer registered; `GET .../rows/{row_id}/history` still lists requested / reserved / unreserved / cancelled newest first. |
| AC-RS-80 | [BE] | The reserved mail rendered for a partial commit carries only the committed rows in its table and the line `1 line still to reserve`; a completing commit carries no such line. Subject unchanged. |
| AC-RS-81 | [BE] | Two commits on the same request in sequence (rows A then B) send two mails, each naming its own rows only. |
| AC-RS-82 | [BE] | A commit inside a transaction that rolls back dispatches nothing. |
| AC-RS-83 | [FE] | Lines grid, viewer WITH the reserve permission and an open request: a requested line's State reads `Request to reserve 107` (amber) and its action cell shows icon buttons `Reserve` (tick) and `Edit reserve` (pencil); a reserved line reads `Reserved 30` + tick and shows `Amend reserve` (pencil) and `History` (info); a line with no reserve state shows the plain state pill and no icons. Viewer WITHOUT the permission: pills only, no action cell. No `reserve` column id, no header badge, no `Confirm all`, no `ReserveRowDialog`. |
| AC-RS-84 | [FE] | Clicking `Reserve` (tick) on a requested line stages `{ qty: requested, warehouse: default pool }` with no dialog: the cell now shows the chip `Reserve 107 @ BRW` and an `Undo` button; `Undo` restores the two icons. Nothing is posted. |
| AC-RS-85 | [FE] | Clicking `Edit reserve` opens `ReserveLineForm` (title = item code; Location `SearchableSelect` prefilled with the default pool, options = the row's pools with availability; Reserved number prefilled `min(requested, available)` floored at 0, max requested; Reason appears when Reserved < Requested and **Stage** stays disabled until filled); Stage closes the form and shows the chip `Reserve 20 @ DC1` (or `Reserve 0`). |
| AC-RS-86 | [FE] | `Amend reserve` on a reserved line opens the same form with Location locked (read-only text) and Reserved prefilled with the net; Stage shows the chip `Amend to 10`; Undo drops it. |
| AC-RS-87 | [FE] | Header: with the reserve permission and an open request, a `Reserve` button renders beside `Confirm`, disabled with label `Reserve` while nothing is staged and enabled with label `Reserve (2)` when two lines are staged; click posts ONE commit `{ reserves: [...], amendments: [...] }` built from the staged map, toasts `Reserved, <requester> notified`, invalidates lines + reserve requests, clears the staged map and the button greys again. A rejected commit leaves the staged map intact and toasts the error. Without the permission the button is absent. |
| AC-RS-88 | [FE] | Lines tab filter: a clearable `SearchableMultiSelect` labelled State beside the product search with options To buy, Partly on PO/SPO, On PO/SPO, Done, Cancelled, Request to reserve, Reserved; selecting `Request to reserve` shows only lines with `reserve_state requested`; `?reserve=<id>` on the URL preselects `Request to reserve` (no dialog opens) and the param is dropped from the URL when the filter is changed. |
| AC-RS-89 | [FE] | `History` (info) on a reserved line opens `ReserveLineHistoryDialog` listing the row's events newest first through `formatDateTime`; the purchasing `ReserveRequestDialog` grid renders no drag grips and no outer scroll wrapper; `Cancel request` lives in the Actions menu for the requester or a permission holder (deferred countdown as AC-RS-19). |
| AC-RS-76c | [BE] | Duplicate `row_id` across `reserves + amendments` (same row twice in `reserves`, or in both lists) is 422 naming the row before anything is read or written. |
| AC-RS-77b | [BE] | A `row_id` whose inquiry is not `{inquiry_id}` (same company) is 404; a foreign-company inquiry is 404; `reserves` on a row with no open request row is 409; `amendments` on a row with no answered request row is 422. |
| AC-RS-78b | [BE] | Row qty 100, request #1 reserved 10, request #2 reserved 90 (or a PO link 90): amending #1 up to 100 is 422 naming the row; up to 20 (= 10 + remaining 10) is accepted. Amending a declined row (0) up to 15 re-creates the link at 15 and writes a `reserved` event of 15. A no-op amendment (same qty) touches nothing and sends no mail. |
| AC-RS-78c | [BE] | The lines serializer reads `reserve_state = declined` for a row whose latest answered request row has `qty_reserved = 0` (and no open row); `requested` still wins while an open row exists. Reserve 0 writes a `reserved` event with qty 0. |
| AC-RS-79b | [BE] | Cancelling a partly answered request is accepted: open rows are withdrawn, answered rows keep their links; a later commit with `amendments` on those rows succeeds, with `reserves` on the cancelled request's rows is 409. Two commits touching rows of two different requests dispatch one `order_inquiry_reserved` per request, each naming its own rows. Re-requesting the balance of a row answered inside a still-open request is accepted (ordinal +1). |
| AC-RS-83b | [FE] | A declined line reads `Not reserved` (neutral pill) with `Amend reserve` + `History`; the action column is absent on an inquiry with no open request and no reserved / declined line, and its header carries no drag grip. |
| AC-RS-85b | [FE] | The form opens only once the pool options have loaded: Reserved is prefilled `min(requested, available)` (never 0 from an unloaded state); Reason is required whenever Reserved < Requested in both modes (availability never waives it); amend prefill = that request row's own reserved qty, clamped to its requested; a staged reserve with no chosen location is sent without `warehouse_id`. |
| AC-RS-88b | [FE] | Changing the State filter while `?reserve=` is on the URL calls `router.replace` without the param; the options list has no `Cancelled`; an empty filter result reads `No line matches the filter.` |
| AC-RS-90 | [E2E] | agent-browser on :3080 from `/` by sidebar, 1280 and 375: Joey requests three lines; Eling follows `?reserve=` (grid filtered to `Request to reserve`), ticks line 1, pencils line 2 to 20 with a reason, leaves line 3, clicks `Reserve (2)`: lines 1 and 2 turn green, line 3 stays amber, one outbox row names lines 1 and 2 and says `1 line still to reserve`, the button greys; she amends line 2 to 10, `Reserve (1)`, History shows reserve 20 then unreserve 10. Screens under `documentation/plans/scm/evidence/oi-request-cs-reserve/round4/`. |

## Out of scope (recorded, not built)

AutoCount transfer / transfer number; `StockTransfer` paper row for OI-driven reserves; Taken /
Remaining columns with footers (ruled in `PLAN-board-oi-mechanical-22sep.md`). Superseded by
round 2: partial answers to one request (now per row) and amending a reserved qty (Unreserve).
