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
- SPO quantities allocated to a particular core SO line and their expected arrival dates;
- existing per-location reorder levels, classifications, supplier constraints, and the frozen
  SCM planning inputs;
- the SO market segment and its deterministic demand class.

### 1.2 Happy path

1. The accepted Project PO and schedule produce a release proposal grouped into the intended
   AutoCount SO worksheet.
2. CS reviews the proposed release and creates the Project SO draft.
3. The AutoCount worksheet is exported, uploaded after AutoCount creation, and reconciled to
   the Project SO, including a stable link for every Project SO line to its core SO line.
4. The whole Project SO enters **Needs CS review**. It is not yet committed purchasing demand.
5. CS opens one side sheet. Each line shows open quantity, timely allocated incoming, proposed
   Reserve, proposed Borrow, proposed Buy, the required date, and evidence for every source.
6. CS adjusts components line by line. Borrow shows donor impact and requires a reason.
   Discontinued Buy shows a warning and requires a reason.
7. CS presses **Confirm Project SO** once. The server rechecks every line and commits all line
   decisions atomically. If any line is stale or unbalanced, no line is confirmed.
8. Only the confirmed Buy residual for each line is handed to Order Inquiry. Reserve, Borrow,
   covered incoming, and unallocated incoming are not purchasing demand.
9. The next SCM run reads the confirmed unplaced Buy once. The buyer can select **Plan grain:
   Product** or **Plan grain: Location**, separately from **Planning mode: Auto / Manual**.
10. Product grain shows one product row with stacked Project and Retail readings. Supplier MOQ
    and order multiple are applied once to the product requirement. Location grain retains the
    existing per-location Buy decisions. The selected decision grain is the only actionable
    grain for that run, so the two modes cannot create overlapping purchase decisions.
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
  = timely_allocated_incoming(l)
  + reserve_qty(l)
  + borrow_qty(l)
  + buy_qty(l)
```

All terms are non-negative and expressed in the SO line UOM. `open_so_qty` is the current core
SO-line quantity still requiring fulfilment at confirmation time. Timely allocated incoming is
an SPO allocation already linked to that core SO line with an expected arrival on or before its
required date.

The confirmation transaction must:

1. lock or otherwise concurrency-protect the Project SO revision and all affected stock and
   incoming allocation facts;
2. verify that every Project line has a unique reconciled core SO line;
3. recompute open quantity and timely allocated incoming from authoritative records;
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
2. Subtract only timely allocated incoming. The SPO must be allocated to this exact core SO line
   and arrive by the required date. An unallocated or late SPO is advisory only.
3. Propose Reserve from eligible free unclaimed stock under section 3.3.
4. Propose Borrow only from stock outside Reserve eligibility or stock committed to another SO.
5. Set Buy to the remaining positive residual.

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
Project line needs 70 units after timely allocated incoming. Dealer-facing free stock is 50,
BRW free unclaimed stock is 120, and BRW's reorder level is 80. The cap is `120 - 80 = 40`.
The proposal is Reserve 40 from BRW and a residual 30 for Borrow or Buy. The 50 dealer-facing
units and BRW's protected 80 are not consumed by Reserve. If CS selects 10 dealer units as
Borrow with a reason, Buy becomes 20 and the line balances at confirmation.

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

Incoming SPO is not a CS decision:

- timely quantity already allocated to the exact SO line is coverage and is part of the balance;
- allocated quantity arriving after the required date is advisory and does not cover the line;
- unallocated incoming is advisory only, even if product, location, and date appear suitable;
- CS cannot convert advisory incoming into coverage in this sheet. That belongs to the existing
  allocation process and must be completed before confirmation.

## 4. Order Inquiry handoff

Order Inquiry is a purchase-requirement handoff, not an independent netting engine.

- A confirmed decision creates one active inquiry row per SO line with `buy_qty > 0`.
- The row quantity is exactly that confirmed Buy residual.
- Lines with Buy 0 create no active purchase row.
- Reserve, Borrow, timely allocated incoming, and unallocated incoming never appear as Order
  Inquiry demand.
- Reconfirmation supersedes prior unplaced rows idempotently. Placed or received quantities stay
  in the purchase ledger and produce an exception if the new need is lower.
- The SCM reader counts current confirmed, unplaced Buy directly. It does not subtract customer
  delivery again and does not repeat the pre-order or inbound netting already decided by CS.

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

Project versus Retail comes from the SO's market segment through the existing
`market_segments` vocabulary and canonical `sales_orders.demand_class` mapping. There is no AI
classification and no salesperson, warehouse, or free-text inference.

The deterministic mapping is:

- a market segment whose existing `demand_nature` is `spike`, or whose canonical segment code is
  `project`, maps to `demand_class = project`;
- existing dealer, retail, and end-user market segments map to `demand_class = retail`;
- an absent or unmapped market segment remains `unclassified`, is excluded from Project and
  Retail labeled totals, and appears as a blocking data-quality exception for Project SO
  confirmation or an explicit exception in the buyer plan for other SOs.

The mapping must be centralized and tested against the existing market-segment rows. It is not a
new configurable rules engine.

### 5.3 Product grain

Product grain shows one row per product for the company and frozen run. Each row has stacked,
expandable readings:

- **Project:** current confirmed unplaced Buy, count of contributing SO lines, earliest required
  date, and drill-down to SO line, decision revision, and inquiry row;
- **Retail:** replenishment requirement after Project claims and other committed demand, with
  velocity, stock, incoming, and reorder evidence;
- **Unclassified:** exception quantity, never silently assigned to either channel;
- **Total:** raw requirement, supplier rounding, suggested quantity, chosen quantity, supplier,
  cash impact, and lifecycle state.

Project Buy is firm committed demand. A reorder threshold cannot suppress it.

```text
raw_product_requirement
  = confirmed_unplaced_project_buy
  + retail_replenishment_after_project_claims

