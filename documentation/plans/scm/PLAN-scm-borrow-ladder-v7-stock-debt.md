# PLAN - Borrow ladder v7 and the Stock Debt view

Status: **APPROVED 2026-08-29** (captain: "the logic is robust, let's proceed"; scenario table on SRTWB242 signed off). Grilled in session (R1-R23), lavish review rounds 1-6 (R24-R36). Tickets: see section 4 / GitHub issues linked below. UAC: `scm-borrow-ladder-v7-stock-debt-acceptance-criteria.md`. Sits on `PLAN-scm-order-unit-ladder-v6.md` (units, donor ledger), `PLAN-demo-followups-19aug-ladder-v2.md` section E (ownership groups, window, coverage date), `PLAN-scm-planning-inline-decisions.md` (board editor, one Confirm), ADR-0011 (no bucketed arithmetic).

## 0. The captain's ask (29 Aug 2026, after the client demo)

Reading SO381895 on `/project-sales/fulfilment-planning`:

- The ladder should be use own location -> borrow -> pool. Delivery date is NOT a factor in whether own stock can be used: Available negative means no.
- Borrowing from another location and borrowing from another order are ONE thing with ONE basis: borrow an order with a later delivery date (not 2030 = TBA), which creates a **stock debt** for that order in the month its date falls in; the debt must be replenished before that date.
- Stock debt is every outstanding sales order without supply, not only order-backs. A month x product view shows the debt per month; the objective is zero or surplus in every month.
- When on hand cannot fill a debt, the nearest incoming can be moved to it, which creates a debt for the order that incoming was for, at a different month, unless that order is too near its date.
- An order that "cuts the queue" (near date, arrives late) creates a debt now; the same process reallocates on hand or incoming to it.

## 1. What exists today (verified in code and on the dev DB, 29 Aug)

- Ladder v5/v6 (`front_planning_engine.propose_line:414`, candidates built in `app/services/project_supply_service.py`): gate (`reorder_coverage_until`, reserve window) -> own GROUP take (`_group_take_candidates:1644`, basis `group_offer = max(group_net + own qty, 0)`, `group_net = on_hand - SO + SPO` over every `*-<group>` bin) -> site POOL (`_pool_chain:1560`, `pools_net`) -> cross-group borrow of free stock (`_cross_group_borrow_candidates:2001`, donor group net, small-quantity cap) -> whole-unit Buy. Pool before borrow is pinned by `tests/scm/test_ladder_v5.py:149`.
- Borrow from another ORDER is not a rung (25 Aug ruling, `front_planning_engine.py:47-51`): `_group_borrow_donors:1891` feeds only the manual `BorrowAddDialog`, gated same-agent or lower-rank.
- No rung reads the donor's date; no 2030 / TBA / NULL filter exists in the ladder. The asker's date is read by the gate, the water timeliness test (`_group_water:1765`), and the rank.
- Debt already persists: every borrow writes an `ORDER_BACK` inquiry row at the donor's required date (`_borrow_shortfalls:4178`) and `so_line_allocations.donor_impact_snapshot`; the reorder run reads ORDER_BACK rows as committed demand at the donor warehouse (`demand.py:481`). A pool draw writes nothing.
- Incoming: not a rung, sits inside `group_net`; arrival = `eta_delay_date > estimated_arrival_date > expected_date` (`_spo_rows:5657`); line-level placement exists only as `order_inquiry_links.spo_allocation_id | po_line_id` written by Link SPO / `_draft_links_for_decision:4103`.
- No product x month projection anywhere. `coverage_timeline.py` is the pure dated running balance (`build_timeline:153`, `closing_balance:219`); `group_by_month:230` has no production caller. Board buckets are display only.
- Warehouses: `segment` (`project` 55 active bins / `dealer` 5 pools), `counts_as_available`, `pool_warehouse_id`, `is_active`. Groups are the code suffix. Flagged-in groups BB/IB/IR/NTC/AM = 23 bins; HP, RSV, SMC, SYNT, ACT, S/L, PSM, ACTS, BILL, CLR, MOC, R/S are out.
- Policy: `scm.priority_policy` one active row, `reorder_coverage_until`, `cross_group_borrow_max_qty/_pct` (migration `ed706a98ddc6`), edited on `/scm/policies` `FulfilmentPriorityPanel.tsx`. Alembic head `442_notice_recipients_opens`.
- Data: open SO lines 1,246 / 363k units dated 2030-01, 160 undated, ~600 past-due. Open SPO 725 lines, all arriving Aug 2026 or earlier, 721 with no container, 14 undated. Open PO lines with no SPO 2,864 / 773k units, `expected_date` on line or header, mostly Jul-Oct 2026, 6 undated. So the supply timeline is real and dated.

