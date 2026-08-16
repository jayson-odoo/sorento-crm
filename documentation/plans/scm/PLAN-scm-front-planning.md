# PLAN: SCM Front Planning

**Status:** FINALIZED, grilled and pre-code, 16 August 2026

**UAC:** `documentation/plans/scm/UAC-scm-front-planning.md`

**Classification:** MIXED. Core sales-order commitments remain in `public`; Project Sales
workflow records remain in `projects`; planning facts and recommendations remain in `scm`.

**Depends on:** `PLAN-project-sales-pipeline.md`, `PLAN-scm-order-inquiry-as-demand.md`,
`PLAN-scm-planning-mode-ledger.md`, `PLAN-scm-m8-reorder-planning-daily.md`,
`PLAN-scm-m9-stock-allocation-transfer.md`, and `PLAN-scm-reorder-copilot.md`.

**Implementation baseline:** `origin/feat/project-lead-to-so` at
`aab24c0c3550e2837b52abdff1342126acdaabe5`.

## 1. Guided journey

### 1.1 Actor and first screen

The primary actor is Customer Service, working from **Project Fulfilment Planning** after a
customer Project PO and delivery schedule have been accepted. Purchasing is the downstream
actor in the existing SCM plan. The industrial process is order promising and supply
allocation, but the user-facing name stays task-oriented.

Before CS opens the sheet, the system already knows:

- the accepted Project PO version, delivery schedule, product resolution, and required dates;
- the Project SO draft and its AutoCount reconciliation status;
- free unclaimed stock by location, stock already committed to another SO, and the shared BRW
  pool;
- SPO quantities allocated to each location and their expected arrival dates;
- existing per-location reorder levels, classifications, supplier constraints, and the frozen
  SCM planning inputs;
- the SO classification source facts and its persisted deterministic demand class.

### 1.2 Happy path

1. The accepted Project PO and schedule produce a release proposal grouped into the intended
   AutoCount SO worksheet.
2. CS reviews the proposed release and creates the Project SO draft.
3. The AutoCount worksheet is exported, uploaded after AutoCount creation, and reconciled to
   the Project SO, including a stable link for every Project SO line to its core SO line.
4. The whole Project SO enters **Needs CS review**. It is not yet committed purchasing demand.
5. CS opens one side sheet. Each line shows open quantity, timely location SPO coverage, proposed
   Reserve, proposed Borrow, proposed Buy, the required date, and evidence for every source.
6. CS adjusts components line by line. Borrow shows donor impact and requires a reason.
   Discontinued Buy shows a warning and requires a reason.
7. CS presses **Confirm Project SO** once. The server rechecks every line and commits all line
   decisions atomically. If any line is stale or unbalanced, no line is confirmed.
8. Only the confirmed Buy residual for each line is handed to Order Inquiry. Reserve, Borrow, and
   timely or late incoming are not purchasing demand.
9. The next SCM run reads the confirmed unplaced Buy once. The buyer can select **Plan grain:
   Product** or **Plan grain: Location**, separately from **Planning mode: Auto / Manual**.
10. Product grain shows one row per product, with stacked Project, Retail, and unclassified
    readings in the SO and Suggested columns. Supplier MOQ and order multiple are applied once to
    the product total. Location grain shows the same frozen location facts with the channel
    breakdown visible. The selected decision grain is the only actionable grain.
11. PO linkage, keying, receipt, cancellation, and amendment events reduce or replace the open
    Buy balance through the existing planning ledger rules.

### 1.3 End state

Customer demand is promised from named supply, Purchasing sees only the confirmed unplaced Buy
residual, and the buyer can explain the product total down to location and SO-line evidence.
No demand, stock, incoming supply, or purchase decision is counted twice.

## 2. Process stages and ownership

Use these SCM practice names in documentation and UI help:

| Stage | Business owner | Durable output |
|---|---|---|
| Demand capture | Project Sales / CS | Accepted Project PO and dated schedule |
| Sales-order release | CS | Project SO draft and AutoCount worksheet |
| Order reconciliation | CS | Project SO linked to core SO header and lines |
| Order promising and supply allocation | CS | One atomic confirmed supply decision for the Project SO |
| Purchase requirement handoff | CS to Purchasing | Order Inquiry rows containing Buy residual only |
| Replenishment planning | Purchasing | Product and location projections from one frozen SCM run |
| Purchase execution | Purchasing | Decision set from the run's selected grain, supplier, keying state, and PO linkage |

The chain is:

```text
Accepted Project PO + schedule
  -> release proposal
  -> Project SO draft
  -> AutoCount worksheet
  -> upload and line reconciliation
  -> Needs CS review
  -> atomic Project SO confirmation
  -> confirmed Buy residual only
  -> Order Inquiry
  -> frozen SCM run
  -> Product or Location plan grain
  -> one purchase decision
  -> PO linkage and fulfilment ledger
```

## 3. Binding operating contract

### 3.1 Project SO confirmation is atomic

Confirmation is at Project SO level, never per line. The side sheet remains line-oriented
because CS must inspect and adjust the composition of each line, but line rows have no durable
partial-confirmation state.

Before confirmation:

- the entire SO is **Needs CS review**;
- none of its lines contributes Project Buy to Order Inquiry or SCM purchasing demand;
- draft suggestions may be recomputed without creating claims or purchasing demand.

At confirmation, for every line `l` in the Project SO:

```text
open_so_qty(l)
  = timely_spo_coverage(l)
  + reserve_qty(l)
  + borrow_qty(l)
  + buy_qty(l)
```

