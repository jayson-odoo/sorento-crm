# Stage 1C slice note: order promising, atomic confirmation, Buy-only handoff

**Status:** IN PROGRESS, 18 August 2026. Branch `fm/scm-stage1c-promising`, stacked on
`fm/scm-stage1b-reconciliation` (PR #209). Phase 1 (mock) and Phase 2 backend are in;
the frontend is off the mock and onto the real routes, the retired write surfaces are
gone from the screen, and the frontend Vitest is in. The evidence run and the AC-H03
report are what is left.

**Contract:** `PLAN-scm-front-planning.md` sections 3.1-3.5, 4, and the Stage 1C bullet in
section 7; `UAC-scm-front-planning.md` Groups B, C, D plus the AC-G / AC-H criteria those
groups reference. This note is the slice detail the coder and tester work from; where it and
the plan disagree, the plan wins.

**Not in this slice:** channel breakdown, Product grain, plan-grain policy, UOM
`decimal_places`, `scm.committed_v` channel columns, allocator generalisation (Stage 2);
reorder-level rollup (Stage 3).

## 0. Coordination with the Stage 2 lane (read before the migration)

Stage 2 is being built in parallel off the same base and its migration 376 ALSO creates
`projects.so_supply_decisions` and adds `order_inquiry_rows.supply_decision_id` (it reads the
table; this slice owns the atomic confirmation that writes it). Neither lane's migration is on
the other's branch, and merge order into `main` is the captain's choice. Therefore this
slice's migration `374_so_supply_decisions` must be **guarded per object**: create the table
only if absent, add each column only if absent, create each index only if absent (use
`sqlalchemy.inspect` on the bind). Whichever migration lands second becomes a no-op for the
shared objects. The `so_line_allocations` additions (`decision_id`, `reason`,
`donor_impact_snapshot`) belong to this lane alone but are guarded the same way for symmetry.
DDL follows plan 6.2/6.3 verbatim so both lanes produce the same shape. Downgrade drops only
what upgrade created (record what was created in the migration via the same inspector checks
re-run, or make downgrade a documented no-op; prefer conditional drops).

## 1. Journey (J04-J06, this slice)

Actor: Customer Service, in **Project Sales -> Fulfilment Planning**, on an SO whose pill
reads **Needs CS review** (Stage 1B end state).

1. CS opens the row's side sheet. Below the Stage 1B reconciliation card, a **Supply
   composition** section shows one card per line: open quantity (core SO line's current open
   fulfilment qty), required date, fulfilment location, then the proposed components, each
   with its reason beside its quantity ("Reserve 10: free stock at BRW covers the need by the
   required date", "Buy 60: remaining uncovered need"). Timely SPO coverage names the SPO and
   arrival date. A later-arriving SPO shows as **advisory** with zero coverage. A dealer
   hot-selling product shows the BRW cap evidence; a product with no classification row at any
   qualifying dealer warehouse shows **Retail classification unavailable**. A discontinued
   product's Buy shows a warning and demands a reason. Every empty state is explicit (AC-G02).
2. CS adjusts components per line: change Reserve/Buy quantities, add Borrow from a listed
   candidate (other location free stock, or stock held by another project) - Borrow shows the
   donor and its impact and requires a reason before Confirm enables (AC-B09). A line whose
   components do not balance to its open quantity shows the imbalance and blocks Confirm.
3. CS presses **Confirm Project SO** once. Shared AlertDialog states the SO reference and line
   count (AC-G03). The server rechecks every line against authoritative facts and commits all
   lines atomically; any stale or unbalanced line fails the whole confirmation, and the error
   names each failing line by line number and item code (AC-C02). On success the pill flips to
   **Confirmed** everywhere (list row, sheet, project SO list, SO detail).
4. Purchasing opens Order Inquiry and sees one Buy row per confirmed line with `buy_qty > 0`,
   quantity exactly the confirmed residual, traceable to the Project SO, line number, item
   code, required date and decision revision (AC-D06). Reserve, Borrow, timely SPO cover and
   late incoming never appear as purchasing demand.
5. A material change (amendment publish, line remap, quantity/date change) supersedes or
   challenges the active revision and the whole SO returns to **Needs CS review** (AC-C06).
   Placed or received Buy stays in the ledger; if the new need is lower an exception row is
   raised, never a silent delete (AC-C07).

## 2. Data model (migration `374_so_supply_decisions`, down_revision `373_merge_scm_stage0_1a`)

Revision id 23 chars (< 32). All new rows company-scoped (`CompanyScopedMixin`).

### New table `projects.so_supply_decisions` (guarded create; plan 6.2)

- `id` UUID PK (str uuid4, like siblings), `company_id`
- `project_sales_order_id` UUID NOT NULL FK `projects.sales_orders.id` CASCADE
- `revision_no` Integer NOT NULL
- `state` String(16) NOT NULL, values `active` / `superseded` / `challenged`
- `source_revision` String(120) nullable - order status + `updated_at` ISO at confirmation,
  display evidence only
- `line_snapshots` JSONB NOT NULL - list, one object per line; freezes: `line_no`,
  `project_line_id`, `core_line_id`, `product_id`, `item_code`, `location` (warehouse code),
  `required_date`, `open_qty`, `timely_spo_qty` + `timely_spo_refs`
  (list of `{spo_number, arrival_date, qty}`), `reserve_qty`, `borrow_qty`, `buy_qty`,
  component reason strings (section 3.2 of the plan), `suggestion_basis`
  (hot_selling flag, pool code, pool cap, classification_unavailable), `lifecycle_warning`
  (discontinued) and the CS `reason` texts entered (borrow reason, discontinued-buy reason)
- `confirmed_by` FK users SET NULL, `confirmed_at` DateTime NOT NULL
- `supersedes_id` UUID nullable self-FK SET NULL, `superseded_at` DateTime nullable,
  `superseded_reason` Text nullable
- `created_at`
- Partial unique index `uq_so_supply_decisions_active` on `(project_sales_order_id)` WHERE
  `state = 'active'` - the DB-level singleton that makes concurrent confirmation lose cleanly
- Unique `uq_so_supply_decisions_revision` `(project_sales_order_id, revision_no)`

### Column adds (guarded)

- `projects.so_line_allocations`: `decision_id` UUID nullable FK
  `projects.so_supply_decisions.id` SET NULL + index; `reason` Text nullable;
  `donor_impact_snapshot` JSONB nullable. New source constant `ALLOC_SOURCE_OTHER_LOCATION =
  "other_location"` (String(16) column, no DB enum - model constant only).
- `projects.order_inquiry_rows`: `supply_decision_id` UUID nullable FK
  `projects.so_supply_decisions.id` SET NULL + index.

No other schema. `allocation_claims` already supports direct-accepted writes.

## 3. Engine (pure): `app/services/scm/front_planning_engine.py`

New module, no DB, no LLM, no optimizer, no config knob. Must satisfy
`tests/scm/test_front_planning_golden.py` exactly (remove the strict-xfail markers in the
same change; the adapters there define the component surface: `kind`, `qty`,
`source_location`, `reason`, `.stated`).

- `propose_line(*, open_qty, line_no, required_date, fulfilment_location,
  is_dealer_hot_selling, free_stock, pool_location, reorder_levels, timely_spo_qty,
  is_discontinued, ...)` -> ordered components. Order per plan 3.2: Reserve from eligible
  free stock (3.3 eligibility: hot-selling -> pool only, capped at
  `max(pool free - coalesce(pool reorder level, 0), 0)`; otherwise own fulfilment location
  first then pool, no floor), then timely SPO coverage, then Buy as the positive residual.
  Borrow is never auto-proposed (quantities come from CS); the engine only computes the
  residual Buy after CS-chosen Borrow when rechecking. Reason strings exactly as the golden
  fixtures pin them (pool-with-level wording vs plain-location wording).
- `attribute_sources(*, product_code, warehouse_code, opening_stock, supply_events,
  demand_lines)` -> mapping keyed `(so_number, line_no)`. Lines ordered by required date, SO
  number, line number (missing last), internal line id; sources consumed opening stock first,
  then SPO arriving on or before the line's required date, SPO sources sorted by arrival
  date, SPO number, SPO line number (missing last), allocation id. Reversed input order
  yields identical results. Same-day SPO counts (supply before demand).
- All quantities `Decimal`. Deterministic for the same inputs.

## 4. Shared timeline ordering flip (plan 3.5)

`app/services/scm/coverage_timeline.py::_sort_key` becomes: date, then kind with
**supply before demand** (opening 0, supply 1, demand 2), then SO number (`ref`), then
`line_no` (new optional `TimelineEvent` field, missing last), then `line_id` (new optional
field, final stable key, never displayed). `CoverageService._demand_events_many` populates
`line_no` / `line_id` from `SalesOrderLine`. Update
`tests/scm/test_coverage_timeline.py::test_same_day_demand_is_ordered_before_supply` in the
same change: same-day supply now covers same-day demand (no shortfall, closing 0 after both),
rewrite the docstring to the plan 3.5 rationale, and pin the two-line worked case
(AC-B02 golden numbers) including identical results with input order reversed. Sweep the
other `tests/scm/test_coverage_*.py` files for same-day-tie assertions that legitimately flip;
update only those, and say which in the commit message. Every consumer (coverage routes,
summary_order_service, plan exceptions) inherits the one ordering - no per-consumer fork.

## 5. Backend services

### 5.1 Proposal read: `app/services/project_supply_service.py` (new)

`proposal_for(order)` builds the side-sheet payload:

- Guards: order review state must be `needs_cs_review` or `confirmed` (Stage 1B service
  says which); every line needs its unique `core_sales_order_line_id` (else 422 listing
  lines by `line_no` + item code).
- Facts per line, all read live: open qty = core line `qty_ordered - qty_delivered`
  (floor 0, line UOM); fulfilment warehouse = core line warehouse; free unclaimed stock =
  `stock.quantity_on_hand - stock.quantity_reserved -` confirmed holds of ACTIVE decisions
  and legacy confirmed allocations (port `_holds` from `project_allocation_service`,
  filtered to allocations whose `decision_id` is NULL or whose decision is `active`);
  hot-selling = EXISTS `scm.item_classification` row `abc_class = 'A'` at an active,
  available `segment = 'dealer'` warehouse; `classification_unavailable` when no
  classification row exists at any qualifying dealer warehouse; pool = fulfilment
  warehouse's `pool_warehouse_id` (never a code parse); pool reorder level =
  per-location `scm.reorder_level` row (NULL/absent -> 0); timely SPO = `SPOAllocation`
  joined `InboundShipment` at the fulfilment warehouse, undelivered
  (`actual_arrival_date IS NULL`, not received), ETA = `coalesce(eta_delay_date,
  estimated_arrival_date)`; arriving `<= required_date` is coverage input, later is
  advisory evidence; the line's SHARE of timely SPO comes through
  `attribute_sources` across the SO's own sibling lines and other outstanding SO lines at
  that product+location (the section 3.5 projection), so two lines never count one SPO
  twice; `is_discontinued` from `products.is_discontinued`.
- Calls `propose_line` per line; returns proposed components with reasons, Borrow
  candidates (other-location free stock outside the Reserve pool; other-project confirmed
  holds with donor project ref and donor impact: donor free before/after, committed qty),
  timely + advisory SPO evidence, warnings, and the active decision (revision_no, state,
  confirmed_by name, confirmed_at, frozen snapshots) when one exists.

### 5.2 Atomic confirmation: same service, `confirm(order, payload, actor_user_id)`

Payload: per line `{project_line_id, reserve: [{warehouse_id, qty}], borrow: [{source:
'other_location'|'other_project', warehouse_id, donor_project_id?, qty, reason}],
buy_qty, buy_reason?, timely_spo_qty}`.

Transaction (plan 3.1 steps, one commit):

1. `SELECT ... FOR UPDATE` the `projects.sales_orders` row, then the `stock` rows of every
   (product, warehouse) the payload touches (deterministic order to avoid deadlock).
2. Re-verify: order is published/amended, review state clean (header linked, every line
   uniquely linked, no surplus), every payload line exists.
3. Recompute open qty and the line's timely SPO share from authoritative rows; a payload
   `timely_spo_qty` above the recomputed share fails the line.
4. Recheck Reserve eligibility + BRW cap, Borrow donor availability, required reasons
   (borrow reason per Borrow component; buy reason when `is_discontinued` and
   `buy_qty > 0`), non-negativity.
5. Balance per line: `open_qty == timely_spo + reserve + borrow + buy` exactly.
6. Any failure -> 409/422 with `failing_lines: [{line_no, item_code, reason}]`, nothing
   written.
7. Write: supersede the current active decision if any (`state = 'superseded'`,
   `superseded_at`, reason "reconfirmed"); insert the new decision (`revision_no = max + 1`,
   `state = 'active'`, snapshots frozen incl. reason strings); insert `so_line_allocations`
   rows grouped by `decision_id` (`own`/`brw` Reserve with warehouse, `other_location` /
   `other_project` Borrow with warehouse + reason + donor_impact_snapshot, `order` Buy with
   no warehouse), old decision's rows left in place for audit; cross-project Borrow writes
   its `allocation_claims` row directly `accepted` (`requested_by = decided_by = actor`,
   `decided_at = now`, reason required), linked via `claim_id`; restamp
   `line.stock_location` from the new components.
8. Refresh Order Inquiry in the same transaction (section 6 below).
9. Concurrency: the partial unique active index makes the second racer's insert fail ->
   map to 409 `refresh-required` with no partial writes. Authorization: route perm +
   `assert_can_edit_project`; company scope via the mixin (AC-C08).

### 5.3 Supersession and challenge (AC-C06)

- `supersede_for_material_change(order, reason)`: sets the active decision
  `superseded` (no replacement revision). Called from amendment publish
  (`project_so_delta_service.publish_amendment`) and from reconciliation `_persist` when it
  changes any line link of an order holding an active decision.
- Challenge on read: `proposal_for` compares each snapshot's `open_qty`, `core_line_id`,
  `required_date` against live facts for the ACTIVE decision; a mismatch flips the decision
  to `challenged` (flush) and the payload says why. Review state then reads
  needs_cs_review again.
- Review state: reconciliation service returns `confirmed` iff the Stage 1B
  `needs_cs_review` conditions hold AND an active decision exists (batched in
  `review_states_for`; route `Literal` gains `"confirmed"`).

### 5.4 Buy-only Order Inquiry handoff (plan section 4)

- New `ProjectOrderInquiryService.refresh_for_decision(order, decision, buy_lines)` called
  ONLY inside the confirmation transaction. Reuses the one-inquiry-per-SO `_existing`
  guard; creates the `OrderInquiry` if absent. Writes one row per line with `buy_qty > 0`:
  `verb = ORDER`, `qty` = confirmed Buy residual, `so_line_id`, `item_code`,
  `delivery_date = required date`, `stock_location`, `supply_decision_id = decision.id`,
  `covered_by = NULL` (no netting, no coverage verbs). Buy 0 -> no row.
- Idempotency / revisions (AC-D05): prior rows with a `supply_decision_id` of a superseded
  decision that are still `raised` (unplaced) are `cancelled` with note
  "Superseded by revision N"; rows already `actioned` (placed) stay; when the new need for
  a line is lower than its placed quantity, write an exception row `verb = CANCEL_BALANCE`,
  note "Placed X, new need Y", `supply_decision_id` set. At most one active `raised` ORDER
  row per (active decision, line).
- `derive_for_sales_order` and its pool netting die on the SO path: delete the method (no
  production caller) and the SO-path netting tests; `derive_for_amendment` and the
  amendment verbs stay untouched. `net_demand` / `verb_for` remain for amendments.
- Reader precedence (section 4 predicate): `PLAN_DEMAND_ORDER_SQL`,
  `is_plan_demand_order()` and `COMMITTED_V_SQL` change together - the sheet leg
  (`demand_origin = 'scm_order_inquiry'`) counts only when the core SO has NO active
  confirmed decision (`NOT EXISTS` join through `projects.sales_orders.so_id` to an
  `active` `so_supply_decisions` row). View updated by the same migration (CREATE OR
  REPLACE `scm.committed_v` with the constant). A narrow tested reader
  `confirmed_unplaced_buy_rows()` (join `order_inquiry_rows` -> decision active ->
  `projects.sales_order_lines.core_sales_order_line_id`) is the Stage 2 consumption point;
  it counts current `raised` ORDER rows directly, no re-netting (AC-D04).
- Serialization for AC-D06: inquiry row payload gains `line_no`,
  `decision_revision`, `project_so_ref` (provisional ref) - human identifiers, no UUID.

### 5.5 Replaced baseline behaviour

- Per-line partial confirmation: `PUT /sales-order-lines/{line_id}/allocation`,
  `DELETE .../allocation`, claim raise/accept/refuse routes and their service methods are
  removed; `rank` / candidates read stays as the Borrow-candidate source (absorbed or
  re-exported by the supply service). The allocation list read stays (now shows decision
  components). FE surfaces calling the removed routes are removed/redirected to the sheet:
  the sales order's Allocation panel keeps its reads and loses Choose source / Change /
  Clear, the ranked-source dialog becomes read-only evidence, and Stock claims becomes the
  Borrow history (no Release, no Refuse, a `Decided by` column instead). All three carry
  one link to **Project Sales -> Fulfilment Planning**, where the composing now happens.
- Tests pinned in STAGE0 note section 5 ("kept until 1C") are deleted or rewritten to the
  new contract in the same commit as the behaviour change, never before.

## 6. API contract (Phase 1 mock is built against this; Phase 2 must match)

Under `/api/v1/project-sales`, in `fulfilment_planning.py` (mounted before
`sales_orders.router`). Reads `require_permission_with_api_key(VIEW)`, writes
`require_permission(EDIT)` + `assert_can_edit_project`.

```text
GET  /project-sales/sales-orders/{pso_id}/supply -> SupplyProposal

SupplyProposal {
  project_sales_order_id, provisional_ref, autocount_doc_no?, project_code, project_name,
  status, review_state,                       // now incl. 'confirmed'
  decision?: { revision_no, state, confirmed_by_name, confirmed_at, challenged_reason? },
  lines: [{
    project_line_id, line_no, item_code?, description?, uom?,
    open_qty, required_date?, fulfilment_location?,     // warehouse code
    is_dealer_hot_selling, classification_unavailable, is_discontinued,
    pool_location?, pool_cap?, pool_reorder_level?,
    components: [{ kind: 'timely_spo'|'reserve'|'borrow'|'buy', qty, reason,
                   source_location?, source_warehouse_id?, donor_project_ref?,
                   donor_project_id?, cs_reason? }],
    timely_spo: [{ spo_number, arrival_date, qty }],
    advisory_spo: [{ spo_number, arrival_date, qty }],
    borrow_candidates: [{ source: 'other_location'|'other_project', warehouse_code,
                          warehouse_id, donor_project_ref?, donor_project_id?, free_qty,
                          donor_impact: { free_before, free_after_full_borrow,
                          committed_qty } }],
    frozen?: { open_qty, components: [...] }            // when review_state = 'confirmed'
  }],
  failing_lines?: [{ line_no, item_code, reason }]      // 422 body when not confirmable
}

POST /project-sales/sales-orders/{pso_id}/confirm -> ConfirmResult
body: { lines: [{ project_line_id, timely_spo_qty, reserve: [{warehouse_id, qty}],
                  borrow: [{source, warehouse_id, donor_project_id?, qty, reason}],
                  buy_qty, buy_reason? }] }
ConfirmResult { revision_no, confirmed_at, review_state: 'confirmed',
                inquiry_rows_created: n, exceptions: [{line_no, item_code, message}] }
409/422 -> { error, failing_lines: [{ line_no, item_code, reason }] }   // no UUIDs
```

`GET /project-sales/fulfilment-planning` `review_state` Literal gains `confirmed`.
Order-inquiry list rows gain `line_no`, `decision_revision`, `project_so_ref`.

Added during Phase 1, because the confirm payload names warehouses and donor projects by
id while the screen names them by code and reference, and the read had no way to carry the
pair: `source_warehouse_id` / `donor_project_id` on a component, `warehouse_id` /
`donor_project_id` on a borrow candidate, `project_id` on the proposal itself (the link to
the project's Order Inquiry). They are addressing only and are never rendered, exactly like
`ReconciliationLine.id`. Two more, for the same "the screen must show what was frozen"
reason: `cs_reason` on a component (the borrow reason and the discontinued-buy reason CS
typed, which the snapshot already freezes) and `frozen.open_qty` beside `frozen.components`,
so a confirmed line states the quantity the revision was balanced against rather than the
live one.

A refused confirmation is read by the frontend from the response body directly
(`failing_lines`), not through `extractApiError`, which answers with a string: the shared
extractor supplies the message and the list is read from a clone of the same response.

Two corrections made while building Phase 2, both recorded here rather than left as a
difference between this note and the code:

- **The refusal body is the shared envelope plus `failing_lines`**, not a bespoke
  `{error, failing_lines}`: `{message, detail, code, failing_lines}`, which is what the
  global `AppException` handler serialises. The frontend is unchanged - it already reads
  the sentence through `extractApiError` (which reads `message`) and the list off a clone
  of the same response - and a second key holding the same sentence under another name
  would be one more thing to keep in step.
- **A refusal, and a confirmation exception, may carry no line number.** `line_no` and
  `item_code` are both optional on `SupplyFailingLine` and `ConfirmException`
  (`app/schemas/project_supply.py`), because a refusal can be about the sales order
  rather than about one of its lines. The frontend types were tightened to match and the
  sheet names the order itself in that case, the way the reconciliation exception list
  already names a surplus core line by item code alone. `ConfirmResult.confirmed_at` is
  optional for the same "the schema is the authority" reason.
- **Confirmation verifies the LINE links, not the whole Stage 1B review state.** Plan 3.1
  step 2 says "verify that every Project line has a unique reconciled core SO line", and
  that is the check: a line with no `core_sales_order_line_id` refuses the order. The
  header link is not re-checked separately because only reconciliation writes those line
  links and it needs `so_id` to do it, so a line link implies a header link; the review
  state the sheet SHOWS still comes from Stage 1B, unchanged.

## 7. Frontend

Phase 1 (mock first, commit before any backend code, AC-H02): extend
`FulfilmentPlanningSheet` with the Supply composition section, per-line component editor
(quantity inputs, Borrow add-from-candidate with required reason, discontinued warning +
required reason, live balance check), Confirm Project SO with AlertDialog (SO ref + line
count), Confirmed frozen view, challenged/stale banner, advisory SPO display, hot-selling /
classification-unavailable evidence, every empty state. `ReviewStatePill` +
`REVIEW_STATE_LABELS` gain `confirmed`. Order Inquiry grid gains S/O line no + decision
revision columns and PSO ref. Mock fixtures behind `NEXT_PUBLIC_PROJECT_SO_MOCK=1` in the
`_shared/services` module (Stage 1B pattern), covering: proposal reserve+buy, hot-selling
cap, borrow candidate + reason flow, discontinued, advisory SPO, classification unavailable,
unbalanced line, confirm success, confirm failure with failing lines, confirmed view,
challenged view. Deleted when Phase 2 lands.

Phase 2: swap mock for real calls (`fulfilmentPlanningService` gains `getSupply` +
`confirmSupply`; `useReconciliationMutations` gains `confirm`, invalidating fulfilment
planning, reconciliation, sales-order and order-inquiry key families). Vitest for every new
component (loading/empty/error/data, reason gating, balance blocking, dialog copy, no-UUID
guard extended to allow the Confirmed pill), hooks and services.

## 8. Tests (Phase 2, TDD - RED before implementation)

Backend pytest, Postgres via `tests/_pg_fixture.py`, every test seeds its own chain:

- Engine: golden un-xfailed; plus own-then-pool Reserve split, hot-selling zero dealer
  draw, cap floor at 0, timely-vs-late SPO boundary (on-date counts, day-after advisory),
  Decimal exactness, reversed-input determinism.
- Timeline: flipped pinned test + worked two-line case + reversed row order.
- Confirmation: happy path multi-line; one unbalanced/stale/unmapped line rolls back all
  (assert zero decisions/allocations/claims/inquiry rows); recheck catches a stock change
  after sheet open; revision chain (confirm -> reconfirm supersedes, revision_no
  increments, old allocations retained); concurrent double-confirm (two sessions, one 409,
  no partial writes - exercise the partial unique index); amendment publish supersedes;
  reconcile link change supersedes; challenge on fact drift; borrow requires reason;
  cross-project borrow writes accepted claim in-transaction with actor stamps; no
  requested-state claim anywhere on the path; discontinued buy requires reason and
  confirms; 403 without permission; cross-company denied without existence leak.
- Handoff: rows only from confirmation (AC-D01: publish/reconcile still create none); qty
  equals Buy exactly, Buy 0 -> no row (AC-D02); reserve/borrow/timely/late never appear
  (AC-D03); reconfirm cancels unplaced rows + placed rows stay + lower-need exception row
  (AC-C07/D05); retried confirm does not duplicate; `confirmed_unplaced_buy_rows` counts
  directly (AC-D04); sheet-leg predicate excludes a confirmed SO (committed_v + Python twin
  both); serialization carries line_no/revision/ref and no UUID (AC-D06 BE half).
- Routes: supply GET happy/403/404; confirm POST happy/403/404/422-failing-lines/409-race;
  fulfilment list filter `confirmed`.
- Replaced baseline tests deleted/rewritten in the same commits as the behaviour changes.

Frontend Vitest per section 7. Evidence run: headless agent-browser, private session, free
ports, sidebar navigation from `/`, console + network checks, 1280x800 + 375x812; recorded
here; no new Playwright spec (standing order).

## 9. AC-H03 test report

Appended to this file at DoD: every AC in Groups B, C, D plus referenced AC-G/H rows with
PASS / FAIL / DEFERRED evidence. PR body links here.