## 1.5 Review round 1 rulings (lavish, 29 Aug)

- **R24** Rung 1's pile is date-aware: an earlier-dated line of the group takes the stock first, so a later line reads Available 0 at its date even when the bin holds stock today. This replaces the 27 Aug "no date order" reading of Available; the number is unchanged when nothing earlier competes.
- **R25** Borrowing from a decided donor supersedes that decision inside the same Confirm, reason `Borrowed by SO<asker> line <n>`.
- **R26** S3 (on-hand borrow) and S4 (incoming borrow) ship as two PRs.
- **R27** A borrow names WHAT it borrows: on hand, an SPO (arriving), or a PO line (on order). Rung 2 = on hand only; rung 3 = SPO first (nearest arrival), then PO lines arriving by the asker's date.
- **R28** A Stock Debt cell opens a lightbox with TWO tables: the demand lines due that month and the supply arriving or held for that month, both with their assignments. Every cell is clickable, TBA and No date included.
- **R29** A PO line's `expected_date` is the SO delivery date the line was bought for (the users type it in), NOT an arrival. Arrival = `issue_date + supplier lead time`. Verified on SRTWB242: PO 202605-S0072's line dates 14 Aug / 19 Aug / 15 Sep / 30 Sep / 15 Oct are exactly the open SO due dates for the product.
- **R30** (Q-D) The bought-for date is display only (lightbox "bought for ..."); PO supply is FIFO like everything else. A PO is ON ORDER, the SPO cut from it is what ARRIVES; PO counts net of the SPO placed on it and always after SPO in rung 3.
- **R31** (Q-E) Overdue incoming (arrival passed, nothing received; today every one of the 725 open SPO lines is Aug 2026 or earlier) is NOT counted as supply until it gets a new date; the lightbox lists it as "overdue, not counted".
- **R32** (ruled round 4) A supply document (SPO, then PO) is taken when it arrives by the asker's date OR before a fresh buy would land (`as_of + lead`): the line is then `late` but earlier than buying. Captain, on row 4: "if buy, it is going to arrive even later".
- **R33** (ruled round 4) Never half and half: one step, ONE document, whole unit. SPO 5 + PO 7 for a unit of 12 is not a proposal.
- **R34** (ruled round 4) The pool runs the same three steps on its own (dealer / retail) book: free pile, then later pool orders' on hand, then their supply; a pool order that lends receives an ORDER_BACK at its date. AC-L13 ("a pool draw raises nothing", `test_ladder_v4_group_netting.py:284,345`) retires. Hot-selling gate kept.
- **R35** (Q-H) Inside step 2 several on-hand donors may combine for one unit (one timing); the one-document rule (R33) applies to step 3 only. PO (3b) is offered only when no single SPO covers the unit.
- **R36** (round 6) The trail and the decision panel list EVERY option with the date it would fulfil the unit and the days late: use own (today, +2 days with a transfer), borrow on hand (same), SPO (arrival), PO (issue + lead), pool, buy (today + lead). The proposal stays the first whole option; Amend picks another. `propose_line` therefore returns the full option list with `fulfil_date`, not only the chosen composition.
- Ladder v7.1 after round 3: 1 USE free supply (own group, then other project groups; no debt) -> 2 BORROW ON HAND from later orders across all project groups (same agent, latest date, same group, nearest bin) -> 3 BORROW SUPPLY held by a later order, one document, SPO before PO, eligible per R32 -> 4 POOL, same three steps on the pool book -> 5 BUY. Section 3.2 is the rewritten form.
- Scenario table on SRTWB242 (19 rows) lives in `mockups/borrow-ladder-v7-stock-debt-plan.html` section 8; the key insight: under FIFO by date an earlier line never borrows from an UNPINNED later line of its own group, it takes the pile first and the later line goes short (debt appears in its month, no ORDER_BACK). Borrow arises when the supply is pinned (decision or link) or sits in another group.

