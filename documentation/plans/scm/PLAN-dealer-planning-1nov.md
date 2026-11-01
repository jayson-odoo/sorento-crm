# PLAN: Dealer sales orders plannable on Fulfilment Planning

**Status:** Planning. PR 1 scope waits on the crew decision below (widen to retail or not). PR 2 not started: behaviour card first. Track for PR 1: size S as briefed, M if widened.

UAC: `dealer-planning-1nov-acceptance-criteria.md` (beside this file).

## Journey

Dealer CS opens Fulfilment Planning, finds a dealer sales order at BRW, decides its lines, confirms, and the order inquiry email goes to purchasing. Project sales admin keeps working exactly as today, including the consignment borrow flow. Owner demo to dealer CS is Monday 2 Nov 2026.

## Measured facts

Read-only on dev copy `sorento_prod_1020`, 1 Nov 2026.

| Open sales orders | SOs | Lines |
| --- | --- | --- |
| BRW, retail | 1,561 | 13,985 |
| BRW, project | 231 | 1,140 |
| BRW, class unset | 2 | 28 |
| MWH, project | 6 | 7 |
| All active dealer-segment bins, retail | 1,617 | 14,509 |
| Project class, all active bins | 1,053 | 27,492 |

Retail is what dealer agents sell: 1,559 open dealer-segment SOs have a retail agent and retail class, 225 have a project agent and project class. `classify_document` derives the class (`app/services/scm/demand_class.py:87`, ladder at `:105`).

## The two gates

1. **The flag verdict.** `outside_fulfilment_planning` (`app/services/scm/planning_predicate.py:95-109`) marks a line unplannable when its bin is active and flagged off. Board `project_fulfilment_board_service.py:1709`, confirm `project_supply_service.py:9570`, `:6129`.
2. **The class filter.** Only `demand_class = 'project'` orders are admitted, so a retail order never reaches the first gate: board `:1632,1826,1933`, line drafts `project_line_draft_service.py:162`, adoption `project_so_adoption_service.py:346`, SO list `project_so_reconciliation_service.py:1452,1525`, OI import `project_order_inquiry_import_service.py:1726`.

## Architecture

- **Layer:** the shared predicate modules in `app/services/scm/`. No board-only or confirm-only special case.
- **Shared mechanism, gate 1:** `outside_fulfilment_planning` stays the one spelling. It gains one exemption using the existing `pool_predicate.is_site_pool(segment)`, so unset segment reads as dealer the same way every other screen reads it. The consignment early return stays first.
- **Shared mechanism, gate 2 (only if the widen decision is yes):** one predicate replaces the eight project-only sites, so the board, line drafts, adoption and SO list cannot disagree about which orders are admitted.
- **The flag is not ticked on BRW.** It would add a site pool to planning, netting and Stock Debt reads for every project line (`project_supply_service.py:11389-11409`, `scm/stock_debt_service.py:965,1015`).
- **Classes fixed:** every line at a dealer-segment bin, not BRW alone. MWH, RSW, WH3 and the unset-segment bins behave the same.
- **Classes not fixed, on purpose:** project-segment bins flagged off (BRW-SMC, MOCHA-WH) keep the verdict. Inactive bins keep theirs.

## PR 1

1. Red tests, then the exemption in `outside_fulfilment_planning`.
2. Trace what the ladder proposes for a pool-bin line, then prove decide, confirm and OI end to end on a BRW line.
3. Real reason in the frontend. `BoardDecisionPill.tsx:112,232-238`, `FulfilmentBoardListView.tsx:863-867,1266` and `BoardCellBreakdownDialog.tsx:519-520` say "Needs a location" for every unplannable line. A flagged-off bin must read "Outside fulfilment planning", the reason the server already sends in `sources[].reason` (`project_fulfilment_board_service.py:2786-2797`). A line with no location keeps "Needs a location".
4. Regression test: consignment borrow unchanged.
5. Guides: `documentation/user-guides/supply-chain/plan-undecided-lines.md`.

## PR 2

Order inquiry recipients for dealer orders: To Josephine, Cc Joey, configurable. Behaviour card first, then build on the answers. The routing key is the owner's choice.

## Open

- Widen to retail: filed with crew 1 Nov, waiting on the answer.
- Double-buy on a confirmed retail line against reorder runs: being traced.
- Whether the SO list has a class filter dealer CS can use: UNVERIFIED.
