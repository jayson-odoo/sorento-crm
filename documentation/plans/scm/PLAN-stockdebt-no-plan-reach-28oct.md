# PLAN: STOCKDEBT-NO-PLAN-REACH - the Stock Debt view walks a decided line as if it had no decision

Status: Merge-ready pending CI + owner hand test (PR #1945; red-first 10 of 26 new tests red before the fix, green after; reviewer READY; browser pass PASS at 1280 + 375). Track: full
(size M by the brief; the diff itself is small: one parameter in the view, the rest is tests). Base: main
f64f4db1 (carries #1919 BOARD-NO-HOLD and #1935 BORROW-NO-HOLD).

## Journey

Owner, 28 Oct ~09:00 MYT, on CB4702 Dec 26 (Project book view): "I don't want to take from BRW even if the
plan says 'Reserve from BRW'", and the line should draw only what the Supply tab shows. Then the key rule at
~09:40, which supersedes the earlier OI-link wording: "I need it to be same behaviour as now, except it is
independent of the planning; even if plan says reserve from BRW, it doesn't care, and how it draws is the
same as other lines that don't have a decision".

So in the Stock Debt view, a line WITH a board decision (Reserve own / BRW / group take, Borrow, Buy) draws
exactly as the same line WITHOUT a decision does today. Nothing else changes: OI placement links, the book's
S/O on PO / SPO lines, received-SPO pins and landed goods work as they do for an undecided line now.

Owner condition (kept from #1919): deciding and confirming on the Fulfilment Planning board work exactly as
today. The board and the ladder keep reading a decision as a route.

## Findings (main f64f4db1, backend `app/`)

- The view (`StockDebtService._assignments(view=True)`, read by `list`, `cell`, `_projection_series`,
  snapshots and exports) and the board / ladder (`assignments_for`, view=False) share `_holds`.
- `_holds` (`services/scm/stock_debt_service.py` ~1797) read every live decision allocation through
  `ProjectSupplyService._decision_allocation_query` and handed each to the walk as `Hold(route=True)`.
- The walk (`services/scm/supply_assignment.py` rule 7, ~817-859 register, ~1088-1104 draw) lets a route
  line draw the named bin at its own date, standing up a bin outside the span. That is how SO400884 read
  "Covered, On hand BRW" in the project book while its Supply tab said "Supply (0)": the stood-up pool bin
  is not listed (`cell` lists stand-ins only for PINNED takes).
- A route to the line's own bin or a sibling bin of its own group adds nothing the group pile does not
  already give it (equivalence tests own / brw-own / group_take / borrow-sibling were green before the fix).
  Only the reach outside the group (another group, a site pool, a bin outside the span) differs.
- Received-SPO rule (owner 09:15, kept, unchanged): received SPO leaves supply (`spo_supply.
  open_incoming_clauses`, `_supply`); its on hand stays with the linked SO (`_holds` received hop, `_landed_holds`).
  Pinned by `test_4_a_received_spo_stays_with_its_linked_so_and_is_not_supply` (auto and hand links).

## Shape of the change

1. `_holds(..., routes=True)`; `_assignments` passes `routes=not view`. In the view no decision row is
   read, so a decided line walks as undecided. Board / ladder unchanged.
2. No frontend change, no migration, no change to the walk itself (rule 7 stays for the board).

What else shifts: board free strip NO, ladder NO, confirm NO, reorder runs NO (own reduction map),
snapshots / exports / MCP / chatbot stock-debt reads YES (they read the view).

#1667 STOCK-DEBT-DECOUPLE (delivered-first route sizing) is moot for the view: with no route there is no
route to size. It could still matter on the board, which is not this lane.

## Red-first tests

`tests/scm/test_stockdebt_no_plan_reach.py`: CB4702 project book (Short 36, month -656, Covered by only names
listed supply), whole book, board still routes; cross-group Borrow; own-bin plan in date order; OI links
unchanged (auto and hand); received SPO kept; and the equivalence decided == undecided over 8 plan shapes x
2 spans. Older tests that asserted view routes now assert the new answer, and their route mechanics are
asserted on the board walk instead (`test_board_no_hold.py` 7 / 7b, `test_borrow_no_hold.py` AC-BNH-3 / 4,
`test_stock_debt_stale_pin.py`, `test_stock_debt_routes.py`, `test_stock_debt_walk_once.py`,
`test_stock_debt_projection_linked_only.py`).

## Measured reach (dev copy 20 Oct, read-only, crew 28 Oct)

The SQL below as written: 104 lines / 3,740 qty (brw 90 / 3,496, other_location 12 / 229, own 2 / 15).
Tighter bound, summing `held_qty_expr` (caps at what the line still owes, cancelled = 0) instead of raw
`a.qty`: **62 lines / 2,475 qty** still owe anything and can flip (brw to a site pool 54 / 2,253;
other_location to another group 4 / 202; other_location to a site pool 2 / 5; own to a site pool 2 / 15).
The other 42 are delivered or cancelled and cannot flip. 62 / 2,475 is the upper bound.

## Count SQL (dev clone, read-only)

Upper bound on Stock Debt view lines whose reach changes: open lines whose live confirmed plan names a
bin outside their own group, or a site pool. A line flips only if that plan was what covered it.

```sql
SELECT count(DISTINCT sol.id) AS plan_reach_lines, sum(a.qty) AS plan_reach_qty
FROM projects.so_line_allocations a
JOIN projects.sales_order_lines psl ON psl.id = a.so_line_id
JOIN public.sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
JOIN public.sales_orders so ON so.id = sol.sales_order_id AND so.status = 'open'
JOIN public.warehouses wa ON wa.id = a.warehouse_id
JOIN public.warehouses wl ON wl.id = sol.warehouse_id
LEFT JOIN projects.so_supply_decisions d ON d.id = a.decision_id
WHERE a.confirmed_at IS NOT NULL AND a.source_type <> 'order'
  AND (d.id IS NULL OR d.state = 'active')
  AND (substring(wa.warehouse_code from '-([^-]+)$') IS DISTINCT FROM
       substring(wl.warehouse_code from '-([^-]+)$')
       OR EXISTS (SELECT 1 FROM public.warehouses c WHERE c.pool_warehouse_id = wa.id));
```
