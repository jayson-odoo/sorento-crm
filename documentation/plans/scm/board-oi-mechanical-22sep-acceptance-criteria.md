# UAC - Board + OI mechanical fixes (lane B, owner rulings 22 Sep 2026)

Plan: `PLAN-board-oi-mechanical-22sep.md`. Status lives on the plan. Round 2: S4 dropped,
default supplier dropped, Ack column dropped, S5 added.

## Journey

**Actor:** CS planner on the fulfilment board; purchasing on the order inquiry pages. Both
several times a day.

**B1 grid date.** Planner opens Fulfilment Planning from the sidebar, picks orders, switches
to Grid. Columns are the lines' own required dates (`01/11/2026`), one column per distinct
date across the selection, however many. By day / week / month still available.

**B2 date move.** The AutoCount book moves a line's date. Planner confirms the change. The
line's existing buy row is restated in place: new date, old date kept as Was, `changed_at`
stamped, ack drops to `changed` so it returns to purchasing's To confirm, every PO/SPO link
kept. Purchasing sees ONE row, a `Changed` tag beside the date, and an (i) reading "Was 100 on
01/11/2026". No ADVANCE / DELAY row is raised beside a buy row. Duplicates already on prod are
folded by a one-off script the owner runs.

**B3 taken / remaining.** Purchasing opens an OI, Lines tab. Each row: Qty, Taken (sum of its
links), Remaining (Qty - Taken - bundled). Footer: three sums over buy rows only. Notice rows
and cancelled rows count nothing. Worklist list carries the same columns and footer.

**B5 plain words.** The State pill says what purchasing does with the row (To buy / Partly on
order / On order / Done / Cancelled), not "Raised" / "Actioned". Wording per owner's pick.

## Phase 1 - frontend against mocks

### B1 grid columns
- **AC-B1-1 [FE]** Given the period select, when the board loads, then the options are
  `By date` (default), `By day`, `By week`, `By month`.
- **AC-B1-2 [FE]** Given `By date` and lines on 2026-11-01, 2027-02-01, 2027-04-01, when the
  grid renders, then exactly three date columns appear, headed `01/11/2026`, `01/02/2027`,
  `01/04/2027`, in date order, plus `No date` last when any line has none.
- **AC-B1-3 [FE]** Given 40+ distinct dates, when the grid renders, then every date is a
  column and the grid scrolls horizontally; no folding, no paging.
- **AC-B1-4 [FE]** Given `By date`, when a past date column renders, then it carries the same
  `Already past` treatment week columns do today.
- **AC-B1-5 [FE]** Given a URL with `granularity=week`, when the board loads, then week view
  is shown (URL param still honoured; `date` is only the default when none is given).

### B2 row screen
- **AC-B2-0 [FE]** Given a Lines-tab row with `ack_state === 'changed'`, when it renders, then
  a `Changed` tag sits beside the delivery date next to the (i); no Ack column exists.

### B3 Lines tab + worklist columns
- **AC-B3-1 [FE]** Given the OI detail Lines tab, when it renders, then columns read Product,
  Qty, Taken, Remaining, Delivery date, Supplier, PO, SPO, Location, Instruction, State, and
  Taken / Remaining are hideable through Columns like the rest.
- **AC-B3-2 [FE]** Given a buy row (`ORDER`, `ORDER_BACK`, `RESERVE_AND_ORDER`) with qty 300,
  links 140 + 24, bundled 0, when it renders, then Taken = `164`, Remaining = `136`.
- **AC-B3-3 [FE]** Given a notice row (`ADVANCE`, `DELAY`, `CHANGE_SO`, `CANCEL_BALANCE`,
  `PRE_ORDERED_DO_NOT_ORDER`, `ALREADY_INBOUND`, `RELEASE`), when it renders, then Taken and
  Remaining print `-`.
- **AC-B3-4 [FE]** Given a row on a cancelled sales-order line or a row in state `cancelled`,
  when it renders, then Remaining = `0` and it is excluded from every footer sum.
- **AC-B3-5 [FE]** Given 10 buy rows and 2 notice rows, when the footer renders, then Qty,
  Taken, Remaining footers equal the sums over the 10 buy rows only, and Remaining footer =
  Qty footer - Taken footer - sum(bundled).
- **AC-B3-6 [FE]** Given the OI worklist list, when it renders, then Taken and Remaining
  columns exist with the same rules and a footer labelled for the current page.
- **AC-B3-7 [FE]** Given the Lines tab at 375px, when it renders, then Taken / Remaining are
  reachable by horizontal scroll and nothing clips.

