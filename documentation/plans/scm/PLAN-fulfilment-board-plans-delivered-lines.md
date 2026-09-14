# PLAN - Fulfilment board plans what nobody decided, delivered or not

Status: approved - owner rulings on the lavish page 14 Sep 2026 (inquiry row = decided, binary;
plan qty = full ordered qty; worklist unchanged; Planned pill on the list = yes, S4 in this
lane); building
UAC: `fulfilment-board-plans-delivered-lines-acceptance-criteria.md` (same folder).
Domain: scm. Lane branch: `feat/fulfilment-board-plans-delivered-lines`. One lane, one PR.
Issues: S1 #900, S2 #901, S3 #902, S4 #903 (raised 14 Sep).
Source of the ask: SO421404 on prod, 14 Sep 2026. Completed, 3 of 3 delivered, no plan ever
made, board says "Nothing is outstanding on these sales orders that can be planned". Owner: "we
cannot base on outstanding quantity, we need to base on planned quantity".

## The problem, measured (local 0907 prod copy, 14 Sep 2026)

The board admits a line through two gates, both about delivery, neither about planning
(`project_fulfilment_board_service.py:1313-1318`):

| Gate | Expression | What it drops |
| --- | --- | --- |
| Header | `SalesOrder.status == "open"` | every `closed` order (10,561 of 11,379 project orders) |
| Line | `is_open_demand()` = `line_status = open` AND `purchasing_status != covered` AND `coalesce(qty_required, qty_ordered) - qty_delivered > 0` | every delivered line, including 261 `open` lines fully delivered |

A line nobody decided is invisible the moment the book says it shipped. Stock leaves the bin,
no Buy is ever confirmed, no ORDER row reaches purchasing, nothing is bought back.

What "decided" already means, in two places that must agree:

