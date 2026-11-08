# PLAN: Sorento Town (2.5D daily overview, cached snapshot)

Status: Step 1 (behaviour card) posted to the owner, revised with dev data 8 Nov, waiting on answers. Track: L (feature lane; new screen + new background job + new table). No code yet.

Lane: SORENTO-TOWN. Owner go: 8 Nov 2026 ~13:35 MYT. Research: crew report of 8 Nov (embedded in the lane brief).

## Hard rule

The town never runs a DB query per viewer. One leader-only scheduler job builds one gzip JSON
snapshot per company; `GET /api/v1/town/snapshot` reads Redis only. A test asserts the endpoint
makes no DB call.

## Order of work

1. Behaviour card (this file, section "Behaviour card") answered by the owner. **Blocks everything.**
2. Lavish static mock (one real company day from dev data) with an element -> component map.
   Build of the town screen starts only after the owner OKs the mock.
3. Phase 0 (snapshot backend) may start in parallel with step 2 once the card is answered.
4. Phase 1 MVP screen; Phase 2 life + team-first gamification.

## Behaviour card (owner decisions, each with a recommendation)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| 1 | Who sees RM amounts | (a) holders of `sales.reports.view` (+ superadmin/admin); others see counts only. (b) everyone with town access. (c) admin only | (a): the town total equals the sales report, so it inherits the sales report's permission (`sales.reports.view`, already used by 10 endpoints). Redaction happens server-side when the cached snapshot is served (two cached variants per company: full and redacted), never in the browser. |
| 2 | Which dealers get shops | (a) top 30 by 90-day invoiced sales (one sales calc), refreshed nightly; anyone invoiced today also gets a stall for the day. (b) every active dealer. (c) per-agent: my dealers | (a): ~30-50 buildings fits the <100 draw call budget; (b) is hundreds of buildings and no glance value. |
| 3 | What the "Approvals" sign counts | (a) purchase requests `approval_status = pending` (`PurchaseRequestHeader`, `models/procurement.py:1187`). (b) + project quotation documents awaiting approval (`models/projects.py:1245`). (c) + dealer-kit editions `pending_approval`/`resubmitted` (`models/dealer_kit.py:643`). (d) form SLA overdue | (a)+(b) for phase 1, shown as one number with a per-kind breakdown on click; form SLA overdue renders as "fires", not approvals, so it is not double counted. |
| 4 | May an office wallboard show customer names | (a) no: wallboard mode shows shop rank numbers and the total only. (b) yes | (a): a wallboard is a public screen (visitors, dealers' staff in the showroom). Names stay on the signed-in personal view. |
| 5 | Which reorder field drives the "!" | (a) `scm.ReorderLevel.level` (`models/scm.py:109`), buyer-owned, per product with optional per-location override; NULL = not set, no "!". (b) `Stock.reorder_point` (`models/inventory.py:134`). (c) `Product.reorder_level` (`models/product.py:346`) | (a): it is the field the SCM reorder engine plans against and only a person sets it, so a "!" means the same thing as a reorder suggestion. (b)/(c) are older mirrors; showing a "!" the buyer does not act on trains people to ignore it. |

### What dev data changed (8 Nov, crew data request; structural facts only, no real names or amounts on GitHub)

The real figures (one full day, top dealers, examples) live with the owner via crew, not in the repo.

- **Decision 2:** the 90-day all-types top 30 is roughly half project accounts plus related-company
  accounts; the Dealer sales type (`invoiced_sales.sales_type()`) excludes both. Sales are keyed per
  AutoCount debtor account, and one dealer company can hold several accounts (`[A/C I]`, `[A/C III]`),
  which reorders the top 30 when merged. Revised recommendation: **2a = top 30 Dealer-type customers by
  90-day invoiced sales, one shop per AutoCount account** (labelled with its account suffix), because
  that is exactly how the Invoiced report groups and the town total must match it; a project-sales
  "site" district and per-company merging are phase 2 options, not phase 1. The day banner still shows
  the all-types total (equals the sales report).
- **Decision 3:** every approval queue is near empty on a normal day (PR pending: 1; project quotation
  documents pending: 0; dealer-kit editions: 0). Recommendation unchanged ((a)+(b) one number), and the
  sign shows "All clear" at zero rather than disappearing. Note: `purchase_requests` has no company
  column, so the PR count is cross-company until that is fixed (snapshot shows it on every company's
  town; flagged for the owner).
- **Decision 5:** (b) `stock.reorder_point` is set on 0 of ~60k stock rows: drop it. (a) and (c) are set
  on ~11.3k products and equal on every product that has both (sourced from AutoCount). (a) has no
  per-location level rows, so a level is product-wide: "below" = product availability summed across
  warehouses. ~1.75k products sit below level, far too many to mark one by one. Revised recommendation:
  **5a, with the "!" on the warehouse district as a count ("1,7xx below reorder"), click -> the existing
  SCM reorder list; per-warehouse stock bars show volume, not "!"**, because a product-wide level cannot
  say which warehouse is short.
- **Warehouses:** 67 active SRT warehouses, most are sub-locations of a few pools (BRW, MWH, DC1, WH3,
  RSW, HQ ...). Recommendation: **one building per pool** (sub-locations folded in), so ~6-8 warehouse
  buildings, not 67.

## Phase 0 sketch (to be confirmed after the card)

- `app/services/town/snapshot.py`: build(company_id, day) -> dict, reads via optional replica URL (5 s statement timeout, fall back to primary), sales via `services/sales/invoiced_sales.py`.
- Leader-only APScheduler job in `app/scheduler/task_scheduler.py`, every 3 min 07:00-22:00 MYT, skip if a run is in flight.
- Redis `town:{company}:{date}:{full|redacted}` gzip JSON + version; end-of-day `town_day` row (snapshot + event log).
- `GET /api/v1/town/snapshot`: Redis only, ETag/304, ~30/min per user.
- Tests (red first): town total == sales report for the day; endpoint makes no DB call; redacted variant has no amount keys; rate limit.
