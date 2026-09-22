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

## Out of scope (recorded, not built)

AutoCount transfer / transfer number; `StockTransfer` paper row for OI-driven reserves; Taken /
Remaining columns with footers (ruled in `PLAN-board-oi-mechanical-22sep.md`). Superseded by
round 2: partial answers to one request (now per row) and amending a reserved qty (Unreserve).
