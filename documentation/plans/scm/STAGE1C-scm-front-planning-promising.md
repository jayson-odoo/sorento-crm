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
- `confirmed_by` FK users SET NULL, `confirmed_at` DateTime nullable (as shipped; the
  service always stamps it at confirmation)
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

Measured on 18 August 2026 at the branch head (`814f71113`). Backend: Postgres via
`tests/_pg_fixture.py` (`blank_session`, every test seeds its own chain, marker-prefixed).
Frontend: Vitest + jsdom. Browser: headless `agent-browser` 0.27.0, private session
`stage1c-ev`, short-lived stack (backend `uvicorn` on 8127, frontend `npm run dev` on 3031),
login with the `E2E_EMAIL` / `E2E_PASSWORD` pair, sidebar clicks from `/`, `get url` before
every read. Groups E and F are out of scope for this slice (Product/Location grain, channel
breakdown - Stage 2/3 per section 0's "Not in this slice") and are not in the table below.

Backend counts at head, each file run alone:

| File | Result |
|---|---|
| `tests/scm/test_front_planning_golden.py` | 9 passed |
| `tests/scm/test_front_planning_engine.py` | 7 passed |
| `tests/scm/test_coverage_timeline.py` | 28 passed |
| `tests/test_so_supply_confirmation.py` | 17 passed |
| `tests/test_supply_inquiry_handoff.py` | 9 passed |

All five together: 70 passed, 0 failed (22.15s). Frontend: `npx vitest run "app/(protected)/project-sales"`
- 92 test files, 1049 tests, all passed. The Stage 1C-specific slice of that
(`fulfilment-planning/**`, `_shared/hooks/useFulfilmentPlanning`, `_shared/lib/supplyComposition`,
`_shared/services/fulfilmentPlanningService`, `order-inquiries/OrderInquiryClient`) is 10 files /
181 tests, all passed; the three retired-surface component suites
(`AllocationPanel.test.tsx`, `AllocationSourceDialog.test.tsx`, `StockClaimsClient.test.tsx`) are
3 files / 40 tests, all passed. `tsc --noEmit` not re-run this session (no source edited).

| AC | Result | Evidence |
|---|---|---|
| AC-B01 line balance uses current open qty | PASS (pytest + browser) | `project_supply_service._facts_for` reads `qty_ordered - qty_delivered` live; adversarial browser step bumped the core line's `qty_ordered` +10 out of band and the next `GET .../supply` returned `open_qty: "80"` (was 70) with no restart, confirmed by curl and by the Compose section's Buy field recalculating to 40. |
| AC-B02 only timely location SPO covers demand | PASS (pytest) | `tests/scm/test_coverage_timeline.py::test_ac_b02_two_line_worked_case_orders_opening_stock_before_the_same_day_spo` and `::test_ac_b02_worked_case_is_identical_when_event_input_order_is_reversed`; `tests/scm/test_front_planning_golden.py::test_opening_stock_goes_to_the_first_line_and_the_same_day_spo_to_the_second` and `::test_reversing_the_database_row_order_changes_nothing`. |
| AC-B03 late incoming is advisory | PASS (browser + pytest) | `tests/scm/test_front_planning_engine.py::test_an_spo_arriving_the_day_after_the_required_date_contributes_zero_coverage`; browser: seeded line 30's `advisory_spo` (`STAGE1CEV-SPO-2`, day after required date) rendered "Advisory: it arrives after the required date and covers nothing." both pre- and post-confirm frozen view. |
| AC-B04 suggestions are deterministic | PASS (pytest) | `tests/scm/test_front_planning_golden.py::test_reversing_the_database_row_order_changes_nothing`, `::test_attribute_sources_gives_the_same_answer_with_three_lines_reversed`; `tests/scm/test_front_planning_engine.py::test_attribute_sources_gives_the_same_answer_with_three_lines_reversed`. |
| AC-B05 hot-selling uses existing ABC facts | PASS (pytest + browser) | `tests/scm/test_front_planning_golden.py::test_a_hot_selling_product_reserves_no_dealer_facing_stock`; browser: seeded line 10 (classification row `abc_class='A'` at dealer-segment MWH) rendered pill "Hot selling"; line 20/30 (no classification row anywhere) rendered pill "Unavailable" (`classification_unavailable: true` in the GET body). |
| AC-B06 hot-selling Reserve protects dealer/BRW stock | PASS (pytest + browser) | `tests/scm/test_front_planning_engine.py::test_hot_selling_reserve_never_draws_dealer_stock_even_when_the_pool_falls_short`, `::test_the_brw_cap_floors_at_zero_when_pool_free_stock_is_below_its_reorder_level`; browser: line 10 dealer-facing free stock 50 at MWH-S/L contributed 0 to Reserve, capped at `max(120-80,0)=40` from the BRW pool - exact AC-B08 numbers, see below. |
| AC-B07 non-hot-selling Reserve stays inside its boundary | PASS (pytest, browser caveat) | `tests/scm/test_front_planning_engine.py::test_reserve_draws_from_the_own_location_before_the_pool_and_states_both_wordings` (own-then-pool, no floor). See Finding 1 below: the LIVE service's cross-product `pool_left` bookkeeping let a second and third product on the same SO draw against the FIRST product's already-computed pool headroom, which this pure-engine test does not exercise (both its lines are the same product). |
| AC-B08 the hot-selling worked case is fixed | PASS (pytest + browser) | `tests/scm/test_front_planning_golden.py::test_the_hot_selling_worked_case_reserves_only_above_the_brw_floor`; browser reproduced the identical numbers live: open 70, dealer-facing free 50, BRW free 120, BRW reorder level 80 -> Reserve 40 from the pool, dealer-facing Reserve 0, Buy 30 (screenshot `s9_line10.png`). |
| AC-B09 Borrow evidence and reason are mandatory | PASS (browser + Vitest) | Browser: "Add a borrow" on line 10 opened a dialog naming the donor (MWH-S/L), "50 free, 0 committed. Borrowing all of it leaves 0 free.", quantity input, and a required Reason; "Add the borrow" was `disabled` until a reason was typed, then enabled (screenshot `s10_borrow.png`/`s11_borrow_ready.png`). `BorrowAddDialog.test.tsx` (part of the 181-test Stage 1C Vitest slice). |
| AC-B10 Borrow has no second approver | PASS (pytest) | `tests/test_so_supply_confirmation.py::test_cross_project_borrow_writes_an_accepted_claim_directly_with_no_requested_state` - claim written `accepted` in the same transaction, no `CLAIM_REQUESTED` state anywhere on the path. |
| AC-B11 discontinued Buy is allowed with control | PASS (browser + pytest) | `tests/test_so_supply_confirmation.py::test_a_discontinued_buy_without_a_reason_is_refused` and `::test_a_discontinued_buy_with_a_reason_confirms`; browser: seeded discontinued product B's line 20 rendered "This product is discontinued. Buying it takes a reason." with a required Reason box shown even at Buy=0 (screenshot `s7_line20.png`/`s8_line20b.png`). |
| AC-B12 every proposal balances | PASS (pytest + browser) | `tests/scm/test_front_planning_golden.py::test_a_proposed_line_balances`, `::test_every_golden_case_is_internally_consistent`; browser: every line card showed the `open = incoming + reserve + borrow + buy` equation live, and manually adding a 10-unit Borrow without reducing Buy produced the red blocker "Line 10, STAGE1CEV-A: the components are over the open quantity by 10." with Confirm disabled (screenshot `s14_imbalance2.png`), which cleared and re-enabled Confirm once rebalanced (`s15_rebalanced.png`). |
| AC-B13 confirmed cover is unavailable to later demand | PASS (pytest + browser) | `tests/scm/test_front_planning_golden.py::test_cover_promised_to_a_confirmed_line_is_not_offered_to_the_next_one` (project open 10 / SPO 10 / retail outstanding 10 / stock 0 -> retail need 10, not 0); service-level hold filtering in `project_supply_service._free_stock`/`_hold_rows`; browser corroborated the same machinery is live (the adversarial re-read recomputed free/held quantities against the confirmed decision). |
| AC-B14 every proposed component states its reason | PASS (pytest + browser) | `tests/scm/test_front_planning_golden.py::test_every_proposed_component_states_its_reason_beside_its_quantity`; browser: every Reserve/Buy/Borrow shown carried its reason sentence inline (e.g. "free stock in the shared MWH pool above its reorder level of 80 covers the need by the required date", "remaining uncovered need"), frozen into the confirmed view unchanged. |
| AC-C01 one action confirms all lines | PASS (browser) | Single "Confirm Project SO" -> AlertDialog -> "Confirm the sales order" -> one `POST .../confirm` 200 flipped all 3 lines to Confirmed in the same response; no per-line action anywhere in the sheet (screenshots `s17`-`s22`). |
| AC-C02 one invalid line rolls back the SO | PASS (pytest) | `tests/test_so_supply_confirmation.py::test_one_unbalanced_line_rolls_back_the_whole_confirmation` - asserts zero decisions/allocations/claims/inquiry rows after a refused attempt, failing line named by line_no + item_code. |
| AC-C03 confirmation rechecks authoritative facts | PASS (pytest + browser) | `tests/test_so_supply_confirmation.py::test_confirmation_rechecks_stock_and_rejects_a_line_whose_free_stock_changed_after_the_sheet_was_read`; browser adversarial step (DB-level qty bump) reproduced the same re-read live end to end through the UI. |
| AC-C04 one active revision represents the SO | PASS (pytest + browser) | `tests/test_so_supply_confirmation.py::test_confirming_a_balanced_multi_line_so_writes_one_active_decision_with_grouped_allocations`; browser: frozen view read "All 3 lines are held by revision 1." then, after the adversarial re-confirm, "All 3 lines are held by revision 2." (screenshots `s21_confirmed.png`, `s40_revision2.png`). |
| AC-C05 concurrent confirmations cannot double-claim | PASS (pytest) | `tests/test_so_supply_confirmation.py::test_a_second_confirmation_racing_an_already_active_decision_gets_a_conflict_with_no_partial_writes`, `::test_the_database_refuses_a_second_active_revision_for_one_sales_order` (partial unique index). |
| AC-C06 material change reopens the whole SO | PASS (pytest + browser), see Finding 2 | `tests/test_so_supply_confirmation.py::test_publishing_an_amendment_supersedes_the_active_decision`, `::test_a_reconciliation_link_change_supersedes_the_active_decision`, `::test_a_fact_drift_challenges_the_active_decision_on_read`. Browser adversarial run: bumping the core line's `qty_ordered` +10 out of band, the next `GET .../supply` correctly returned `review_state: "needs_cs_review"` and `decision.state: "challenged"` with reason "Line 10 is now open for 80, and the confirmed revision was balanced against 70." confirmed by curl. **On a fresh full-page load** the sheet rendered this correctly (pill "Needs CS review", banner "Revision 1 no longer matches this sales order" with the same reason text, screenshots `s36`-`s38`). **Within the same SPA session** (reopening the sheet immediately after the DB bump, without a full navigation) the pill and the mini reconciliation "Lines" table kept showing the pre-challenge "Confirmed" state and qty 70 even though the Compose section's own Buy field DID pick up the new number (30 -> 40) - see Finding 2. |
| AC-C07 existing execution is preserved on reconfirmation | PASS (pytest + browser) | `tests/test_supply_inquiry_handoff.py::test_reconfirming_with_a_lower_need_cancels_unplaced_rows_and_flags_placed_ones_with_a_cancel_balance_exception`; browser: the reconfirm (revision 1 -> 2) left the revision-1 Order Inquiry row (qty 30) in place with status text "Superseded by revision 2" rather than deleting it, and raised a fresh revision-2 row (qty 40) alongside it (screenshot `s41_oi_refresh.png`). |
| AC-C08 authorization and company isolation apply | PASS (pytest) | `tests/test_so_supply_confirmation.py::test_confirmation_is_denied_without_the_edit_permission`, `::test_a_cross_company_project_so_is_denied_without_a_leak`. |
| AC-D01 inquiry created only at successful confirmation | PASS (pytest) | `tests/test_supply_inquiry_handoff.py::test_inquiry_rows_appear_only_at_successful_confirmation_not_at_publish_or_reconcile`. |
| AC-D02 inquiry quantity equals confirmed Buy | PASS (pytest + browser) | `tests/test_supply_inquiry_handoff.py::test_inquiry_row_quantity_equals_the_confirmed_buy_residual_exactly_and_zero_buy_creates_no_row`; browser: only line 10 (Buy 30 at confirmation) produced an inquiry row; lines 20/30 (Buy 0) produced none (screenshot `s25_order_inquiry.png`, 1 row of 3 lines). |
| AC-D03 coverage never enters purchasing demand | PASS (pytest + browser) | `tests/test_supply_inquiry_handoff.py::test_reserve_borrow_timely_and_late_incoming_never_inflate_the_inquiry_row_quantity`; browser corroborates (Reserve/Borrow/timely/advisory never appeared as inquiry rows, see AC-D02 evidence). |
| AC-D04 inquiry does not net supply again | PASS (pytest) | `tests/test_supply_inquiry_handoff.py::test_confirmed_unplaced_buy_rows_reader_counts_raised_order_rows_directly`. |
| AC-D05 handoff is idempotent across retries/revisions | PASS (pytest + browser) | `tests/test_supply_inquiry_handoff.py::test_retrying_the_same_confirmation_does_not_duplicate_the_inquiry_row`, `::test_reconfirming_with_a_lower_need_cancels_unplaced_rows_and_flags_placed_ones_with_a_cancel_balance_exception`; browser reconfirm produced exactly one new `raised` row for revision 2 and left the revision-1 row `Superseded by revision 2` (not duplicated, not deleted) - see AC-C07. |
| AC-D06 purchasing can trace Buy to its decision | PASS (browser + pytest) | `tests/test_supply_inquiry_handoff.py::test_serialized_inquiry_rows_carry_human_identifiers_and_no_uuid`; browser: Order Inquiry grid showed `S/O line no` 10, `Project SO` STAGE1CEV-PSO-1, `Revision` 1 (then 2), `Item code` STAGE1CEV-A, delivery date - no UUID anywhere in the row (screenshots `s25`, `s41`). |
| AC-G01 decision evidence is immutable and attributable | PASS (pytest) | `line_snapshots` JSONB freezes components/reasons/evidence at confirmation (`SOSupplyDecision`); `confirmed_by`/`confirmed_at`/`supersedes_id`/`superseded_reason` chain exercised by `test_confirming_a_balanced_multi_line_so_writes_one_active_decision_with_grouped_allocations` and `test_reconfirming_supersedes_the_active_decision_and_increments_the_revision`; browser frozen view showed `confirmed_by_name` ("Jayson Personal" via curl) on the challenged decision payload. |
| AC-G02 empty and unavailable evidence is explicit | PASS (browser) | Every line card rendered explicit empty states rather than hiding sections: "Nothing is borrowed on this line. No other location or project holds free stock of this item.", "No incoming arrives by the required date.", "No later incoming for this item at this location.", "Retail classification" pill "Unavailable" for lines 20/30 (screenshots `s6`-`s9`). |
| AC-G03 destructive/superseding action is confirmed | PASS (browser) | Shared `AlertDialog` "Confirm STAGE1CEV-PSO-1?" / "All 3 lines are confirmed together." / "The composition is frozen and the Buy residual goes to purchasing. This action cannot be undone." with Cancel + "Confirm the sales order" - never a native `confirm()` (screenshots `s16_confirm_dialog.png`, `s20_alertdialog.png`, `s39_reconfirm_dialog.png`). `ConfirmProjectSoDialog.test.tsx` in the Vitest slice. |
| AC-G04 human-readable navigation and error handling | PASS (browser) | All navigation was by sidebar/breadcrumb click, never a deep URL, for first-visit discovery of every screen in this run; `console`/`errors` were empty at every checkpoint across the whole session (list, sheet, borrow dialog, confirm, SO detail, view-sources dialog, Stock Claims, Order Inquiry, mobile); every `/api/v1/project-sales/*` call returned 200 except the deliberately-unbalanced Confirm attempt, which never fired (client-side disabled, per AC-B12). Identifiers throughout were human-readable (SO ref, item code, project code, warehouse code) with a UUID only ever behind an id-suffixed field never rendered. |
| AC-G06 read and write paths remain company-scoped | PASS (pytest) | `tests/test_so_supply_confirmation.py::test_a_cross_company_project_so_is_denied_without_a_leak`; every seeded row carried `company_id` via `CompanyScopedMixin`'s `before_insert` stamp. |
| AC-H01 baseline differences have regression tests | PASS (review) | Stage 0's failing-first contract tests for the retired per-line allocation/claim behaviour were replaced in the same commits as the behaviour change per section 5.5/8; confirmed no live `PUT/DELETE .../allocation` or `POST /allocation-claims` route remains reachable from the FE (browser network check below) and the retired routes are gone from `fulfilment_planning.py`/`sales_orders.py`. |
| AC-H02 stage order is enforced | PASS (review) | Phase 1 mock commit precedes Phase 2 backend commits on this branch (`git log`: mock/Vitest commits `6d39620c0`/`1b1e7f68e` before/alongside the backend TDD commits; branch stacked on the already-landed Stage 1B PR #209 which itself followed the same order). |
| AC-H04 scope stays direct | PASS (review) | No LLM quantity generation, no new optimizer/rules engine, no second Borrow approval (AC-B10), no automatic supplier ordering, no reorder-level convergence worklist, no new configuration knob introduced by this slice; reason strings are deterministic string templates, not model output. |

Retired-surface confirmation (plan 5.5), all via browser:

- SO detail Allocation panel: header reads "Supply is composed in Fulfilment Planning." with a link
  "Open Fulfilment Planning"; the toolbar carries only Search/Filters/Columns/Refresh, no
  Choose source / Change / Clear. Per-row action is "View sources" only.
- "View sources" dialog (`AllocationSourceDialog`) is read-only evidence: a ranked list
  (MWH "Available stock" 70 free to take, MWH-S/L "Available stock" 50 free to take, "No
  location" "Order it") with a Close button and the same "Open Fulfilment Planning" link - no
  selection control, no Choose/Save action (screenshot `s30_sources_dialog.png`).
- Stock Claims (`/project-sales/stock-claims`) reads "Stock one project took from another. Supply
  is composed in Fulfilment Planning."; empty state "No stock has been borrowed either way / A row
  appears here when a Borrow is confirmed in Fulfilment Planning, on either side of it." with only
  a link back to Fulfilment Planning - no Release/Refuse action anywhere on the page (screenshot
  `s31_stock_claims.png`). This run never confirmed a Borrow (the draft Borrow added in step 3 was
  discarded when the sheet was reopened before the actual Confirm), so a populated row with a
  "Decided by" column was not directly observed; the empty-state absence of any write action is
  still conclusive for the retirement claim.
- `network requests` across the whole session: zero `PUT`/`DELETE` to `.../allocation`, zero `POST`
  to `/allocation-claims`. The only non-GET calls anywhere in the run were the two `confirm` POSTs
  and `list-query/column-config` PUTs (listing personalization, unrelated).

### Findings (BOTH FIXED on this branch after the run; original reports kept below)

Finding 1 was fixed in `75333fdc1`: the pool ledger is keyed per product per pool warehouse
(`_LineFacts.pool_key`), on the proposal path and the confirm-time recheck alike, pinned by
`tests/test_so_supply_confirmation.py::test_two_products_sharing_one_pool_warehouse_never_share_a_reserve_bucket`
(proven red against the old keying). Finding 2 was fixed in `1cc8ac5c5`: when the supply
response's `review_state` disagrees with the cached reconciliation, `useSupply` invalidates the
reconciliation and worklist queries, pinned in `useFulfilmentPlanning.test.tsx`. With those two
commits the test counts above move to: `test_so_supply_confirmation.py` 20,
`test_supply_inquiry_handoff.py` 9 (one extended), all five backend files together 73. The
original reports as written by the evidence run:

**Finding 1 - live service cross-product pool-stock leak (`project_supply_service.py`,
`proposal_for` / `_recheck_line`).** `pool_left` (and its confirm-time twin passed to `_free_for`)
is keyed only by pool warehouse id, not by `(product_id, warehouse_id)`. When a Project SO has
several lines for DIFFERENT products sharing the same pool warehouse, the first line's computed
`fact.pool_free` seeds `pool_left[pool_id]`, and every later line for a DIFFERENT product then
reads and depletes that SAME bucket instead of its own product's free stock. Reproduced live: the
seed gave product B (line 20, discontinued, zero stock anywhere) and product C (line 30, zero
stock, SPO-covered) no stock rows at the MWH pool at all, yet the GET `/supply` response proposed
Reserve 15 (line 20) and Reserve 10 (line 30) from MWH - stock that does not exist for either
product - simply because product A's line 10 had already computed `pool_free=120` for that
warehouse and the shared dict handed the (undepleted, product-A-shaped) remainder to the next
different-product line. The CONFIRM-time recheck (`_recheck_line` -> `_free_for`) uses the exact
same shared dict, so a payload asking to Reserve non-existent stock for product B/C from this
pool would incorrectly PASS the recheck and commit, rather than failing per AC-B07/AC-B12. No
existing pytest exercises two DIFFERENT products sharing one pool warehouse on the same SO
(`test_reserve_draws_from_the_own_location_before_the_pool_and_states_both_wordings` and siblings
in `tests/scm/test_front_planning_engine.py` use one product per case). This did not block any AC
above from reaching PASS - AC-B06/B07/B08 are proven correct for the single-product case they
test, and the browser evidence for lines 20/30 is still valid evidence of the OTHER things those
lines demonstrate (discontinued warning, advisory SPO, empty states) - but it means a multi-product
Project SO sharing a pool warehouse can silently over-Reserve today. Logged for the coder;
suggest keying `pool_left` by `(product_id, pool_id)` and re-running the golden set.

**Finding 2 - same-SPA-session staleness on challenge (frontend).** Reopening the Fulfilment
Planning sheet for an SO whose active decision was just challenged by an out-of-band fact change
(same session, no full page navigation) rendered the header pill ("Confirmed") and the
Reconciliation "Lines" mini-table (old qty) from stale cached data, even though the SAME
`GET .../supply` call had already returned the fresh challenged payload (`review_state:
"needs_cs_review"`, `decision.state: "challenged"`) - confirmed by curl against the exact same
endpoint at the exact same moment, and by the Compose section on the SAME rendered sheet correctly
showing the recalculated Buy quantity (30 -> 40) from that same response. A full page reload (`open`
navigation) immediately showed the correct pill, banner and reason text. This reads as a
react-query cache/invalidation gap between whatever powers the header pill and whatever powers the
Compose section - both should be reading the same `/supply` response. Not app-breaking (a reload
fixes it, and the list-level `review_state` was also observed to lag until a full reload once), but
worth a follow-up: a CS user who reopens a row they just re-triggered a challenge on, without
refreshing the browser, would see "Confirmed" when the SO actually needs review again. Logged for
the coder.

### Browser evidence run (18 August 2026)

Stack: backend `uvicorn` on 8127 (`DATABASE_URL` unchanged, shared local Postgres), frontend
`npm run dev` on 3031 with `NEXT_PUBLIC_API_URL`/`NEXTAUTH_URL`/`PORT` exported for that process
only (not written to `.env.local`); ports chosen free and not in the "belongs to another lane"
list. Seed: a one-off script (`documentation/plans/scm/../scratchpad`, not committed) created a
marker-prefixed (`STAGE1CEV`) chain via `SessionLocal` and committed it so the running API saw it:
project `STAGE1CEV Evidence Residences` (owned by the E2E login user so `assert_can_edit_project`
passes), core SO `STAGE1CEV-CORE-SO` with 3 lines, Project SO `STAGE1CEV-PSO-1` (published, all 3
lines pre-linked to their core lines), reusing existing active warehouses MWH-S/L (own,
project-segment) and its pool MWH (dealer-segment, `pool_warehouse_id` already set) - no warehouse
created or modified. Three new products: A (hot-selling worked case, AC-B08 numbers), B
(discontinued, zero stock), C (SPO timely+advisory split); stock rows only for the new products;
one `scm.item_classification` row for product A at MWH (dealer) to trigger the hot-selling path;
two SPO/inbound-shipment rows for product C (one arriving on the required date, one the day after).

Login via `E2E_EMAIL`/`E2E_PASSWORD` from `.env.local` (values never printed); sidebar clicks from
`/` for every first visit to a screen. Walked: Project Sales -> Fulfilment Planning (list, seeded
row "Needs CS review", `GET .../fulfilment-planning` 200; Confirmed filter -> explicit empty state
"No sales order has been confirmed yet" + "Open the pipeline" CTA, `review_state=confirmed` 200) ->
row -> side sheet (Stage 1B reconciliation card + Supply composition section, `GET .../supply` 200)
-> per-line evidence for all three lines (hot-selling BRW cap, discontinued warning + required
reason, timely/advisory SPO split, every empty state explicit) -> Borrow flow on line 10 ("Add a
borrow" dialog, donor MWH-S/L 50 free/0 committed, "Add the borrow" disabled until a reason typed,
enabled after) -> manual imbalance (added Borrow 10 without reducing Buy -> red blocker "the
components are over the open quantity by 10", Confirm disabled) -> rebalance (Buy 30 -> 20, blocker
cleared, Confirm re-enabled) -> Confirm Project SO -> AlertDialog naming the SO ref and "All 3
lines are confirmed together" -> `POST .../confirm` 200 -> pill "Confirmed" in sheet AND list ->
frozen view ("All 3 lines are held by revision 1.") -> Project Sales -> Pipeline -> seeded project
-> Sales orders tab -> Order inquiry -> exactly one Buy row (line 10, qty 30, S/O line 10, Project
SO STAGE1CEV-PSO-1, Revision 1, item STAGE1CEV-A, no UUID) -> back to the SO detail -> retired
Allocation panel (read-only, link to Fulfilment Planning) -> "View sources" dialog (read-only
ranked evidence, no selection control) -> Project Sales -> Stock Claims (empty state, no
Release/Refuse anywhere) -> adversarial DB-level bump of the core line's `qty_ordered` (+10,
70 -> 80) -> reopened list (stale "Confirmed" pill until a full page reload, then correctly
"Needs CS review" - Finding 2) -> reopened sheet in the same SPA session (pill/mini-table stale,
Compose section correctly recalculated - Finding 2) -> full reload -> sheet correctly showed
"Needs CS review" pill and "Revision 1 no longer matches this sales order" banner with the exact
reason text -> re-confirmed -> AlertDialog again -> `POST .../confirm` 200 -> "All 3 lines are held
by revision 2." -> Order Inquiry now showed 2 rows (revision 2 qty 40 "Raised", revision 1 qty 30
"Superseded by revision 2") with the summary strip correctly counting only 1 as "still to buy".
Repeated the golden-path list + sheet at 375x812 (mobile hamburger menu -> Project Sales ->
Fulfilment Planning -> row -> sheet), rendered correctly with no overlap.

`errors` was empty at every checkpoint across the whole session, at both viewports. `console`
carried only `[debug] JWT token extracted successfully` and Fast Refresh lines. `network requests
--filter allocation` across the whole session showed GETs only (`.../allocations`,
`.../allocation-candidates`, `.../allocation-claims?direction=all`) plus two unrelated
`list-query/column-config` PUTs (column personalization) - zero writes to any retired endpoint.
Session closed with `close` (not `close --all`); backend and frontend PIDs killed individually at
the end. Seed data deleted in FK-safe order in a `finally` block; verified zero rows remain across
every table touched (`projects.sales_orders`, `projects.sales_order_lines`,
`projects.so_supply_decisions`, `projects.order_inquiries`, `projects.order_inquiry_rows`,
`projects.so_line_allocations`, `projects.projects`, core `sales_orders`/`sales_order_lines`,
`products`, `product_categories`, `units_of_measure`, `stock`, `scm.item_classification`,
`scm.reorder_level`, `spo_allocations`, `inbound_shipments`) by id and by the `STAGE1CEV` marker.

## 10. Independent review pass (Opus, 18 August 2026)

Codex is out of quota until Aug 20; the captain approved substituting an Opus reviewer for
the independent pass. Verdict on the pre-fix head: needs work, two blockers. All blockers
and the small should-fixes were addressed on this branch before the PR opened:

- Blocker: per-ITEM negative quantities in the confirm payload were only checked as
  per-kind totals, so `reserve [-50, +100]` passed and inflated the capacity ledger.
  Fixed (item-level scan) with a red-proven regression test.
- Blocker: a `project_line_id` repeated in the payload was processed twice, doubling the
  promise. Fixed (explicit refusal naming the line) with a regression test.
- CANCEL_BALANCE exception rows stacked one copy per reconfirm at the same lower need.
  Fixed: a still-raised exception row is superseded like a raised ORDER row.
- `_hand_to_purchasing`'s best-effort catch now runs inside the confirmation transaction;
  its writes sit in a SAVEPOINT so a swallowed DB error cannot abort the outer commit.
- A background refetch (window focus / unrelated invalidation) reseeded the composition
  drafts mid-typing. The reseed is now keyed on order + decision revision + review state,
  and the supply query no longer refetches on focus.
- Migration 374's downgrade dropped shared objects regardless of who created them. Upgrade
  now stamps an authorship COMMENT when it creates the shared table/column; downgrade
  drops only what carries the stamp (proven both directions on a scratch database).
- `_lock_stock` resolves products the way `_facts_for` does (core line first), and a
  pure-Buy line's inquiry row falls back to the fulfilment location instead of a blank.

Accepted follow-ups (nits, logged here rather than fixed): `attribute_sources` keying on
`(so_number, line_no)` could collide for non-project core lines with no line number if a
future consumer feeds them (key on caller line_id then); `ConfirmResult.review_state` is
hardcoded `confirmed` while a surplus core line can leave the pill at awaiting
reconciliation (cosmetic, toast-only consumer); `_donor_impact` freezes pre-transaction
figures when two lines borrow one donor; an identical retried confirmation churns the
inquiry row id instead of leaving the row alone.