All terms are non-negative and expressed in the SO line UOM. `open_so_qty` is the current core
SO-line quantity still requiring fulfilment at confirmation time. `timely_spo_coverage` is the
line's deterministic share of the incoming SPO leg of product-location supply through its required
date. Stock remains in Reserve or Borrow. The coverage comes from the location projection in
section 3.5 and is not a persisted SPO-to-SO-line allocation.

The confirmation transaction must:

1. lock or otherwise concurrency-protect the Project SO revision and all affected stock and
   dated location-supply facts;
2. verify that every Project line has a unique reconciled core SO line;
3. recompute open quantity and timely SPO coverage from authoritative records;
4. recheck Reserve availability, the hot-selling BRW cap, Borrow donor impact, reasons, and
   discontinued warnings;
5. verify the balance invariant for every line;
6. write one SO decision revision, every line snapshot, all component allocations, any
   cross-project Borrow claims, and all Buy components;
7. create or refresh the corresponding Buy-only Order Inquiry rows; and
8. commit all writes together.

One stale or invalid line rolls back the entire transaction. The response identifies every
failing line by human-readable SO line number and item code. It does not expose UUIDs.

A material SO amendment, line remap, quantity change, required-date change, or source challenge
supersedes the active revision and returns the whole SO to **Needs CS review**. Existing placed
or received supply is preserved in the ledger and shown as an exception; it is never silently
deleted or bought again.

### 3.2 Deterministic component suggestion

The engine proposes a composition. It never uses an LLM or a new optimizer to generate
quantities.

For each line, in order:

1. Start with current `open_so_qty`.
2. Propose Reserve from eligible free unclaimed opening stock under section 3.3.
3. Apply timely SPO coverage from the line's product and location, arriving on or before the
   required date. An SPO arriving after the required date is advisory at that date.
4. Propose Borrow only from stock outside Reserve eligibility or stock committed to another SO.
5. Set Buy to the remaining positive residual.

Steps 2 and 3 follow the section 3.5 attribution order: opening stock first, then timely SPO, with
lines processed by required date, SO number, line number, then internal line ID.

The output is evidence-backed and deterministic for the same snapshot. The system may rank
candidate locations for presentation, but ranking does not change quantities without the
stated rules.

### 3.3 Hot-selling test and BRW Reserve constraint

This plan reuses the existing SCM ABC facts. It adds no analytics subsystem or threshold knob.

**Dealer hot-selling test:** a product is dealer hot-selling when this query-equivalent predicate
is true for at least one row:

```text
scm.item_classification.product_id = product
AND scm.item_classification.abc_class = 'A'
AND warehouses.segment = 'dealer'
AND warehouses.is_active = true
AND warehouses.counts_as_available = true
```

`scm.item_classification` already has one current row per product and warehouse, so no freshness
threshold is added and `computed_at` is display evidence only. If no classification row exists
for any qualifying dealer warehouse, the product is not hot-selling and the sheet shows
**Retail classification unavailable**. If rows exist but none is ABC A, it is deterministically
not hot-selling. The shared BRW pool is resolved through the fulfilment warehouse's existing
`pool_warehouse_id`, never by parsing a warehouse code. This warehouse use is only a
stock-protection test. Project versus Retail demand classification still follows section 5.2.

Reserve eligibility is then:

- **Dealer hot-selling:** dealer-facing free stock is excluded from Reserve. Reserve may draw
  only from the shared BRW pool, and only above BRW's own per-location reorder level.
- **Not dealer hot-selling:** Reserve may draw from free unclaimed stock in the SO's fulfilment
  location or from shared BRW. Stock outside that pool, or stock committed to another SO, is
  Borrow.

For a dealer hot-selling product:

```text
brw_protected_level = COALESCE(BRW per-location reorder level, 0)
brw_reserve_cap = MAX(BRW free unclaimed stock - brw_protected_level, 0)
reserve_qty = MIN(remaining need, brw_reserve_cap)
```

The general Q7 rule applies: an absent or NULL location level contributes `0`. This makes the
rule computable from existing data while keeping every configured BRW protection unit intact.
Borrow may still deliberately use a non-Reserve source, including dealer stock, but only through
the explicit CS confirmation in section 3.4.

**Worked example:** Product P is ABC A at a dealer-facing location, so it is hot-selling. Its
Project line has open quantity 70 and no SPO arrives by its required date. Dealer-facing free
stock is 50, BRW free unclaimed stock is 120, and BRW's reorder level is 80. The cap is
`120 - 80 = 40`. The proposal is Reserve 40 from BRW, timely SPO coverage 0, and a residual 30 for
Borrow or Buy. The 50 dealer-facing units and BRW's protected 80 are not consumed by Reserve. If
CS selects 10 dealer units as Borrow with a reason, Buy becomes 20 and the line balances at
confirmation.

### 3.4 Borrow and discontinued Buy

Borrow requires exactly one approval: explicit confirmation by the CS actor confirming the
Project SO. The sheet must show source location or donor SO/project, quantity, projected donor
shortfall or days-of-cover impact from the current snapshot, and a required reason. No second
approver, donor-CS acceptance, or rules-engine workflow may block confirmation.

For cross-project Borrow, reuse `projects.allocation_claims`: the atomic SO transaction creates
the claim directly in its existing terminal accepted state, with `requested_by` and `decided_by`
set to the confirming CS actor, `decided_at` set to the confirmation time, and the required
reason retained. The matching `so_line_allocations` row links through `claim_id`. There is no
intermediate requested state. For free stock at another location outside the Reserve pool, write
an `other_location` allocation with no claim row because there is no donor project. Both forms
freeze donor impact on the allocation row.