product_suggested_qty
  = apply_supplier_MOQ_and_multiple_once(raw_product_requirement)
```

Applying supplier constraints once at product grain avoids buying one MOQ for every location.
No AI-generated quantity, optimizer, or extra policy knob is introduced.

### 5.4 Location grain and reconciliation

Location grain remains a permanent selectable and actionable Buy mode. It reads the existing
location-level net positions and each location's own reorder level, shows suggested Buy by
product and location, and retains the existing recommendation decision and override workflow.

Both grains are frozen from the same run, as-of time, stock, demand, incoming, policy, and
supplier facts. For a product, define:

```text
product_reorder_level = SUM(COALESCE(location_reorder_level, 0))
product_raw_need = network calculation after shared supply is allocated once
location_raw_need_sum = SUM(each location's non-negative raw need)
product_suggested_qty = supplier_round(product_raw_need)
location_suggested_qty_sum = SUM(supplier_round(each location raw need))
reconciliation_delta = location_suggested_qty_sum - product_suggested_qty
```

The bridge must display:

1. summed location reorder level, which must equal the product reorder level;
2. cross-location netting delta between location raw need sum and product raw need;
3. rounding delta between round-each and round-once;
4. Product suggested quantity and the sum of Location suggestions; and
5. the allocation of the chosen product quantity back to locations.

The two suggested totals need not be numerically equal. They are reconciled when the displayed
deltas reproduce the difference from frozen inputs. A non-zero unexplained difference is a
blocking calculation defect.

Each run has exactly one actionable `decision_grain`:

- `product`: `scm.order_summary_row` owns the chosen product quantity and the location allocation
  must sum to it. Location recommendations are a read-only reconciliation projection.
- `location`: existing `scm.reorder_recommendation` decisions and
  `scm.recommendation_override` rows remain actionable. The Product row is a read-only aggregate
  of their chosen quantities.

The buyer may inspect both views at any time. The first saved decision locks `decision_grain`
permanently for that frozen run. If the buyer needs the other grain to become actionable after a
decision, a new current run must be created from a new frozen input snapshot; the old run and all
of its decisions remain immutable and auditable. PO worklists read only the run's selected grain.
This preserves two real Buy planning modes without allowing both to order the same requirement.

### 5.5 Reorder-level rule

Product-level reorder level is always the deterministic sum of per-location levels for that
product:

```text
product_reorder_level = SUM(COALESCE(scm.reorder_level.level, 0))
                        for rows with a concrete warehouse_id
```

An absent location row and a NULL location value both contribute 0. Product-wide
`warehouse_id = NULL` rows are not used as a competing level for this view. There is no inferred
winner, buyer worklist, migration to one product row, or **Needs level** state in Product grain.
Location grain continues to read the individual per-location values and applies the same NULL as
0 rule for this feature.

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
core line identifiers, product, required date, open quantity, timely allocated incoming and its
allocation references, Reserve, Borrow, Buy, suggestion basis, lifecycle warning, and required
reason. The existing normalized `so_line_allocations` rows remain the confirmed components and
are grouped atomically by `decision_id`. This is the report's narrow decision header corrected
from line grain to SO grain for Q6, not a new generic workflow or a second allocation model.
Authoritative stock and SPO allocation records remain in their existing tables; identifiers in
the snapshot provide the audit path.

### 6.3 Order Inquiry reuse

Reuse `projects.order_inquiries` and `projects.order_inquiry_rows`. Add `supply_decision_id` to
each standard Buy row and enforce one active unplaced row per active decision and SO line.
Existing fields such as `so_line_id`, item code, quantity, delivery date, location, state, and
actor remain useful. The standard new-demand verb is Buy/Order only; legacy coverage verbs are
not produced for a confirmed decision.

### 6.4 SCM reuse and deltas

- Add `decision_grain` (`product` or `location`) to `scm.reorder_run`. It is NULL until the first
  decision and immutable after that decision.
- `scm.reorder_recommendation` continues to hold location-grain rows. Its existing
  decisions, overrides, `allocation`, and frozen `inputs` remain the actionable Location mode and
  carry the bridge evidence.
- `scm.order_summary_row` remains one row per `(run, product)` and owns the single chosen product
  quantity when `decision_grain = product`; under Location it is the read-only aggregate. Add
  `project_buy_qty`, `retail_replenishment_qty`, `unclassified_demand_qty`,
  `earliest_project_need_date`, and `channel_calculation_basis` to freeze the stacked reading.
- `scm.reorder_level` remains per location. No consolidation migration or product-level winner
  is added. The product value is calculated as the sum in section 5.5.
- `scm.item_classification` supplies the existing ABC hot-selling fact.
- `scm.demand_stat.channel_split` and canonical core SO `demand_class` supply channel evidence.

All new durable rows are company-scoped, follow existing audit conventions, and use service-layer
transactions. No new service boundary, rules engine, optimizer, or LLM quantity path is needed.

## 7. Rollout plan

Each stage follows `PRINCIPLES.md`: approved UAC and plan, Phase 1 frontend mock, Phase 2 backend
TDD and implementation, Phase 3 code review and Definition of Done. This document is the
pre-code contract only.

### Stage 0: Contract and data readiness

- Confirm the core SO-line link, market-segment mapping, BRW identity, dealer-facing locations,
  ABC availability and evidence behavior, and SPO allocation/date source against
  production-shaped fixtures.
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
- Replace early publish derivation, per-line partial confirmation, independent inquiry netting,
  and second-approver Borrow on the named implementation branch.

### Stage 2: Product and channel plan view

- Add the independent Plan grain selector and retain Planning mode.
- Add stacked Project, Retail, and Unclassified readings, one-round supplier quantity, evidence
  drills, and the Product-to-Location reconciliation bridge.
- Keep both grains actionable, lock one decision grain per run, and make PO worklists consume only
  that grain.

### Stage 3: Reorder-level rollup and hardening

- Calculate Product reorder level as the sum of per-location levels with NULL or absent as 0.
- Keep Location grain reading its per-location levels.
- Add reconciliation, concurrency, amendment, cancellation, missing-classification,
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
| Same incoming or stock covers two lines | Authoritative allocation links, concurrency protection, unique active claims, and recheck at commit |
| Confirmed cover remains free in a later proposal | The same confirmed claim read reduces CS free stock and Retail planning supply before either calculation |
| Order Inquiry buys coverage again | Buy residual only; no independent coverage netting in the reader |
| Customer delivery reduces Buy twice | Reader consumes current unplaced Buy directly, not delivered-order arithmetic |
| Hot dealer stock is silently reserved | Existing ABC A test, dealer stock excluded, and BRW floor cap |
| Borrow harms another commitment | Donor impact shown and frozen, explicit CS confirmation, required reason |
| Discontinued commitment is blocked or hidden | Buy allowed with visible warning and required frozen reason |
| Channel total changes by heuristic | Central market-segment mapping; no AI or salesperson inference |
| Product and Location modes disagree silently | Same frozen run plus visible netting and rounding bridge; unexplained delta blocks action |
| Both plan grains create purchases | One locked actionable decision grain per run; PO worklists ignore the comparison grain |
| Product grain accidentally applies MOQ once per location | Product grain aggregates raw requirement and rounds once |
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
| Q2 | Incoming SPO is not a CS decision. Timely incoming already allocated to the exact SO line counts as coverage; unallocated incoming is advisory only. |
| Q3 | Borrow needs explicit CS confirmation with donor impact shown and a required reason. There is no second approver. |
| Q4 | Buying a discontinued product for committed customer demand is allowed, with a warning and required reason. |
| Q5 | Dealer hot-selling is determined by an existing ABC A row at an active, available warehouse with `segment = dealer`. Reserve cannot consume dealer-facing free stock for such a product and may use the `pool_warehouse_id` BRW pool only above BRW's per-location reorder level. For other products, own fulfilment free stock and shared BRW are Reserve; outside or already committed stock is Borrow. |
| Q6 | Confirmation is one atomic Project SO-level transaction covering all lines. Before it, the whole SO is Needs CS review and outside purchasing. Every line must satisfy the balance invariant at the same commit. |
| Q7 | Product reorder level is the sum of per-location reorder levels. NULL or absent contributes 0. There is no inferred winner, worklist, or Needs level state; Location grain keeps reading each location level. |
| Q8 | Product and Location remain selectable and actionable Plan grain modes. One decision grain is locked per frozen run, the comparison view remains readable, and suggestions reconcile through visible cross-location netting and rounding deltas. Plan grain is separate from Planning mode: Auto / Manual. |
| Q9 | Project versus Retail derives deterministically from the SO market segment and canonical demand class. No AI classification is used. |

## 12. Supersession notes

Where an older plan conflicts with this finalized contract, this UAC and plan win for SCM front
planning:

- per-line confirmation language is replaced by atomic Project SO confirmation;
- inquiry-at-publish and inquiry-side coverage netting are replaced by confirmed Buy-only handoff;
- requested/accepted donor approval is replaced by explicit confirming-CS Borrow with evidence
  and reason;
- inferred channel classification is replaced by the SO market-segment mapping;
- retirement of the per-location plan is rejected; both plan grains remain;
- product-level reorder level is a sum, not a selected or migrated winner.