## 2. Journey

In the UAC. The planner decides on the board as today; the Stock Debt view shows; the admin flags bins and sets the TBA date.

## 3. Design (simplest thing that works)

### 3.1 One assignment, read by both the ladder and the view (R21)

New pure module `app/services/scm/supply_assignment.py` (no I/O, golden-tested, same discipline as `coverage_timeline.py`; it reuses `TimelineEvent` and `build_timeline` for the running balance):

```
assign(product, *, as_of, tba_from, lead_days, supply: [SupplyEvent], demand: [DemandLine], pinned: [Hold]) -> Assignment
```

- `SupplyEvent`: kind `on_hand | spo | po`, warehouse, date (on hand = as_of; SPO = arrival precedence above; PO = `issue_date + lead time`, R29), qty, ref (spo_number / po_number + line), and for a PO line `bought_for` = its `expected_date` (Q-D decides whether it pre-assigns). A PO line's qty is its open quantity minus the SPO already placed on it (R11, AC-S2-4).
- `DemandLine`: so, line, warehouse (group derived), agent, required_date, open_qty, decided hold (qty + source) or none.
- Walk: pinned holds first (a confirmed allocation binds its supply to its line, any date). Then events chronologically per ownership group: supply adds to that group's free pile; a demand line at its date draws from the pile oldest-first. A line that cannot draw at its date is `short`; if supply later covers it, `late`. Lines on/after `tba_from` and undated lines draw nothing and go to `tba` / `undated` (R14, AC-S2-3). Past-due uncovered demand lands in the current month (AC-S2-5).
- Output: per line `{assigned: [(event, qty)], uncovered, status covered|late|short|pinned}`, per month cumulative balance + tone, `tba`, `undated`.

Months are display grouping of the dated arithmetic, as ADR-0011 requires; `group_by_month` finally gets its caller.