### B5 plain words
- **AC-B5-1 [FE]** Given the label map, when any State pill renders, then `raised` /
  `partly_linked` / `placed` / `actioned` / `cancelled` print **To buy / Partly on PO/SPO /
  On PO/SPO / Done / Cancelled** (owner's pick, 22 Sep) on the Lines tab, the worklist and the
  board chips alike.
- **AC-B5-2 [FE]** Given filters or tooltips that repeat the state word, when they render,
  then they use the same map (no second spelling anywhere; grep test for `'Raised'`).

### B6 OI row ⇄ SO line deep links
- **AC-B6-1 [FE]** Given an OI Lines tab or worklist row with `so_number` SO402757 and line
  5, when it renders, then a column **SO line** prints `SO402757 · L5` as a link to
  `/scm/sales-orders/<sales_order_id>?tab=lines&line=<core_line_id>`; no id is printed.
- **AC-B6-2 [FE]** Given the SCM sales order detail Lines tab and a line with an order
  inquiry, when it renders, then the Order inquiry cell is a link to
  `/project-sales/order-inquiries/<inquiry_id>?row=<row_id>`.
- **AC-B6-3 [FE]** Given the SO detail loads with `?tab=lines&line=<id>`, when the lines
  render, then the Lines tab is selected, that row is scrolled into view and highlighted
  for ~2s, and the `line` param is removed from the URL without a navigation.
- **AC-B6-4 [FE]** Given the OI detail loads with `?row=<id>`, when the rows render, then
  the Lines tab is selected, that row is scrolled into view and highlighted for ~2s, and the
  `row` param is removed.
- **AC-B6-5 [FE]** Given the `line` / `row` id matches nothing (row cancelled and hidden, or
  wrong id), when the page loads, then nothing glows and no error shows.
- **AC-B6-6 [UX]** Highlight uses an existing colour token and a 2s fade; under
  `prefers-reduced-motion` it appears and disappears without transition.
- **AC-B6-10 [FE]** Given the target row sits on page 3 of a 25-per-page grid, when the page
  lands with `line` / `row`, then the grid switches to page 3 first, then scrolls and glows
  that row.
- **AC-B6-11 [FE]** Given the grid's search box holds text from a previous visit, when the
  page lands with a target, then the search is cleared before the lookup so the row is
  findable.
- **AC-B6-12 [FE]** Given the target is not in the loaded set, when the page lands, then a
  toast reads "That line is not shown here" and nothing glows.
- **AC-B6-13 [FE]** Given the fulfilment planning List view, when it renders, then the
  leftmost column is **Line** (AutoCount line number), sortable, and the default sort is
  Sales order then Line ascending.
- **AC-B6-14 [FE]** Given the List view Sales order cell, when it renders, then it prints
  the number only (no `(Line N)`), and its link opens the sales order detail with that line
  glowing (AC-B6-3).
- **AC-B6-15 [FE]** Given a List view line with a live OI row, when it renders, then a new
  **OI** column prints the inquiry number as a link that lands on that row (AC-B6-4); a line
  with no live row prints `-`. Grid view is unchanged.
- **AC-B6-16 [FE]** Given the List view at 375px, when it renders, then Line, Sales order
  and OI stay readable and nothing clips.

## Phase 2 - backend

### B1 grid columns
- **AC-B1-6 [BE]** Given `granularity=date`, when `GET /project-sales/fulfilment-planning/board`
  runs, then `bucket_key` = the line's `required_date` ISO, `dateBuckets` lists only keys
  with at least one contribution (no calendar fill, no `day_window_start`), sorted
  ascending, `No date` last, each with `is_past`.
- **AC-B1-7 [BE]** Given `granularity=date`, when the label is built, then it is `DD/MM/YYYY`.
- **AC-B1-8 [BE]** Given `granularity=day`, when the endpoint runs, then behaviour is exactly
  today's (30-day window); pinned by the existing test.
- **AC-B1-9 [T]** `tests/test_fulfilment_board.py::test_bucket_assignment_for_day_week_and_month`
  extended: `date` key == `day` key for the same input; `dateBuckets` for `date` has no empty
  calendar days.

### B2 date move settles in place
- **AC-B2-1 [BE]** Given a line with one live buy row (raised / partly_linked / placed) and a
  confirmed planning change `advanced` or `delayed` on that line, when the change applies,
  then that row's `delivery_date` = new date, `previous_delivery_date` = old date,
  `previous_qty` = its qty, `changed_at` set, note gains `Was <qty> on <old date>`, and NO
  `ADVANCE` / `DELAY` row exists for the line afterwards.
- **AC-B2-2 [BE]** Given that row was `acknowledged`, when it settles, then `ack_state` =
  `changed`; given it was `awaiting`, it stays `awaiting`.
- **AC-B2-3 [BE]** Given the row carries PO and SPO links, when it settles, then every link
  survives with its qty and document unchanged.
- **AC-B2-4 [BE]** Given a line with NO buy row before the confirm, when the confirm raises a
  fresh buy row for it AND the batch carries an `advanced` / `delayed` change for the line,
  then only the buy row is raised (dated the new date, note `Was <old date>`), no notice row.
- **AC-B2-5 [BE]** Given a line with TWO live buy rows, when a date move applies, then both
  rows are restated in place per AC-B2-1 and no notice row is raised.
- **AC-B2-6 [BE]** Given a lone `placed` row with no link rows, when a date move applies,
  then the placed row gets `delivery_date` / `previous_delivery_date` / `changed_at` / ack
  `changed`, its qty untouched, and no notice row.
- **AC-B2-7 [BE]** Given a line whose buy rows are all `actioned` and fully linked, when a
  date move applies, then each gets the same date stamp and no notice row; the handover
  email lists it once as a date change.
- **AC-B2-8 [BE]** Given a line with no buy row and the confirm raising none, when a date
  move applies, then behaviour is unchanged from today; the test pins it.
- **AC-B2-14 [BE]** Given a change that moved the QUANTITY as well as the date
  (`DATE_AND_QTY_CHANGED`), when it applies, then the date half still lands on every buy
  row of the line per AC-B2-1 (qty and links untouched) and the quantity half is left to
  the ordinary netting, which raises the outstanding remainder on the new date. No notice
  is raised, because a buy row now carries the change's new date - and conversely, a line
  whose buy rows all still sit on the OLD date DOES get its notice (review round, 22 Sep).
- **AC-B2-9 [BE]** Given the settle stamps a date change, when the handover context builds,
  then the row appears under `changed` with was/now dates, never under `raised`.
- **AC-B2-10 [T]** `tests/scm/test_oi_confirm_per_so.py` and
  `tests/test_planning_change_apply_on_board.py` gain the cases above; every one is red first.

### B2 cleanup script
- **AC-B2-11 [BE]** `scripts/fold_oi_date_notices.py` with `--dry-run` (default) prints one
  line per live `ADVANCE` / `DELAY` row, any OI, whose `so_line_id` has a non-cancelled buy
  row: OI number, item, qty, notice date, buy row id, buy row date.
- **AC-B2-12 [BE]** `--apply` sets the notice row `state=cancelled`, appends
  `; Folded into the buy row by script, <date>` to its note, and on the buy row sets
  `delivery_date` = the NOTICE's own delivery date (the notice is the only row carrying the
  new date, so a fold that left the buy row where it was would delete the move rather than
  fold it - review round, 22 Sep; a notice with no date of its own is skipped and reported),
  `previous_delivery_date` = the notice's own "Was" date parsed from its note (skipped and
  reported when absent), `changed_at=now()`, note `; Was <qty> on <date>`; commits once;
  prints counts.