- An ACTIVE `so_supply_decisions` revision whose `line_snapshots[].core_line_id` names the line
  (`_frozen_decisions`, and the netting engine's `_decided_core_line_ids()`).
- Since #875 the migrated order inquiry sheet raised inquiry rows on real SO lines. On the 0907
  copy 2,311 open undecided lines carry a `raised` ORDER row and 296 a `placed` or
  `partly_linked` one: purchasing was told, and the board today proposes for them again.

Newly admissible if selected (delivered, no decision, no live inquiry row, not covered, not
cancelled): 111,915 closed lines on 10,552 closed orders, 6,634 of them ordered since June;
177 closed lines on 11 open orders; 1 open partial line. The board is selection-scoped and
capped at 50 orders, so none of this appears unasked. The owner accepts the old ones: they
only show when somebody selects them, and nothing is written until somebody confirms.

One latent defect the change would multiply, so it is fixed first: a confirmed own-location
allocation holds `so_line_allocations.qty` for as long as its decision is active
(`_hold_query`, `project_supply_service.py:7771-7778`). Delivery does not shrink it, and the
book already took the units off `quantity_on_hand`, so a delivered decided line is subtracted
twice. Today that bites nobody: 97 decided lines, 0 with any delivery, 0 confirmed allocations
on delivered lines. Planning delivered lines makes it routine.

## Design

### The rule

**A line is planned when nobody has decided it. Delivery is not a decision.**

- Admitted: order status `open` or `closed`, demand class project; line status not
  `cancelled`; purchasing status not `covered`; plan quantity above zero.
- Plan quantity = `coalesce(qty_required, qty_ordered)`, zero for a cancelled line. Not the
  still-owed figure. A delivered unit nobody sourced is a unit to put back.
- Decided = active decision on the core line (as today) OR a live inquiry row on it (state not
  `cancelled`, ack_state not `rejected`). Decided lines render read-only and are never proposed
  for, never in the confirm set, never in the pile queue.
- Stock holds follow what is still owed: an own-location allocation holds
  `least(alloc.qty, greatest(ordered - delivered, 0))`, zero on a cancelled line. So "Use own
  location" on a delivered unit records the source and holds nothing, while "Buy" on it raises
  the order-back row.

`is_open_demand()` and `demand_qty()` are NOT touched. The netting engine, the reorder plan
and the worklist keep answering "what is still owed"; only the board answers "what is
undecided". The two predicates diverge on purpose, the way `_cancelled_pending_change_rows`
already diverges for pending changes.

### Why binary "inquiry row = decided", not "inquiry qty nets the Buy"

The owner's ruling is that the migrated book is the decision on the buying side. A partial row
(the G2 cascade splits a placed allocation from its raised remainder) would under-count if the
board netted quantities, but the cascade already keeps the remainder as its own `raised` row,
so the line stays covered by a live row either way. Trigger for revisiting: a real line whose
live rows sum to less than its plan quantity and whose remainder needs a board decision. None
measured today.

### Why the board is always shown

Decided lines already render read-only with their frozen composition (`covered`,
`_suggest_live_for_covered`). A fully decided completed order is a board with nothing to
confirm, which is the audit view for free. A "fully planned" gate on the SO list and detail
would need a per-order computation, a hidden button and a second empty state, for nothing.

## Slices

### S1 - Hold cap [BE]

`project_supply_service.py`:

- Add `owed_qty_expr()` beside `_open_of`: the SQL twin of `_open_of` over the joined
  `SalesOrderLine` (`greatest(qty_ordered - coalesce(qty_delivered, 0), 0)`, `0` when
  `line_status = 'cancelled'`). `_hold_query` already outer-joins `SalesOrderLine`.
- `_hold_query` gains a `held_qty` column expression = `least(SOLineAllocation.qty,
  coalesce(owed_qty_expr(), SOLineAllocation.qty))` (an allocation with no core line keeps its
  raw qty). `_hold_rows` and `stock_debt_service._holds` select `held_qty` instead of
  `SOLineAllocation.qty`. One expression, two readers (AC-S1-4).

Tests (`tests/test_project_supply_holds.py`, new; Postgres fixture): AC-S1-1 to AC-S1-5.

### S2 - Board admission and plan quantity [BE]

`app/services/scm/demand.py`:

- Add `plan_qty()` (SQL: `coalesce(qty_required, qty_ordered)`) and `is_undecided_demand()`
  = `line_status != 'cancelled' AND purchasing_status != COVERED AND plan_qty() > 0`. Documented
  as the BOARD's predicate, beside `is_open_demand()` which stays the netting predicate.

`project_supply_service.py`:

- Add `plan_qty_of(core)` beside `_open_of`: `coalesce(qty_required, qty_ordered)`, zero when
  cancelled. `_LineFacts.open_qty` is set from it (line 7366). Every ladder ask, the confirm
  sum check (4685) and its wording (4716), and the drift comparison (4275) then read the plan
  quantity. `_open_of` keeps its two remaining readers: the hold cap (S1) and
  `project_line_draft_service` / `sales_order_service.is_stale`, which speak about what is owed.
  AC-S2-10 holds without a data migration because no decided line has a delivery today.

`project_fulfilment_board_service.py`:

- `_demand_rows`: header filter `SalesOrder.status.in_(["open", "closed"])`, line filter
  `is_undecided_demand()`, `qty=plan_qty_of(line)`.
- `_order_inquiries` already returns state and ack_state per core line. Add `_Row.inquiry_decided`
  = live row present, state not `cancelled`, ack_state not `rejected`. `covered` becomes
  `decision is not None or inquiry_decided`. `_allocate`, `_suggest_live_for_covered`, the pile
  queue's `_decided_elsewhere` and `confirmLinesFor`'s server twin treat an inquiry-decided row
  like a decision-covered one with an empty composition (no `proposal`, no `decision`).
`project_so_adoption_service.py` (gap the tester found, 14 Sep): `adopt` refuses any order not
`open` (`_assert_plannable`) and `_open_core_lines` mirrors `is_open_demand()` lines only, so a
Completed order could never reach confirm. Both move to the board's predicates: header
`status in (open, closed)`, lines `is_undecided_demand()`. `adopt_for_migration` already has
the shape. Refusal wording for a cancelled order stays. AC-S2-14, AC-S2-15.

`project_fulfilment_board_service.py`, continued:

- The `stock_detail` query (line 876) keeps `SalesOrder.status == "open"` and `is_open_demand()`:
  it lists what is still owed against a bin, which is a delivery question.
- Empty-state copy source unchanged (`line_count`), meaning unchanged (0 admitted lines).

Tests (`tests/test_fulfilment_board.py`, adoption tests beside the existing adopt tests): rewrite
the admission test (AC-S2-12), add AC-S2-1 to AC-S2-9, AC-S2-13 to AC-S2-15; existing netting and worklist tests untouched (AC-S2-11).

### S3 - Board wording [FE]

`FulfilmentBoardPanel.tsx` two empty states reworded (AC-S3-1, AC-S3-4); tests in
`FulfilmentBoardPanel.test.tsx` and `FulfilmentPlanningClient.test.tsx` updated. Inquiry-decided
cell rendering (AC-S3-2): reuse the covered-row branch, show `order_inquiry.inquiry_no` in the
composition slot when `decision` is null. Phase 1 is this wording and the mock row shape; no
new component.

### S4 - "Planned" on the Sales Orders list and detail header [BE] [FE]

Owner's question on the lavish page: "how do I know if the order is fully planned from the list
itself?" Today the list has an Order inquiries column (inquiry numbers, rows placed) and nothing
that says decided. SO421404 reads Completed and nothing else.

Backend, `sales_order_service.py`: a `with_planning_state(rows)` sibling of
`with_order_inquiries` (line ~1020), one grouped query per PAGE over the page's orders' lines,
never per row. Per order it writes `planned_lines` (admitted lines that are decided) and
`plannable_lines` (admitted lines), using THE SAME two predicates the board uses:
`is_undecided_demand()` for admitted, and decided = core line id in `_decided_core_line_ids()`
OR has a live inquiry row (state not `cancelled`, ack_state not `rejected`). The decided rule
is one function in `app/services/scm/demand.py` (`decided_core_line_ids_with_inquiries()` or
a filter the board's `_Row.inquiry_decided` also reads) so the list and the board cannot
disagree. Both fields go on the list response schema AND the detail response (the two manual
dict builders; a field missing from either never reaches the FE).

Frontend: one `Planned` column on `SalesOrdersGrid` (Badge, `size` set, after Status): all
decided = "Planned" (success), some = "Partly n/m" (warning), none = "Not planned"
(destructive), `plannable_lines` 0 = "-". Same Badge in the `SalesOrderDetail` header beside
Status (view and edit share the layout). Not sortable, not filterable in this lane (trigger:
the owner asks for the filter; the counts are already on the row).

Tests: pytest for the counts per state (AC-S4-1 to AC-S4-5), vitest for the four pill states.

## Phase order

Phase 1: S3 wording and the S4 pill against the mocked list, detail and board responses (the
contracts: `_Row` with `covered: true, decision: null, order_inquiry: {...}`; list and detail
rows with `planned_lines` and `plannable_lines`). Phase 2: tester writes S1, S2 then S4 red
tests from the UAC; coder greens S1 first (the cap), then S2, then S4, then swaps the Phase 1
mocks. Phase 3: reviewer + tester browser walk (AC-E2E-1 to AC-E2E-3) in parallel; security
reviewer not needed (no auth, ingest, upload or scoping change).

## What changes in the planning engine, stated plainly

The rungs, the ranking and the policy do not change. Three inputs do:

1. **Which lines the board walks** (`_demand_rows`): board-only predicate, netting untouched.
2. **How much a line asks for** (`_LineFacts.open_qty`): plan qty, not still-owed. Every ladder
   ask, group net, pile share, the confirm sum check and the drift check read this one field.
   On the 0907 copy the only live difference is one open partial undecided line; no decided
   line has a delivery, so no existing revision changes meaning.
3. **What a confirmed own-location allocation holds** (`_hold_query`): capped at still-owed.
   Zero effect on today's data (no allocation sits on a delivered line).

Plus one new read-only state on the board: a row decided by an inquiry with no composition.

## Out of scope, named

- The planning worklist stays on `is_open_demand()`. Completed undecided orders are reached by
  selection from the Sales Orders list. Trigger to revisit: CS asks for a queue of them.
- Netting an inquiry row's quantity against the Buy (see the binary ruling above).
- A "planned quantity" column on the sales order lines grid. Trigger: the owner asks for it.