Buying a discontinued product for committed customer demand is allowed. The Buy component must
show a discontinued warning and requires a reason before SO confirmation. The warning and reason
are frozen with the decision revision. The product is not silently substituted.

### 3.5 Incoming SPO treatment

Incoming SPO is dated location supply, not a CS decision and not an SO-line link. The existing SPO
warehouse allocation identifies the location. For product `p`, location `w`, and date `d`:

```text
availability_by_date(p, w, d)
  = stock(p, w)
  + SUM(SPO incoming(p, w) arriving on or before d)
  - SUM(outstanding SO(p, w) required on or before d)
```

The shared location-projection boundary owns all ordering and source attribution. Timeline events
sort by date, then kind with supply before demand, then SO number, then line number with missing
numbers last, then the internal SO-line ID. The line ID is a final stable key only and is never
displayed. Demand lines consume sources in that order: opening stock first, then SPO arriving on or
before the line's required date. Eligible SPO sources sort by arrival date, SPO number, SPO line
number with missing numbers last, then allocation ID. This order is used by the timeline, the line
proposal, and confirmation recomputation; database return order never participates.

Supply before demand on the same day reverses the existing shared `coverage_timeline._sort_key`
order, which places demand first and is pinned by
`tests/scm/test_coverage_timeline.py::test_same_day_demand_is_ordered_before_supply`. Stage 1C
changes `_sort_key` and that pinned test together, and the new order applies to every consumer of
the shared timeline: the reorder engine, the `summary_order_service` Coverage Timeline panel, plan
exceptions, and coverage routes. There is one ordering contract and no per-consumer divergence.

An SPO arriving on the required date therefore counts at that date. The calculation may explain
which SPO rows contributed, but it creates no `spo_allocation -> sales_order_line` ownership and no
`order_link_claim` chain. An SPO arriving after a line's required date is advisory for that need and
contributes no coverage at that date. For the line balance, stock consumed by the attribution is
represented only by Reserve or Borrow and incoming only by timely SPO coverage, so the combined
availability formula never counts either unit twice.

Worked attribution: eligible opening stock is 10, one SPO of 10 arrives on the required date, and
SO-100 has two 10-unit lines for the same product, location, and date at line numbers 10 and 20.
Line 10 receives Reserve 10 from opening stock; line 20 receives timely SPO coverage 10. Reversing
database row order does not change that result. If line numbers tie, internal line ID decides the
order.

## 4. Order Inquiry handoff

Order Inquiry is a purchase-requirement handoff, not an independent netting engine.

- A confirmed decision creates one active inquiry row per SO line with `buy_qty > 0`.
- The row quantity is exactly that confirmed Buy residual.
- Lines with Buy 0 create no active purchase row.
- Reserve, Borrow, timely SPO coverage, and late incoming never appear as Order
  Inquiry demand.
- Reconfirmation supersedes prior unplaced rows idempotently. Placed or received quantities stay
  in the purchase ledger and produce an exception if the new need is lower.
- The SCM reader counts current confirmed, unplaced Buy directly. It does not subtract customer
  delivery again and does not repeat the pre-order or inbound netting already decided by CS.
- On new runs the single owner of Project demand is confirmed unplaced Buy in
  `projects.order_inquiry_rows`, joined to core `sales_order_lines` through
  `projects.sales_order_lines.core_sales_order_line_id` and the fulfilment warehouse. The legacy
  sheet leg (`sales_orders.demand_origin = 'scm_order_inquiry'`) is read only for SOs with no
  confirmed CS decision, so a sheet-named SO that CS later confirms counts once: the confirmed Buy
  replaces the sheet quantity.

This explicitly replaces two behaviors on the implementation baseline:

| Baseline behavior | Required target |
|---|---|
| `ProjectSODraftService.publish` calls `derive_for_sales_order` before AutoCount reconciliation and CS supply confirmation. | Inquiry is created or refreshed inside atomic SO confirmation only. |
| `ProjectOrderInquiryService` independently nets pre-order and inbound pools and emits operational verbs. | The standard demand row carries confirmed Buy residual only; coverage evidence belongs to the SO decision. Amendment exception verbs may remain separate from new-demand rows. |

`PLAN-scm-order-inquiry-as-demand.md` still governs idempotent adoption and lifecycle accounting,
but its demand quantity is narrowed by this plan to confirmed Buy.

## 5. SCM plan presentation and calculations

### 5.1 Separate selectors

The UI uses two independent controls:

- **Plan grain: Product / Location** selects how the purchase requirement is viewed and worked.
- **Planning mode: Auto / Manual** retains the existing policy vocabulary from
  `PLAN-scm-planning-mode-ledger.md`.

Neither selector replaces or overloads the other.

### 5.2 Deterministic Project and Retail classification

Project versus Retail comes from the existing import and publish classification path. Persisted
`sales_orders.demand_class` is authoritative for planning. There is no AI, warehouse, or
fulfilment-location inference.

The deterministic mapping is:

- `_classify_demand` checks the stored SO `order_type`, then the stated import `order_type`, then
  the customer's market segment, then the sales agent's persisted demand class;
- for each textual order-type or market-segment source, any normalized value containing `project`,
  `projects`, or `contract` maps to `project`, including `subcontractor`, and every other stated
  value maps to `retail`;
