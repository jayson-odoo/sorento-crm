# PLAN: BOARD-NO-HOLD - a Fulfilment Planning decision is a plan, not a stock hold

Status: Plan (behaviour card + dry-run script; no code until the owner answers the card). Track: full
(size L, touches every free-stock reader). Lane is LEAD pattern (tester + coder + reviewer subagents).

## Journey

Owner, 27 Oct ~17:55 MYT: "board decision don't hold stock, board decision is just a planning choice".
Case CB4702: SO400884 (required 28 Dec) has a confirmed "Reserve from BRW 36" decision (21 Aug) that is
honoured first at any date, so SO426986 (earlier need) shows short while the 36 sit pinned.

## Findings

To be filled from the code read (file:line) in the next commit.

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
