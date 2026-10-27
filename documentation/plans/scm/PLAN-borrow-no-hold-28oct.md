# PLAN: BORROW-NO-HOLD - a Borrow decision is a plan, not a stock hold

Status: Merge-ready pending CI + owner hand test (PR #1935; red-proof 6558131254 + 3c8369d7de, fix aedf4aed1a, kill-proof posted, reviewer READY, browser pass PASS on the crew copy). Owner answers 28 Oct ~00:25: (a) on all (Q1 reach only via a plan; Q2 OI links keep holding; Q2b supply
Borrows unchanged, "incoming doesn't come into the picture anyway"; Q3 keep the board donor cell; Q4 reorder runs stop
deducting Borrow; Q5 keep the confirm-time donor-line check). Track: full (size M, LEAD pattern: tester + coder +
reviewer subagents). Keep the diff apart from CONFIRM-DOUBLE-ROWS #1934 (repeat-Confirm stacking in
`project_supply_service.py`); merge main before crew-done. Base: main 71a43b3ba1 (carries #1919).

## Journey

Owner, 28 Oct ~00:20 MYT: "borrow shouldn't affect the planning also". This reverses the 27 Oct BOARD-NO-HOLD
Q3 answer ("Borrow as today, keeps holding"). #1919 (merged 3783f8c08b) made a confirmed Reserve a plan only:
it no longer holds stock in Stock Debt, the board strip, location stock, the ladder or the confirm floor, and in
the Stock Debt walk its line draws the planned bin at its own date (walk rule 7, a ROUTE). Borrow still holds
stock ahead of everyone and the lending order shows "lent to".

Goal: a confirmed Borrow becomes a planning choice only, like Reserve after #1919. Deciding and confirming on
the board must keep working exactly as today (owner's condition for #1919, kept here).

## Findings

Code read on main 71a43b3ba1 (file:line, backend `app/`):

- **One predicate.** `ProjectSupplyService._decision_allocation_query` (`services/project_supply_service.py:9827`):
  confirmed, has a bin, not Buy, decision ACTIVE or NULL. `_hold_query` (:9791) = it minus Reserve sources (:9825).
  Minus Borrow too, it matches no decision row at all.
- **Readers of `_hold_query`**: `_hold_rows` :9771 -> `_free_stock` :9710/:9740, `free_stock_by_location` :9685,
  `held_stock_by_location` :9594, `_holds_by_project` :9882 -> ladder caches :4813/:9306 -> `_held_at` :9901;
  `holds_at_locations` :9613; `_holds_by_holder` :6717 (confirm floor `_check_reserve_against_on_hand` :6624);
  Allocation panel `services/project_allocation_service.py:234`; board `project_fulfilment_board_service.py:1244`,
  :1257-1258, :2827-2829; `scm/location_stock_service.py:103-104`; `planning_change_service.py:2084`.
- **Stock Debt** `_holds` (`scm/stock_debt_service.py:1677`): one read of `_decision_allocation_query` (:1791, qty
  `held_qty_expr`), split Borrow -> pin (:1814), Reserve -> route (:1815), `Hold(route=...)` :1873-1887.
- **Walk** (`scm/supply_assignment.py`): `Hold.route` :351-353; a route skips step 1 (:728), registers :821-859,
  draws at the line's own step :1088-1104. Generic, no change expected.
- **Reorder runs** (`scm/reorder_run_service.py`): `_project_supply_reduction_map` :1290, Borrow-only default
  :1335/:1362-1363; `_apply_project_supply_reduction` :1396-1408 writes `retail_supply_reduction` (Borrow) and
  `project_supply_reduction` (with Reserve); `retail_net` :2767-2779; snapshot :3494-3496.
- **Not the hold, unchanged**: transfer proposal `_write_transfers` :8806 -> `stock_transfer_service.py:171`
  (decision snapshot only); buy-back `_borrow_shortfalls` :8131 -> `project_order_inquiry_service.py:5741`
  (payload); board donor cell `_lent_from` (`project_fulfilment_board_service.py:2033-2082`, decision snapshots);
  group-borrow donor-line ledger `_group_borrow_held_qty` :9132 (raw allocation qty, used :7296); step-3 supply
  Borrows are placement links (:8956-8963, `_place_supply_borrows` :7696).
- Stock Debt's "Lent to SO396071 (32)" is STOCK-DEBT-LENDABLE (landed goods, `stock_debt_service.py:2434-2442`),
  not a Borrow.

## Shape of the change (owner answers 28 Oct: (a) on all)

Reuse #1919's one shared rule, no per-screen copy:

1. `_hold_query` also drops `ALLOC_BORROW_SOURCES`. Every reader above follows (free = on hand less AutoCount
   reserved). The readers stay in place for this lane (they now net nothing); removing them is a cleanup with
   its own trigger: this lane merged and owner-tested.
2. Stock Debt `_holds`: every decision row is a route (no Borrow pin branch).
3. Reorder runs: retail deducts nothing for decisions; the project half keeps Reserve + Borrow.
4. Unchanged by design: confirm writes, transfers, ORDER_BACK rows, `_lent_from`, `_group_borrow_held_qty`,
   step-3 supply Borrow links. No frontend change.

## Red-first test list (UAC `borrow-no-hold-acceptance-criteria.md`)

Backend, Postgres scratch schema (`tests/_pg_fixture.py`), shapes from `tests/scm/test_board_no_hold.py`:

1. AC-BNH-1: Borrow route, date order (rewrite of `test_2_a_borrow_still_binds_first_at_any_date`).
2. AC-BNH-2: SO402757 shape 42 + 42 + 16 on one line, borrower earlier -> covered 100, nothing `pinned`.
3. AC-BNH-3 / -4: cross-group Borrow and BRW Borrow as routes.
4. AC-BNH-5: OI placement, step-3 supply Borrow link, landed, S/O pin still bind first.
5. AC-BNH-6: free / held / holds_at / location stock / Allocation panel ignore a Borrow (rewrites test_3, test_4,
   test_9 of `test_board_no_hold.py`).
6. AC-BNH-7 / -8: confirm a second order's Reserve and location Borrow on the same stock, no short recorded;
   the donor-line refusal still fires; transfer + ORDER_BACK unchanged.
7. AC-BNH-9: `_lent_from` unchanged.
8. AC-BNH-10: reorder retail figure ignores Borrow; project Buy keeps both (rewrite of test_8).

Plus old-rule tests that encode "a Borrow holds stock" (candidates: 35 files mention Borrow and a hold reader;
the tester narrows by running them red against the change), rewritten keeping their intent.

Kill tests (reviewer): put Borrow back into `_hold_query` -> 1, 5, 6 red; restore the pin branch in `_holds`
-> 1, 2 red; restore the retail Borrow deduction -> 8 red.

## Built

- `_hold_query` drops `ALLOC_BORROW_SOURCES` too (`project_supply_service.py` ~9799-9832): no decision row holds stock.
- Stock Debt `_holds`: every decision allocation is `Hold(route=True)` (`scm/stock_debt_service.py` ~1786-1882).
- Reorder runs: `_project_supply_reduction_map` has no `with_reserve` flag; it returns every non-Buy claim, which lowers
  the project Buy only; `retail_net = net + project_need`; `retail_supply_reduction` is gone from rows and snapshot.
- Tests: new `tests/scm/test_borrow_no_hold.py`; `test_board_no_hold.py` Borrow halves restated; 29 old-rule tests in
  11 files restated keeping their intent (none deleted). Related list (85 files): 1382 passed.
- Visible on the board: stock another project used to hold by a Borrow now reads free, so the ladder offers it as a
  Reserve rather than "Borrow from project X" (same as Reserve-held stock after #1919).

## Coordination

STOCK-DEBT-DECOUPLE #1667 (delivered qty consumes Reserve/Borrow before Buy) is rebasing onto #1919. This lane
bases on main and merges main again after #1667 lands.