- today two stamp points exist: `outstanding_import_service._classify_demand` at outstanding-order
  import (including AutoCount upload, where core SOs arrive), and
  `project_order_inquiry_import_service`, which writes `order_type = 'project'` and
  `demand_class = 'project'` directly on sheet-created SOs, bypassing the mapper; the target routes
  that direct stamp through the same mapper. `ProjectSODraftService.publish` writes no core SO and
  is not a stamp point. The persisted field is the semantic owner read by planning;
- a missing persisted `demand_class` after those sources are evaluated is a data-quality exception
  and does not create a third demand class.

Channel is not a location set. A Project SO may be fulfilled from BRW and remains Project; a Retail
SO may use another location and remains Retail. Every demand line carries its parent SO's persisted
class at its actual fulfilment location. The mapping reuses the unchanged substring semantics in
`app.services.scm.demand_class.class_of`; it is not a new configurable rules engine.

### 5.3 Product grain with channel breakdown

Product grain shows exactly one row per product for the company and frozen run. Channel is analysis
inside that row, never row identity. The SO and Suggested columns stack these readings:

- **Project:** confirmed unplaced Buy for Project-class lines summed across every fulfilment
  location, without another stock, SPO, PO, or delivery netting pass;
- **Retail:** normal netted Retail-class need summed across every fulfilment location;
- **Unclassified:** demand whose persisted class is missing, shown as an exception and excluded
  from an actionable suggestion until classified.

The shared read model keeps one aggregate row per product and location. Its Project, Retail, and
unclassified demand columns are separate, while stock, dated SPO incoming, PO supply, and reorder
level remain single shared facts of that product-location. Location grain displays those columns
beside the shared supply. Product grain sums each demand breakdown across locations and exposes
expandable channel ledgers and a location drill without repeating shared supply.

At each location `w`:

```text
project_need(p, w)
  = confirmed unplaced Buy for Project-class lines fulfilled from w

retail_free_supply(p, w)
  = existing shared free-supply calculation
  - confirmed Project Reserve and Borrow claims against w

retail_need(p, w)
  = existing normal netting of Retail-class outstanding SO against retail_free_supply

project_buy_qty(p)
  = SUM(project_need(p, w)) across locations w

retail_replenishment_qty(p)
  = SUM(retail_need(p, w)) across locations w

product_raw_need(p)
  = project_buy_qty(p) + retail_replenishment_qty(p)

product_suggested_qty(p)
  = apply_supplier_MOQ_and_multiple_once(product_raw_need(p))
    at the frozen uom_decimal_places
```

Project Buy is firm demand: Retail free-supply netting never reduces it. Applying supplier
constraints once to the actionable product row avoids buying one MOQ for every location or demand
channel. On new runs `order_summary_row.suggested_qty` is this value; it replaces the existing
`summary_order_service.write_rows` derivation that sums per-location `rounded_qty` and then
`math.ceil`s to a whole unit. No Product-versus-Location reconciliation bridge or rounding delta
exists because both views read the same channel-aware location facts. No AI-generated quantity,
optimizer, or extra policy knob is added.

### 5.4 Location grain and decision ownership

Location grain remains a permanent selectable and actionable Buy mode. It reads the existing
recommendation workflow extended with the frozen demand-class split. At each product-location it
shows Project need, Retail need, and shared stock, SPO, PO, reorder, and policy evidence. It retains
the existing decision and override workflow. Both grains use the same run, as-of time, facts,
supplier inputs, source revision, and per-product UOM `decimal_places` snapshot.

Each new front-planning run has exactly one actionable `decision_grain`:

- `product`: the single product `scm.order_summary_row` owns the chosen quantity. Its PO-worklist
  split reruns the existing `reorder_engine.allocate` deterministically with `chosen_qty`, the
  frozen location inputs, and the `decimal_places` frozen on the summary row. Allocation works in
  those integer minor units, persists the resulting decimal location quantities, and makes their sum
  exactly equal `chosen_qty`; no proportional rescaling formula is added. Location recommendations
  are read-only under this grain.
- `location`: existing `scm.reorder_recommendation` decisions and
  `scm.recommendation_override` rows remain actionable. The Product row is a read-only aggregate
  of their chosen quantities.

The buyer may inspect both views at any time. The first saved decision locks `decision_grain`
permanently for that frozen run. The lock is atomic: every Product or Location decision write
first takes a row lock on the `scm.reorder_run` row (`SELECT ... FOR UPDATE`) in the same
transaction as the decision write, then sets `decision_grain` when NULL or rejects the write when
it holds the other grain, so two concurrent first decisions can never persist competing grains. If
the buyer needs the other grain to become actionable after a decision, a new current run must be
created from a new frozen input snapshot; the old run and all of its decisions remain immutable
and auditable.
PO worklists read only the run's selected grain.
This preserves two real Buy planning modes without allowing both to order the same requirement.

Runs created before this contract are legacy. They keep their existing recommendations, overrides,
and product summary rows unchanged and read-only. They accept no new Product or Location decision,
`decision_grain` is not backfilled, and the buyer must create a new front-planning run to act.
Their new channel-breakdown fields remain unavailable; no semantic backfill is attempted.

### 5.5 Reorder-level rule

Product reorder level is a shared product fact and the deterministic sum of per-location levels.
It is calculated once, not once per demand channel:

```text
product_reorder_level
  = SUM(COALESCE(scm.reorder_level.level, 0)) for concrete locations
```

