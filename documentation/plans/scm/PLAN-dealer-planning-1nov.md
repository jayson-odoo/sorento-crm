# PLAN: Dealer sales orders plannable on Fulfilment Planning

**Status:** PR 1 built on the briefed S track: flag exemption, own-pool netting fix, real reason. Retail widening is not in it; crew decision pending, recommendation in Open below. PR 2 not started: behaviour card first.

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

1. Exemption in `outside_fulfilment_planning`, using `pool_predicate.is_site_pool`.
2. **Own-pool netting (found while tracing, proved by running it).** A line at a pool is inside that pool's book, so 10 on hand and 10 ordered read net 0 and proposed Buy 10. `_stands_on_its_own_pool` in `project_supply_service.py` puts the line's owed quantity back, the arithmetic `_group_offer` does for a group (captain's rule, 26 Aug 2026). It is applied in `_apply_group_nets` and `_unit_fact`, so the walk, the board and the confirm check read one figure. A line at a project bin that draws the pool is untouched.
3. Real reason in the frontend. A flagged-off bin reads "Outside fulfilment planning", the reason the server already sends. A line with no location keeps "Needs a location". The cell count and the filter read "not plannable", because they cover both.
4. Regression: consignment borrow unchanged.
5. Guide: `documentation/user-guides/supply-chain/plan-undecided-lines.md`.

Results for a line of 10 at its own pool, 50% default share, due within the window:

| On hand | Other lines there | Proposal |
| --- | --- | --- |
| 0 | 0 | Buy 10 |
| 10 | 0 | Reserve 5, Buy 5 |
| 20 | 0 | Reserve 10 |
| 15 | 10 | Reserve 2, Buy 8 |

### Known limits, left on purpose

- **The dealer share still caps a project-class line at BRW.** It is the written rule for a project line (`available_for_project`), and only project-class lines reach the board in this PR. Retail lines are the ones it makes no sense for, so that decision belongs to the retail PR.
- **Two dates of one product on one order at its own pool** read cautiously: the walk's ledger is seeded once per product, so the later date can propose more Buy than strictly needed. A planner can amend it.
- **Own-arrival credit stays 0 at a pool**, because `_on_hand_at` reads the group list, which is empty for a pool. The line falls through to the pool share. Named by the trace at `project_supply_service.py:3852`, not separately tested.

## PR 2

Order inquiry recipients for dealer orders: To Josephine, Cc Joey, configurable. Behaviour card first, then build on the answers. The routing key is the owner's choice.

## Open

- **Widen to retail: not safe as designed, crew decision pending.** A retail line with a confirmed decision and a raised ORDER row counts twice: the book leg has no decided-line test (`scm/demand.py:503-510`, `:726-733`) and the confirmed leg has no class test (`:536-556`, `:736-770`). An All-scope run takes both (`:861`), so 10 owed with 0 on hand buys 20 (`reorder_run_service.py:2812-2816`). The Container Request drops the same line to 0 (`container_request_service.py:522,884`). The view fix needs a migration. Recommendation filed: ship this PR, demo on a project-class order at BRW, build retail as its own PR with a behaviour card.
- Whether the SO list has a class filter dealer CS can use: UNVERIFIED, only matters for the retail PR.
