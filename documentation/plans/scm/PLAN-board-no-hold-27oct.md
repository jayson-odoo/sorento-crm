# PLAN: BOARD-NO-HOLD - a Fulfilment Planning decision is a plan, not a stock hold

Status: Build, review round 1 fixes in progress. Owner answers 27 Oct: Q1 (a) the plan is a route; Q2 as today; Q3 Borrow unchanged in every way (only Reserve stops holding); Q4 (a) retail stops seeing a Reserve, the project-side Buy reduction pending crew-ask (built as kept); Q5 no wording change beyond losing `pinned` for a Reserve. Track: full
(size L, touches every free-stock reader). Lane is LEAD pattern (tester + coder + reviewer subagents).

## Journey

Owner, 27 Oct ~17:55 MYT: "board decision don't hold stock, board decision is just a planning choice".
Case CB4702: SO400884 (required 28 Dec) has a confirmed "Reserve from BRW 36" decision (21 Aug) that is
honoured first at any date, so SO426986 (earlier need) shows short while the 36 sit pinned.

## Findings

Code read on main e027b6b5 (file:line):

- **The one predicate.** `ProjectSupplyService._hold_query` (`app/services/project_supply_service.py:9787-9858`):
  confirmed, has a bin, not Buy (`source_type != 'order'`), decision ACTIVE or NULL. Quantity is
  `held_qty_expr()` (`:256`, capped at what the line still owes).
- **Readers of it**:
  - free stock `_free_stock` `:9706-9743` (on hand - AutoCount reserved - holds), via `_hold_rows` `:9767`;
    public `free_stock_by_location` `:9681`, `held_stock_by_location` `:9590-9607`, `holds_at_locations` `:9609`.
  - ladder caches `_drawable_free_stock` + `_holds_by_project` at `:4809-4812` and `:9300-9303`; Borrow donor
    figures `_donor_impact` `:9113` read `_held_at`.
  - confirm floor check `_check_reserve_against_on_hand` `:6623-6700` via `_holds_by_holder` `:6714`.
  - Stock Debt `_holds` `app/services/scm/stock_debt_service.py:1652-1830` (allocation half `:1761-1780`,
    turned into `Hold(kind=on_hand)` `:1841-1854`); bound first in `assign()` step 1
    (`app/services/scm/supply_assignment.py:676-790`, rule text `:24-43`).
  - board strip / group drill `app/services/project_fulfilment_board_service.py:1244-1258`, `:1511`, `:2827-2829`.
  - location stock `app/services/scm/location_stock_service.py:103-104`.
- **Not a reader of it but the same idea**: reorder runs take non-Buy allocations of active decisions off
  retail planning supply, `_project_supply_reduction_map` (`app/services/scm/reorder_run_service.py:1289+`).
- **Untouched by the ruling** (they are not board decisions): OI placements (`stock_debt_service.py:1782-1830`,
  `hop_hold` `:1856`), landed goods (`_landed_holds` `:2430`), the book's S/O pins (`_book_so_holds` `:2518`),
  AutoCount `quantity_reserved`.
- **Board queue**: covered lines leave the queue and print their frozen plan (`project_fulfilment_board_service.py:2748-2760`,
  `_apply_frozen` `:3194`); "covered" comes from `PLAN_DEMAND_LINE_SQL` (`app/services/scm/demand.py:77+`).
- **Buy demand**: project demand is only raised OI ORDER / ORDER_BACK rows (`demand.py:55-75`, `:525-555`).
- **Groups**: undecided demand never crosses an ownership group and never draws a site pool; a decision hold is the
  only cross-group move (`supply_assignment.py:36-43`, `may_draw` `:166-171`, walk `:1008-1017`).

Behaviour card: `CARD-board-no-hold-27oct.md` (posted as one crew-ask). Dry run: `sorento_crm_backend/scripts/board_no_hold_dry_run.py`.

## Shape of the change (after the owner answers)