An absent location row and a NULL location value both contribute 0. Product-wide
`warehouse_id = NULL` rows are not used as a competing level for this view. There is no inferred
winner, buyer worklist, migration to one product row, or **Needs level** state in Product grain.
Location grain continues to read the individual per-location values and applies the same NULL as 0
rule. The Product row references this shared evidence once.

## 6. Target data model

Reuse the implementation branch and current SCM schema first. Names below are the target
contract for later migrations; this PR creates no schema.

### 6.1 Reused Project Sales records

- `projects.po_versions`, `projects.po_lines`, `projects.delivery_schedules`, and schedule cells
  remain the accepted demand and date source.
- `projects.sales_orders` remains the Project-to-core SO header link through `so_id`.
- `projects.sales_order_lines` remains the Project line. Add nullable
  `core_sales_order_line_id` referencing `public.sales_order_lines.id`, then require a unique
  reconciled link before confirmation.
- `projects.so_line_allocations` remains the component ledger. Keep the established source values
  `own`, `brw`, `other_project`, and `order`, and add only `other_location` for the explicit
  outside-pool Borrow case. Add `decision_id`, `reason`, and `donor_impact_snapshot` while
  retaining source location and donor references. UI mapping is `own` and `brw` to Reserve,
  `other_project` and `other_location` to Borrow, and `order` to Buy.
- `projects.allocation_claims` may retain historical requested/accepted records, but new Borrow
  confirmation must not wait in a donor approval state. Cross-project Borrow creates a claim
  directly as accepted in the atomic CS transaction; `requested_by` and `decided_by` are the
  confirming actor, `decided_at` is the confirmation time, and `reason` is required. Other-location
  Borrow has no claim because no donor project exists.

### 6.2 Atomic decision revision

Add `projects.so_supply_decisions`:

- `id`, `company_id`, `project_sales_order_id`, and `revision_no`;
- `state` with `active`, `superseded`, and `challenged` values;
- `source_revision`, `line_snapshots`, `confirmed_by`, `confirmed_at`, `supersedes_id`,
  `superseded_at`, and `superseded_reason`;
- unique active revision per Project SO and unique `(project_sales_order_id, revision_no)`.

`line_snapshots` is one small JSON object per included line. It freezes line number, Project and
core line identifiers, product, location, required date, open quantity, timely SPO coverage and its
dated location-supply references, Reserve, Borrow, Buy, suggestion basis, lifecycle warning, and
required reason. The existing normalized `so_line_allocations` rows remain the confirmed components and
are grouped atomically by `decision_id`. This is the report's narrow decision header corrected
from line grain to SO grain for Q6, not a new generic workflow or a second allocation model.
Authoritative stock and SPO warehouse-allocation records remain in their existing tables;
identifiers in the snapshot provide the audit path. No SPO-to-SO-line FK or claim is added.

### 6.3 Order Inquiry reuse

Reuse `projects.order_inquiries` and `projects.order_inquiry_rows`. Add `supply_decision_id` to
each standard Buy row and enforce one active unplaced row per active decision and SO line.
Existing fields such as `so_line_id`, item code, quantity, delivery date, location, state, and
actor remain useful. The standard new-demand verb is Buy/Order only; legacy coverage verbs are
not produced for a confirmed decision. SCM reads these rows through the section 4 join path and
precedence over the legacy sheet leg.

### 6.4 SCM reuse and deltas

- Keep `scm.committed_v` and its consumer `scm.net_position_v` at exactly one aggregate row per
  `(product_id, warehouse_id)`. Add Project, Retail, and unclassified demand columns to that same
  row while retaining the existing aggregate committed column and join keys for current consumers.
  The Project column reads only current confirmed, unplaced Order Inquiry Buy through the
  section 4 join path and passes it through as firm need; the `demand_origin = 'scm_order_inquiry'`
  leg contributes only for SOs without a confirmed decision. The Retail column keeps the existing
  open-SO basis for normal netting. Front planning reads the split columns; shared stock, SPO, PO,
  and reorder facts remain single product-location values and never gain a demand-class row
  dimension.
- Add `front_planning_contract_version` and `decision_grain` (`product` or `location`) to
  `scm.reorder_run`. Existing runs keep both NULL. New runs set contract version `1`, leave
  `decision_grain` NULL until the first decision, and then lock it under the section 5.4 row lock.
  Decision services reject every write when the contract version is NULL, so legacy runs are
  read-only without a decision-grain backfill.
- Keep the existing `scm.reorder_recommendation` identity. For each concrete-location fact used by
  front planning, store its Project, Retail, and unclassified demand breakdown plus references to
  shared location supply in the existing `inputs` snapshot. On new runs location need is
  `project_need + retail_need`: Project need bypasses net-position subtraction, Retail retains
  normal netting of Retail-class demand only after confirmed Project Reserve and Borrow claims
  reduce free supply, and unclassified demand is excluded from the actionable need in both grains.
  No `demand_class` row key or duplicate supply row is added.
- Keep the existing `scm.order_summary_row` identity and unique key `(run_id, product_id)`. New runs
  still write one row per product. Add nullable Numeric `project_buy_qty`,
  `retail_replenishment_qty`, and `unclassified_demand_qty`, nullable Date
  `earliest_project_need_date`, nullable JSONB `channel_calculation_basis` as the frozen channel
  breakdown, and nullable SmallInteger `uom_decimal_places` copied from the product's base UOM at
  calculation. Existing decision, keying, worklist, and response operations remain keyed by run
  and product, with no channel identifier. New runs require the three quantities, the
  basis, and `uom_decimal_places` after calculation; `earliest_project_need_date` is required only
  when `project_buy_qty > 0` and is otherwise NULL. Chosen-quantity validation and allocator
  replay read `uom_decimal_places` from the row, never live UOM master data, so a later UOM edit
  cannot change a frozen run. Existing rows remain untouched and their new fields stay NULL; they
  are not split, duplicated, defaulted, or made actionable.
