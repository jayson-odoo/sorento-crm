# PLAN: Dealer sales orders plannable on Fulfilment Planning

**Status:** PR 1 (#2062) cut to the flag exemption and the real reason (crew ruling 1 Nov), re-review and browser pass on the final head next. PR 2 and PR 3 answered, start after #2062 merges. Tracks: PR 1 S, PR 2 M, PR 3 M.

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

1. Exemption in `outside_fulfilment_planning`, using `pool_predicate.is_site_pool`. Walk and confirm stay as on main, so no project line's answer can change.
2. Real reason in the frontend. A flagged-off bin reads "Outside fulfilment planning", the reason the server already sends. A line with no location keeps "Needs a location". The cell count and the filter read "not plannable", because they cover both.
3. Regression: consignment borrow unchanged.
4. Guide: `documentation/user-guides/supply-chain/plan-undecided-lines.md`.

### Known limits, disclosed on the PR and in the hand test

- **A line whose location holds just enough for it reads Buy.** 10 on hand, 10 ordered, nobody else: Buy 10, because the line's own demand nets the pool to zero, and a planner cannot reserve it by hand either. Measured on dev: 8 of 301 undecided project-class lines at these bins would answer differently, at most 1,399 of 19,942 owed units. PR 2 fixes it.
- **The stock pop-up can disagree on a line at a pool:** BRW row Available for Project 30 against Site pool 15, with nothing explaining it. PR 2 fixes and tests it.
- **The dealer share caps a project-class line at BRW**, the written rule, confirmed by the owner (card Q1).

### Why PR 1 was cut

An own-pool add-back was built here first. Four review rounds found faults in it, each in the walk and confirm that every project line uses: shared ledgers seeded from one line, a confirm that took less than the engine proposed, and other pools read above the true net. The work is kept on `crew/dealer-planning-retail-seed` (7c01a1a306) for PR 2.

## PR 2 (owner ruling, 1 Nov 2026)

Retail orders at dealer-segment locations work end to end in Fulfilment Planning: board, sales order list and class filter, decide, confirm, borrow, order inquiry email. Reorder-run demand counting is not changed, and neither is the committed view. PR 2 also builds the own-location read once, with Q1: a line at its own pool stops netting its own demand against that pool, retail takes no dealer share there, and the stock pop-up tells the truth. Start from the add-back, its tests and the reviewer's scenarios on `crew/dealer-planning-retail-seed`, kept in `crew/state/files/dealer-planning-pr2-seed` too. Those scenarios are its red tests. Open from that work: other pools must read one budget of the true net, spent as drawn, in the walk and at confirm (a line at the pool drawing two other pools above the true net confirmed short). The Loading Plan is in scope: its Lines tab is built by `container_request_service.py`, and a decided retail line vanishes from it (`:522`, `:782`, `:884`). The coverage reader is out.

## PR 3 (owner ruling, 1 Nov 2026)

The order inquiry handover email routes by sales order class: retail to dealer purchasing, project unchanged. To and Cc are explicit, and the owner edits them in System Management > Automation. The owner creates the retail automation row himself after release; no seed carries recipients.

## Answers from the owner and crew, 1 Nov (card)

- Q1 (a): no dealer share on a retail line at its own dealer location. Other locations and project-class lines at BRW keep it.
- Q2 (a): the Customer Service role gets `projects.projects.view`, `projects.projects.edit` and `scm.dashboard.view` in an additive migration, so production gets it on release. Pipeline and forecasts become visible to the role, accepted. Security review runs.
- Q3 (a): "other" counts as retail. No class stays off the board with a true reason.
- Q4 (a): retail email To dealer purchasing, Cc project purchasing and the raiser. The undo email follows the same class rule.
- Q5 (a): Type filter on the Fulfilment Planning list only, multi-select.

## Open

- Branches, agreed with crew: `crew/dealer-planning-retail` and `crew/dealer-planning-oi-route`, cut from main after #2062 merges. Red tests prepared locally until then.