One place: `_hold_query` stops matching decision allocations, so every reader above follows. Stock Debt's
allocation half then hands the walk a ROUTE instead of a hold: "this line may draw this bin, at its own date"
(card Q1 a), joined to `may_draw` for that line only. No per-screen copy.

## Red-first test list (owner answers 27 Oct: Q1 a, Q2 as today; Q3-Q5 trimmed to as today, Q4 a)

Backend, Postgres scratch schema (`tests/_pg_fixture.py`), seeded with the `_decided_line` shape of
`tests/test_project_supply_holds.py`:

1. **Stock Debt walk, CB4702 shape**: 36 on hand; later order (due +60d) has a confirmed Reserve of 36 at the bin;
   earlier undecided order (due +10d) needs 36. Expect earlier `covered` 36, later `short` 36 (today: later `pinned`,
   earlier `short`). Smoke-proven by the dry run.
2. **Free-stock figure**: `free_stock_by_location` = on hand - AutoCount reserved, with a confirmed decision present;
   `held_stock_by_location` = 0. Rewrites `test_project_supply_holds.py` AC-S1-1/5 (those assert the hold).
3. **Board strip / group drill**: free and held on the board's stock detail read the same as (2).
4. **Location stock**: `location_stock_service` free equals on hand - reserved with a decision present.
5. **Reorder runs** (Q4 a): a Reserve no longer lowers retail's figure (`retail_net`); a Borrow still does; the project
   half's own Buy is still lowered by both (Lane F, pending crew-ask).
6. **Route, cross-group** (Q1 a): a decided line in group BB planned from an IB bin draws that bin at its own date;
   an earlier IB line due first takes it first; an undecided BB line still cannot draw IB.
7. **Route, site pool** (Q1 a): a project line planned "Reserve from BRW" draws BRW at its date; an earlier dealer line
   on BRW is served first.
8. **Unchanged binders**: an OI placement on an SPO, landed goods for the line's own purchase, a PO S/O pin still bind
   first at any date (guards against the change leaking past `so_line_allocations`).
9. **Confirm**: two orders may both confirm Reserve 36 of a 36 pile; no short recorded for the second because of the first.
10. **Board queue as today** (Q2): a decided line Stock Debt reads short stays decided and out of the queue; no new
    buy demand row appears for it.
11. **Borrow as today** (Q3): a Borrow keeps holding everywhere (free stock, Stock Debt pin, confirm floor, reorder
    runs), the donor's "lent to" entry and the buy-back OI ORDER_BACK demand are unchanged.

No frontend change (Q5 trimmed to as today); browser pass checks Stock Debt + the board strip numbers only.

Kill tests (reviewer): put the old `or_(decision_id IS NULL, state = ACTIVE)` back in `_hold_query` and tests 1-5 must go
red; drop the route join and 6-7 must go red; widen the change to `_holds`' placement half and 8 must go red.

## Built (as of review round 1)

- One predicate: `_decision_allocation_query` (the old hold rule), `_hold_query` = it minus Reserve sources
  (`project_supply_service.py`); every free / held reader, the confirm floor and the Allocation panel read `_hold_query`.
- Stock Debt `_holds` splits the same read: Borrow -> pinned `Hold`, Reserve -> `Hold(route=True)`.
- `supply_assignment.py`: rule 7, a Reserve plan is a ROUTE (drawn at the line's own date, before its own group's pile;
  out-of-span bins via a stand-in only route lines draw, its untaken part never free stock).
- Reorder runs: retail's figure deducts Borrow only; the project Buy reduction keeps Reserve + Borrow.
- Planning-change reallocation: `_reserve_rival` also fires on an all-Buy re-run, capped by the Reserve bin's live free stock.
- One confirm still cannot give the same pile twice (kept); separate confirms may plan the same stock, Stock Debt decides by date.
- `scripts/board_no_hold_dry_run.py`: one-shot, models the rule on the pre-wiring engine (6dc173c2); retired before merge.