Facts feeding it come from the readers that exist: `_stock_context` / `group_netting` for on hand, `_spo_rows` for SPO, a new `_po_rows` over `purchase_order_lines` net of `spo_allocations.po_line_id`, `_facts_for` for demand, `so_line_allocations` for pinned holds. One new predicate `fulfilment_planning_predicate` (in `pool_predicate.py`'s style) applied by every reader (AC-S1-5).

### 3.2 Ladder v7.1 (R1, R2, R13, R24, R32-R36)

`propose_line` walks, per planning unit (v6), in this order, and a step either covers the WHOLE unit or gives nothing (R10, R33): gate (unchanged) -> `use` -> `order_borrow` -> `supply_borrow` -> `pool` -> `buy`. Constants: `RUNG_ORDER_BORROW`, `RUNG_SUPPLY_BORROW` added (`incoming_borrow` in the UAC text is this rung); `RUNG_CROSS_GROUP_BORROW` kept for reading frozen snapshots only. Every step is also reported as an OPTION with its `fulfil_date` and `days_late` (R36), chosen or not.

1. **use** (rung `group_take`): the asker's own group's free pile from `assign()` at the asker's date (supply here by then, minus lines due before the asker; later lines never count, R24), drawn own code first then siblings by code as today; then the other project groups' free piles the same way (no debt: free means owed to nobody). Negative = empty = nothing. In the one-date case the number equals today's `max(group_net + own, 0)`, so `test_ladder_v4_group_netting.py` keeps its figures; it differs only when earlier-dated demand exists, which is the point.
2. **order_borrow**: donors = `assign().lines` with `status covered|pinned` whose assignment holds `on_hand` events, in ANY flagged project group (R5), filtered by the window (`required_date >= as_of + lead + 14`, reusing `reserve_window_end`), not past-due, not TBA, not undated (R3, R12, AC-S3-4), never the asker's own order; ordered `(same_agent desc, required_date desc, same_group desc, same_warehouse desc)` (R4, R19). Several on-hand donors may combine for one unit (R35, one timing). Capped by a donor ledger keyed by donor line inside `compose_lines` (today's `borrow_left`, re-keyed, AC-S3-9). Component: kind `borrow`, rung `order_borrow`, `donor_so_number`, `donor_line_no`, `donor_agent_code`, `same_agent`, `donor_required_date`, `donor_core_line_id`, `order_back_qty = qty` (fields exist on `Component`). A decided donor (R9) is offered like any other; on Confirm `_write_decision` supersedes its active decision with `superseded_reason = "Borrowed by SO<asker> line <n>"` in the same transaction (R25) and its next board build re-proposes it. ORDER_BACK raised by `_borrow_shortfalls` as today (AC-S3-5).
3. **supply_borrow** (S4): ONE document covering the whole unit (R33). Candidates = supply events (`spo`, then `po`, R27/R35: a PO only when no single SPO covers) that are free or assigned to an eligible later order (same window and donor order as step 2), eligible when the document arrives by the asker's date OR before a fresh buy would land (`as_of + lead`, R32); SPO nearest arrival first. Component kind `borrow` (or `reserve` when the document was free), rung `supply_borrow`, `source = spo:<n> | po:<n>/<line>`, arrival carried; sentence `Borrow 50 arriving 15 Sep 2026 (SPO ...) from SO...` / `Take 32 on order (PO ... line 3, arriving about 16 Nov 2026)`. On Confirm the placement link moves (3.3).
4. **pool** (rung `pool`, R34): the SAME three steps run on the pool's own book (the site pools' on hand, their SPO/PO, and the dealer / retail SO lines at the pools by required date): free pile at my date -> later pool orders' on hand (window rule) -> their supply (one document, R32). A pool order that lends receives an ORDER_BACK at its own date; AC-L13 ("a pool draw raises nothing") retires with `test_ladder_v4_group_netting.py:284,345`. The hot-selling gate stays in front of the whole step. `pools_net` / `pool_reserve_capacity` are replaced by the pool's `assign()` (one more group with `is_pool = true` in the assignment, its demand = the pool's own open lines).
5. **buy**: whole unit, `fulfil_date = as_of + lead`.

Trail (`project_fulfilment_board_service._trail`): five questions (AC-S3-11) plus the options table (AC-S3-14); the borrow sentence names what is borrowed, the donor, agent, date, warehouse and the debt month. `BorrowAddDialog` reads the same candidate list, same order.

Retired: `cross_group_borrow_max_qty/_pct` columns and reads, the two panel inputs, `_cross_group_borrow_candidates`, `_pool_chain` / `pool_reserve_capacity` (replaced by the pool assignment). Tests move to v7.

### 3.3 Placement links on Confirm (S4, R8)

On Confirm of a `supply_borrow`: an `order_inquiry_links` row for the asker's ORDER_BACK-verb row on that `spo_allocation_id | po_line_id` for the borrowed qty; the donor's link on the same placement reduced or removed; the donor's ORDER_BACK row raised at its date. The rule that only an ORDER_BACK row may name an allocation (`OrderInquiryLink` docstring) is kept: the asker's row IS an order-back against something already ordered. `assign()` reads links as pinned supply, so the view moves the quantity between the two months with no further work (AC-S4-3). A free document (nobody assigned) writes the asker's link only.

### 3.4 Stock Debt view (S2, R15, R16, R22, R23)

- Route `GET /api/v1/project-sales/stock-debt` (list, paginated by product, `query`, `group`, `only_debt`) and `GET /project-sales/stock-debt/{product_id}/cell?month=` returning `{demand: [...], supply: [...]}` (R28). Service `stock_debt_service.py` builds the supply/demand inputs for the page of products in one read each (no per-product queries) and calls `assign()`. Tone per month: `red` when the month starts before `as_of + lead` (cannot buy in time), `amber` when negative later, `green` otherwise. Permission `projects.stock_debt.view`, grant sweep from `projects.projects.view` (pattern of `419_stock_transfers.py`).
- FE `app/(protected)/project-sales/stock-debt/`: `page.tsx` (RequireAccess), `StockDebtClient.tsx` (DataGrid, fixed layout, sticky product column, month columns generated from the payload, `useStockDebtQuery`, `stockDebtService.ts` with the contract at the top), `StockDebtCellDialog.tsx` (lightbox, two DataGrids: Demand with the Plan link, Supply with source, arrival and assigned-to). Menu entry under Project Demand after Fulfilment Planning (`menu.config.tsx:242` and the second nav at `:1829`). Empty state CTA flips `only_debt` off. No explanation copy on screen.
- Cell tone uses the DataGrid cell class, not a new component; the toggle and the group select are the shared toolbar's.

### 3.5 Flag and policy (S1, R17, R20)

Migration `443_fulfilment_planning_flag_tba_date`: `warehouses.fulfilment_planning boolean not null default false`, seeded true where `is_active and warehouse_code ~ '-(BB|IB|IR|NTC|AM)$'`; `scm.priority_policy.tba_date_from date not null default '2029-01-01'`; drop the two cap columns; permission row + sweep. Downgrade mirrors. Bootstrap_env mirrors the seed (CI DB is bootstrap, not migrations; lesson from #363).

Warehouse schema + `PUT /warehouses/{id}` gain the field; the Warehouses list gains the column and the edit modal the switch. `FulfilmentPriorityPanel` swaps the two cap inputs for the date input; policy schema + `priority.py` expose `tba_date_from`.

### 3.6 What is deliberately NOT built

- No debt table. Debt is computed from the book, and the persisted parts (ORDER_BACK rows, links, allocations) already exist. Trigger for a table: the view is too slow over the whole catalogue after the one-read-per-input service (measure on the prod copy: ~4k flagged products).
- No alert, email or job on "date nears" (R16): colours only.
- No per-group table for the flag (R17): one boolean per bin.
- No change to the reorder run: it already reads ORDER_BACK and committed demand.
- No new Playwright spec; agent-browser evidence runs per slice.

## 4. Slices (tracer bullets, in order; each = Phase 1 FE mock -> Phase 2 BE test-first -> Phase 3 review -> PR)

| Slice | Content | Migration | Estimate |
| --- | --- | --- | --- |
| S1 | Flag + TBA policy field + shared predicate; Warehouses column/switch; panel input; readers honour the flag | 443 | 2 days |
| S2 | `supply_assignment.py` (pure, golden; groups incl. the pool, pinned holds and links, overdue excluded R31) + `_po_rows` + stock-debt service/routes + Stock Debt page + cell lightbox (demand + supply) + menu + permission sweep (in 443) | - | 5 days |
| S3 | Ladder v7.1 steps 1, 2, 4, 5: use (date-aware, other groups' free), `order_borrow` + ledger + decided-donor supersede, pool on the same algorithm with pool ORDER_BACK, options with fulfil dates in trail + panel, v4/v5/v6 test rewrites, SO381895 + SRTWB242 evidence runs | - | 6 days |
| S4 | Step 3 `supply_borrow` (SPO then PO, one document, R32 eligibility) + link moves on Confirm + wording | - | 3 days |

S1 first (everything reads the flag). S2 before S3 (the ladder consumes a tested `assign()`). S3 and S4 are two PRs (R26). One coder per worktree; S2's FE mock and S1 can run in parallel slots.

## 5. Testing seams

- `supply_assignment.assign()` pure: golden fixtures in `tests/scm/fixtures/supply_assignment/*.json` (AC-S2-1..5).
- Ladder: `tests/scm/test_ladder_v7_borrow.py` on Postgres (`tests/_pg_fixture.py`), seeded chain per test (CI DB is empty).
- Routes: happy + permission denial + 422 on the policy date.
- FE: vitest on `StockDebtClient` states (mock `useListingColumnPreferences` for DataGrid rows in jsdom), `StockDebtCellDialog`, `FulfilmentPriorityPanel`, Warehouses column.
- E2E: agent-browser runs AC-S2-13, AC-S3-13, AC-S4-6 by sidebar from `/`, 375 + 1280.

## 6. Risks and open points for the plan review

1. ~~Rung 1 becomes date-aware~~ ruled R24.
2. **Assignment cost over the whole catalogue.** One read per input for a page of products; if the list is still slow on the prod copy, the trigger in 3.6 fires.
3. **Existing snapshots** carry `cross_group_borrow` components; they render unchanged (rung constant kept for reading).
4. ~~Superseding a donor's decision on Confirm~~ ruled R25; the planning-changes page shows it.
5. **Lead time for the tone** = the product's lead (supplier performance, else `product_suppliers.standard_lead_time_days`, else 90), the same source the window uses.