- Re-base the existing `order_summary_row.project_demand`, `dealer_outstanding`, and their line
  counts on persisted `sales_orders.demand_class` for new runs: `summary_order_service
  ._demand_aggregates` classifies open SO lines by `demand_class` instead of exact `order_type`
  membership, `summary_order_service.demand_drill` filters by the same persisted `demand_class`
  with its `dealer` kind exposed as retail, a missing `demand_class` counts as unclassified, and
  `dealer_outstanding` is exposed as `retail_outstanding` in the new API and UI while the column
  name stays. The row then carries
  two Project measures with one owner, shown side by side: `project_demand` is open Project-class
  SO quantity and `project_buy_qty` is confirmed unplaced Buy. Legacy runs keep their stored
  values on the old basis, read-only.
- Write `suggested_qty` on new runs as section 5.3 `product_suggested_qty`, rounded once at
  supplier MOQ and multiple and the frozen `uom_decimal_places`, replacing the
  `summary_order_service.write_rows` sum of per-location `rounded_qty` plus `math.ceil`. Reuse the
  other existing summary-row quantity, supplier, and keying fields. Do not add a frozen cash field:
  `cash_committed` remains the live `chosen_qty` and cost calculation in
  `summary_order_service.po_worklist`, while frozen `cash_impact` remains owned by each
  `ReorderRecommendation`.
- Add `decimal_places` to `public.units_of_measure` as a SmallInteger constrained to `0..4`.
  Products read it through their existing `base_uom_id`; a missing value during rollout resolves
  to `0`. Backfill from the lowercased, trimmed UOM name only, before making the field non-null;
  the UOM code is not used, so code `EA` with name `Kilogram` is a measure unit.
  Exact count aliases `ea`, `each`, `piece`, `pieces`, `unit`, `units`, `pc`, `pcs`, `set`, and
  `sets` receive `0`. Exact measure aliases are `kg`, `kilogram`, `kilograms`, `g`, `gram`, `grams`,
  `m`, `meter`, `meters`, `metre`, `metres`, `cm`, `centimeter`, `centimeters`, `centimetre`,
  `centimetres`, `l`, `liter`, `liters`, `litre`, `litres`, `ml`, `milliliter`, `milliliters`,
  `millilitre`, `millilitres`, `m2`, `m²`, `square meter`, `square meters`, `square metre`,
  `square metres`, `m3`, `m³`, `cubic meter`, `cubic meters`, `cubic metre`, and `cubic metres`.
  Measure units receive the greatest observed fractional scale after trailing zeroes are removed,
  capped at `4`, across `order_lines.quantity`, `sales_order_lines.qty_ordered`,
  `sales_order_lines.qty_delivered`, `sales_order_lines.qty_required`,
  `purchase_order_lines.qty_ordered`, and `purchase_order_lines.qty_received` for products using
  that base UOM. Every unknown name receives `0`; no historical quantity is rewritten.
- UOM model, create/update/response schemas, `UnitOfMeasureService` list serialization, canonical
  master ingest, and frontend create/edit/detail surfaces carry `decimal_places`. Create defaults a
  missing value to `0`; edit preserves the stored value when omitted; every write validates `0..4`.
  List, detail, and select responses return it. This is canonical UOM divisibility, not SCM
  arithmetic precision or a planning-policy knob, and it is not inferred from `conversion_factor`.
- Extend the non-durable shared projection input with `line_no` and core `line_id`. Reconciled
  Project lines supply their human line number; a missing line number sorts last. Extend
  `CoverageService._demand_events_many` and `TimelineEvent` to carry both values, and change
  `coverage_timeline._sort_key` to the section 3.5 order, including its same-day supply-first
  reversal for all timeline consumers. The internal ID never enters a user-facing response.
- Add the narrow child `scm.order_summary_location_allocation` with `order_summary_row_id`,
  `reorder_recommendation_id`, `warehouse_id`, and Numeric `allocated_qty`. When Product `chosen_qty`
  changes, generalize and rerun
  `reorder_engine.allocate(chosen_qty, frozen_location_inputs, decimal_places)` with the summary
  row's frozen `uom_decimal_places` and persist its output. The decision boundary rejects
  `chosen_qty` with more fractional places than that snapshot permits. The allocator scales the
  accepted total and the frozen location deficits by `10^decimal_places`, rounds only the total to
  an integer, leaves demand-rate weights unconverted so branch selection and surplus weights are
  unchanged, reuses its deterministic largest-remainder allocation, then converts the children
  back to decimal quantities. Enforce one
  row per summary row and warehouse, non-negative quantities, company scope, and a
  transaction-time invariant that child quantities sum exactly to the parent's stored `chosen_qty`.
  Do not rescale a prior split. This is persistence for the PO worklist, not a new allocator or
  subsystem.
- `scm.reorder_level` remains per location. No consolidation migration or product-level winner
  is added. The product value is calculated as the sum in section 5.5.
