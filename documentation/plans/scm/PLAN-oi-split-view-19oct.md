# PLAN: split follow-ups after #1749 (OI-SPLIT-VIEW)

Status: Plan. Card answered (crew Q1 a, Q2 a; owner Q3 b, Q5 = (i) popup per line, crew ruling
a14761180); Q4 open with the owner. Mock v3 filed (`documentation/mockups/OI-SPLIT-VIEW/index.html`, own Split column per the owner's v2 note);
build after the owner OKs it. Track: M (new rule on the board, UI on two existing screens, no
migration). Lead pattern: tester red tests, one coder, reviewer, browser pass 1280/375 on the crew
test copy.

Card: `oi-split-view-behaviour-card.md` (alongside; filed as crew ask 19 Oct). UAC:
`oi-split-view-19oct-acceptance-criteria.md` (after the card is answered). Mock:
`documentation/mockups/OI-SPLIT-VIEW/index.html`.

## Journey

Owner 19 Oct ~20:30 MYT, after OKing #1749: "you have a follow up PR to make the split delivery at
this level [planning board] and it should be based on those that are saved only, not all the
lines, and I need this split detail visible at the sales order level at the line meaning I can
visualize the split from the sales order perspective, as well as the OI perspective at line level".

1. Planning board: after a plan is confirmed, a saved split-only edit (qty or date changed on the
   split sheet and Saved) shows in "Confirm (N)" and can be confirmed, so the change reaches
   purchasing (OI rows, email, Excel). Count only saved split edits that differ from the last
   applied plan. One function for engine, email and Excel; no CANCEL from splits (#1749 AC-G15
   gap, step 16 of laneboard/scripts/1749.md).
2. Sales Order page > Lines tab: each SO line shows its split detail.
3. Order Inquiry page > Lines tab: each OI line shows its split detail at line level.

## Steps

1. Discovery with file:line (board count, Confirm path, SO and OI Lines tabs, split read API).
2. Behaviour card as ONE crew ask.
3. Lavish mock on SO417636 (business data only, masked in the committed copy).
4. After owner OK: UAC, tester red tests, coder, reviewer, browser pass, hand-test script.

## Discovery (summary; full citations in the card)

- Board count is FE only: `confirmSummaryFor` (`_shared/lib/fulfilmentBoard.ts:861`) over board
  contributions; it never reads splits, so a split-only edit counts 0.
- Confirm applies only the lines the FE posts (`fulfilment_planning.py:1447`, `:446`). AC-G15's
  "edited applied plan" compare lives inside `_later_change_lines`
  (`project_order_inquiry_service.py:6028-6040`) and needs a pending AutoCount change on the line.
- Applied plan stamp: `split_plan_key` (`project_order_inquiry_service.py:237`) on the decision
  snapshot; newest per line read by `_recorded_split_plans` (`project_line_split_service.py:1021`).

## Phase 2 contract (tester and coder share this; UAC is the behaviour)

Backend, one module-level function in `app/services/project_line_split_service.py`:
`split_plan_edited(saved_splits, applied_plan) -> bool` (`split_plan_key(saved) != (applied or [])`,
False when there are no saved splits). Every reader below calls it; none recomputes the compare.

1. Board (UAC A2): `BoardContribution` (`app/schemas/project_board.py:574`) gains
   `split_edited: bool = False`. GET `/fulfilment-planning/board` sets it per line.
2. Confirm (UAC A4): POST `/sales-orders/{pso_id}/confirm` (`fulfilment_planning.py:1447`) and
   POST `/fulfilment-planning/confirm-all` (`:446`) apply every split-edited line of each order they
   confirm, even when the body names no line of it (body `lines: []` is accepted for an order that
   has split edits; an order with nothing to confirm answers as today). POST
   `/fulfilment-planning/simulate-confirm` (`:689`) does the same on its rolled-back session.
3. Split view (UAC B): one serializer builds `split_view` for a mirror line, null when the line has
   no splits:
   `{status: "confirmed" | "saved" | "autocount_changed", revision_no: int | null,
   confirmed_on: "YYYY-MM-DD" | null, base_qty: str, base_date: str | null, now_qty: str,
   now_date: str | null, total_qty: str, rows: [{qty: str, delivery_date: str | null,
   change: str, sits_on: "own" | "line" | "new" | "extra", sits_on_line_no: int | null,
   remark: str, is_cancel: bool, changed: bool, was_qty: str | null, was_date: str | null}]}`.
   Rows: the saved splits in `seq` order, then the AutoCount extra row (`sits_on: "extra"`,
   `change: "ORDER <n>"`, date = the line's now date). `change` = `remark_for_row` word.
   `sits_on_line_no` = AutoCount line number (core `line_no`). It rides on:
   - the OI header-lines rows: `OrderInquiryRowOut.split_view` (`app/schemas/project_order_inquiry.py:212`)
     and the worklist row (`:552`), beside the existing `splits`;
   - the SCM sales order read: `SalesOrderLine.split_view` (`app/schemas/scm_orders.py:151`), GET
     `/scm/sales-orders/{id}` (core line -> mirror line by `core_sales_order_line_id`).

Frontend:
4. `_shared/lib/fulfilmentBoard.ts`: `confirmSummaryFor` counts a contribution with
   `split_edited` once per line; the Confirm press posts each order that has a split-edited line
   (body may carry no lines for it). Result card line "Split edits to confirm: line <n> <item>".
5. One shared component `project-sales/_shared/components/LineSplitInfo.tsx` exporting
   `LineSplitInfo` (props: `lineNo`, `itemCode`, `soNumber`, `oiNumber?`, `purchasingState?`,
   `po?`, `view: LineSplitView | null`): renders nothing for a null view, else the "Split N" chip
   and the (i) button (aria-label "Show the splits of line <n>") that opens the Dialog of UAC B2-B4.
   It is the cell of a new column `id: 'split'`, header "Split", right after Product, in the OI
   header-lines columns (`orderInquiryHeaderLinesColumns.tsx`; today's `SplitChip` leaves the Product
   cell) and in the SO Lines columns (`SalesOrderDetail.tsx`); both Columns menus list it.
   Type `LineSplitView` mirrors item 3 (in `_shared` types next to `OrderInquiryLineSplit`).

Test files (tester): `tests/scm/test_split_view_board.py` (A), `tests/scm/test_split_view_read.py`
(B data on both reads); vitest beside `fulfilmentBoard.ts`, `LineSplitInfo.tsx`,
`SalesOrderDetail.tsx` and the OI columns. Throwaway DB `sorento_oisv_throwaway` (lead-made; run with
`SORENTO_ENV_FILE=<scratchpad>/env.throwaway`), pytest `-n 2`, touched files only.