- **AC-B2-13 [T]** pytest on the private CI DB: seed one pair, run dry-run (no change),
  run apply (notice cancelled, buy row stamped), run apply again (no-op, idempotent).

### B6 deep-link ids
- **AC-B6-7 [BE]** Given an OI row, when `list_rows` / the worklist serialise it, then the
  payload carries `core_line_id` (the mirror's `core_sales_order_line_id`) and the CORE
  sales order's own id beside `so_number` and `line_no`; null when the mirror has no core
  line. (Review round, 22 Sep: the worklist row already carried that id as
  `core_sales_order_id`, which is the field the "SO line" cell reads, so it is NOT shipped
  a second time as `sales_order_id`; `list_rows`, which carries no `core_sales_order_id`,
  keeps its own `sales_order_id`.)
- **AC-B6-8 [BE]** Given an SCM sales order line with an inquiry row, when the detail lines
  serialise (`sales_order_service.py:510`), then `order_inquiry` carries `inquiry_id` and
  `row_id` beside `inquiry_no`.
- **AC-B6-9 [T]** Both fields asserted present in a response test (response_model guard).
- **AC-B6-17 [BE]** Given a board line with a live OI row, when
  `GET /project-sales/fulfilment-planning/board` serialises the contribution, then
  `order_inquiry` carries `inquiry_id` and `row_id` beside `inquiry_no` - the pair the List
  view's OI column (AC-B6-15) addresses the exact row with. Asserted off the route, not off
  `build()`: `BoardLineOrderInquiry` drops an undeclared field silently.

## Phase 3 - verification
- **AC-E2E-1 [E2E]** agent-browser, sidebar from `/`: Fulfilment Planning → Grid → default
  is By date on SO402757, columns read exact dates, screenshot at 1280 and 375.
- **AC-E2E-2 [E2E]** Order Inquiries → OI-2609-0678 → Lines: Taken / Remaining / footer /
  plain state words visible, screenshot.
- **AC-E2E-3 [E2E]** On the lane DB: apply a date-move batch on a line with a linked row, OI
  shows one row with the Changed tag and Was/Now (i), links intact.

## No-motion list
Nothing new animates. Column count change, new cells, new words: static.