- `scm.item_classification` supplies the existing ABC hot-selling fact.
- Persisted core `sales_orders.demand_class` supplies channel ownership. The existing import and
  publish precedence is stored `order_type`, stated `order_type`, customer market segment, then
  sales-agent demand class. Text sources use the unchanged substring behavior of
  `demand_class.class_of`; a missing result is the classification exception.

The intentional NULL values above are durable legacy markers, not a deferred semantic backfill.

All new durable rows are company-scoped, follow existing audit conventions, and use service-layer
transactions. No new service boundary, rules engine, optimizer, or LLM quantity path is needed.

## 7. Rollout plan

Each stage follows `PRINCIPLES.md`: approved UAC and plan, Phase 1 frontend mock, Phase 2 backend
TDD and implementation, Phase 3 code review and Definition of Done. This document is the
pre-code contract only.

### Stage 0: Contract and data readiness

- Confirm the core SO-line link, classification precedence and stamp points, channel demand columns
  on `scm.committed_v`, dealer-facing locations, ABC evidence, legacy-run identification, UOM
  name classes and observed quantity scales, and SPO location/date source against
  production-shaped fixtures.
- Pin mapper cases for `project`, `projects`, `contract`, and `subcontractor` as Project and an
  ordinary non-matching stated segment as Retail. Pin stored order type, stated order type,
  customer market segment, and sales-agent fallback precedence, the two existing stamp points
  (outstanding import and the sheet import's direct stamp), that publish does not stamp, and the
  missing persisted-class exception.
- Add contract tests that demonstrate the implementation baseline's early inquiry, partial line
  confirmation, and second-approver Borrow behaviors before replacing them.
- Produce no buyer or CS feature behavior yet.

### Stage 1A: Project PO to AutoCount release worksheet

- Implement the guided release proposal and worksheet handoff from the accepted Project PO and
  schedule.
- Keep all resulting demand uncommitted and outside Purchasing.

### Stage 1B: AutoCount upload and reconciliation

- Reconcile the AutoCount SO header and every line to the Project SO.
- Enter **Needs CS review** only after a unique line mapping exists.
- Show the Phase 1 side-sheet mock before backend behavior is written.

### Stage 1C: Order promising, confirmation, and handoff

- Implement deterministic incoming, Reserve, Borrow, and Buy suggestions.
- Implement the hot-selling BRW rule, Borrow and discontinued reasons, atomic SO confirmation,
  revision supersession, and Buy-only inquiry rows.
- Implement the shared section 3.5 ordering and source attribution, including the same-day
  supply-first reversal of `coverage_timeline._sort_key`; update
  `test_same_day_demand_is_ordered_before_supply` to the new order in the same change and pin the
  two-line worked case, including identical results when database row order is reversed.
- Replace early publish derivation, per-line partial confirmation, independent inquiry netting,
  and second-approver Borrow on the named implementation branch.

### Stage 2: Product plan and channel breakdown

- Add the independent Plan grain selector and retain Planning mode.
- Extend the single-row shared committed read model and frozen recommendation facts with Project,
  Retail, and unclassified demand columns, shared supply, firm Project Buy, normally netted Retail
  need, and location drills.
- Add and backfill UOM `decimal_places`, expose it in UOM master-data create and edit with `0..4`
  validation, and preserve the `0` fallback during rollout.
- Keep one Product row, freeze its UOM `decimal_places` snapshot, add its stacked channel readings
  and expandable ledgers, re-base `_demand_aggregates`, `demand_drill`, and `project_demand` /
  `dealer_outstanding` (`retail_outstanding` in the API and UI) on `demand_class`, replace the
  `write_rows` per-location rounded sum with `suggested_qty` rounded once at supplier constraints
  and the frozen `uom_decimal_places`, and persist the durable allocator-rerun location split.
- Pin mixed-channel same-location demand, Project Buy pass-through, decimal chosen-quantity
  allocation at UOM precision, unavailable legacy breakdowns, and rejection of every legacy-run
  decision write.
- Keep both grains actionable, lock one decision grain per run, and make PO worklists consume only
  that grain.

### Stage 3: Reorder-level rollup and hardening

- Calculate Product reorder level as the sum of per-location levels with NULL or absent as 0.
- Keep Location grain reading its per-location levels.
- Add aggregation, allocation-balance, concurrency, amendment, cancellation, missing-classification,
  classification-age-does-not-change-the-predicate, high-volume, authorization, audit, and
  company-isolation tests.
- Do not add a level-convergence worklist, a product-level winner, or a **Needs level** state.

## 8. Verification strategy

The binding cases are in `UAC-scm-front-planning.md`. Implementation must provide:

- focused backend pytest coverage for every balance, atomicity, classification, idempotency,
  concurrency, lifecycle, and isolation rule;
- frontend Vitest coverage for selectors, calculations, validation, warnings, and empty/error
  states;
- headless `agent-browser` flows from the normal navigation for the CS confirmation and buyer
  planning journeys, including console and network checks;
- a test report keyed to every UAC ID.

No browser run is required for this documentation-only PR.

## 9. Risks and controls

| Risk | Control |
|---|---|
| Partial commitment leaks to Purchasing | One SO-level transaction; no active decision or inquiry rows until every line balances |
| Same incoming or stock covers two lines | One dated product-location projection, stable line and source ordering, concurrency protection, and recheck at commit |
| Confirmed cover remains free in a later proposal | The same confirmed claim read reduces CS free stock and Retail planning supply before either calculation |
| Order Inquiry buys coverage again | Buy residual only; no independent coverage netting in the reader |
| Customer delivery reduces Buy twice | Reader consumes current unplaced Buy directly, not delivered-order arithmetic |
| Hot dealer stock is silently reserved | Existing ABC A test, dealer stock excluded, and BRW floor cap |
| Borrow harms another commitment | Donor impact shown and frozen, explicit CS confirmation, required reason |
| Discontinued commitment is blocked or hidden | Buy allowed with visible warning and required frozen reason |
| Channel total changes by heuristic | Persisted demand class stamped by the tested source precedence and shared substring mapper; no AI or location inference |
| Project Buy is netted twice | Project branch of the channel-aware read model passes confirmed unplaced Buy through without stock or incoming subtraction |
| Shared supply is doubled by channel | One location row owns stock, SPO, PO, and reorder; channel is a demand-column breakdown only |
| Product and Location modes disagree silently | Both grains read the same frozen product-location facts and channel columns |
| Both plan grains create purchases | One locked actionable decision grain per run; PO worklists ignore the comparison grain |
| Product grain accidentally applies MOQ per location or channel | One Product row aggregates all actionable need and rounds once |
| Product choice cannot be replayed by location | Existing allocator reruns with chosen quantity; narrow child persists an exactly balanced split |
| Fractional count units or lost measure quantities | UOM master data owns `decimal_places`; input validation and minor-unit allocation keep children equal to chosen quantity |
| Legacy decisions become actionable twice | Legacy runs remain unchanged and read-only; only new versioned runs accept decisions |
| Same-day incoming is attributed inconsistently | Section 3.5 owns supply-first event order, stable line keys, and stock-before-SPO attribution |
| Product level overrides location ownership | Deterministic sum only; individual rows remain authoritative in Location grain |
| Amendment creates duplicate Buy | Revision supersession plus idempotent active inquiry row and placed-supply exception ledger |
| Cross-company facts leak | Company-scoped reads, writes, uniqueness, permissions, and isolation tests |

## 10. Explicit non-goals

- No feature code, migration, or UI is part of this PR.
- No LLM classifies demand or proposes quantities.
- No new optimization service, rules engine, second approval workflow, or policy knob is added.
- No automatic supplier ordering or AutoCount write-back is introduced.
- No per-line Project SO confirmation or partial committed state is supported.
- No retirement of Location grain or renaming of Auto / Manual planning mode is permitted.
- No consolidation of per-location reorder-level rows is planned.

## 11. Decisions log

All decisions below were made by the captain on **2026-08-16** and override earlier scout-report
or plan language where different.

| Decision | Captain answer |
|---|---|
| Q1 | Order Inquiry carries only the confirmed Buy residual. |
| Q2 | Incoming SPO to the line location is dated location supply. Availability by date is stock plus SPO arriving by that date minus outstanding SO at that location. Same-day SPO counts, and line attribution follows the stable ordering in section 3.5. There is no allocated-incoming concept; later SPO is advisory and contributes no coverage at the required date. |
| Q3 | Borrow needs explicit CS confirmation with donor impact shown and a required reason. There is no second approver. |
| Q4 | Buying a discontinued product for committed customer demand is allowed, with a warning and required reason. |
| Q5 | Dealer hot-selling is determined by an existing ABC A row at an active, available warehouse with `segment = dealer`. Reserve cannot consume dealer-facing free stock for such a product and may use the `pool_warehouse_id` BRW pool only above BRW's per-location reorder level. For other products, own fulfilment free stock and shared BRW are Reserve; outside or already committed stock is Borrow. |
| Q6 | Confirmation is one atomic Project SO-level transaction covering all lines. Before it, the whole SO is Needs CS review and outside purchasing. Every line must satisfy the balance invariant at the same commit. |
| Q7 | Product reorder level is the sum of per-location reorder levels. NULL or absent contributes 0. There is no inferred winner, worklist, or Needs level state; Location grain keeps reading each location level. |
| Q8 | Product and Location remain selectable and actionable Plan grain modes over the same frozen product-location facts. Product has one row per product with Project, Retail, and unclassified demand as stacked analysis; Location shows the same breakdown by location. MOQ and rounding apply once to the Product total. One decision grain is locked per new run, separately from Planning mode: Auto / Manual; legacy runs are read-only. |
| Q9 | Persisted `sales_orders.demand_class` is the semantic owner. Import and publish evaluate stored `order_type`, stated `order_type`, customer market segment, then sales-agent demand class. The unchanged mapper treats a textual value containing `project`, `projects`, or `contract` as Project and every other stated textual value as Retail. A missing persisted class is an exception. Warehouse and AI never classify demand. |

## 12. Supersession notes

Where an older plan conflicts with this finalized contract, this UAC and plan win for SCM front
planning:

- per-line confirmation language is replaced by atomic Project SO confirmation;
- inquiry-at-publish and inquiry-side coverage netting are replaced by confirmed Buy-only handoff;
- requested/accepted donor approval is replaced by explicit confirming-CS Borrow with evidence
  and reason;
- inferred channel classification is replaced by the existing import and publish precedence plus
  persisted SO demand class;
- retirement of the per-location plan is rejected; both plan grains remain;
- exact-line incoming allocation is replaced by dated product-location availability;
- same-day demand-before-supply timeline ordering is replaced by the section 3.5 supply-first
  order for every timeline consumer;
- Product-versus-Location reconciliation is replaced by one Product row that aggregates the same
  channel-aware location facts;
- location-set channel classification is replaced by persisted SO demand class across all
  locations;
- product-level reorder level is a sum, not a selected or migrated winner.
