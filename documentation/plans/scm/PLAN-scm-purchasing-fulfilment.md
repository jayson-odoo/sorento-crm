# PLAN - SCM Purchasing and Fulfilment

> Status: **IN BUILD 2026-08-05** on `feat/scm-purchasing-base` (worktree `.claude/worktrees/scm-base`,
> unpushed). Done and committed: **S0** shared base, **S2** dated Coverage Timeline plus pooled
> netting wired into the planner, **S1** the outstanding SO/PO upload channel, the warehouse
> screen exposing pool + planning availability, **S3/S3b/S4** the planning UI on `/scm/reorder`,
> **S5** plan exceptions, the two curation feeds (purchase history and the Order Inquiry sheet,
> which now CREATES sales orders), and **S7** the supplier stock list plus the container Loading
> Plan on `/scm/loading-plan` (migration 336). Remaining: **S8** supplier notice, **S9** packing
> list and SPO allocation, and the transfer-proposal accept endpoint that belongs with them.
>
> Verified against a database bootstrapped from EMPTY the way CI builds one, not against the
> prod-copy. Zero new test failures versus `origin/main`; 62 previously-failing tests now pass
> because the module's permissions and seed data could not previously reach a fresh database.
>
> Blocking external dependency unchanged: the real AutoCount extract described in
> `scm-autocount-extract-spec.md` does not exist yet. S1 is built to that spec and tested against
> fixtures derived from it using the real Tuju Residence figures.
>
> Grilled with the user, then the plan itself grilled, then revised across four rounds of visual
> review. **Schedule decided: four worktrees, ten days, every migration in S0.**
> UAC: `scm-purchasing-fulfilment-acceptance-criteria.md`. Extract spec to hand to the
> client: `scm-autocount-extract-spec.md`. Decisions: ADR-0011, ADR-0012.
> Target: both spines complete in 10 working days. The user was shown the dependency risk on
> the planning spine and chose full scope; this plan controls that risk rather than reduces it.
>
> **Delivery model.** Parallel worktrees driven by agent teams, with a single architect and
> gatekeeper who owns the shared contract and reviews every merge. Four worktrees at peak after the
> review round grew the scope (see "Scope growth"). The 10-day schedule depends entirely on that
> parallelism, which is why S0 is not optional and why **no migration may be authored outside it**:
> the shared surface must exist, and be merged, before anything forks.

## What is shipping

Two lanes of the source flow, end to end:

- **Planning** (Project CS, Josephine, Mr Loo, Joey): demand and supply feed from AutoCount
  extracts uploaded by CS and by planning under role-bounded scope, one dated planning engine with
  pooled netting, the Coverage Timeline, the Summary Order Report where the order quantity is
  decided, the PO creation worklist Joey executes against, and Plan Exceptions batched on each SO
  re-upload.
- **Fulfilment** (Ms Tee): supplier inventory upload, volume-constrained Loading Plan, the
  Supplier Notice, pre-load and packing-list import, and SPO allocation against Supply PO lines.

Out of scope is listed in UAC Group K and is not repeated here.

## Current state, verified

Checked against `main` and the dev database on 2026-08-03, not assumed.

| Fact | Value | Consequence |
|---|---|---|
| `orders` | 30,939 rows, real | DOs exist. Not demand. |
| `sales_orders` / `_lines` | 15 / 15 rows, demo seed only | `scm.committed_v` is empty in reality. No demand feed exists. |
| `purchase_orders` / `_lines` | 10 / 16 rows, demo seed only | `scm.on_order_v` is empty. "Outstanding PO" has no substrate. |
| `inbound_shipments` | 112 rows, real | Fulfilment lane has live data to demo against. |
| `spo_allocations` | 860 rows, real | Same. No `po_line_id` column. |
| `market_segments` | `project` (spike), `retail` (continuous) | Demand class vocabulary exists. No `dealer`. |
| warehouses | 82, including `BRW`, `BRW-BB`, `BRW-NTC`, `BRW-HOLD` | Borrow and deallocate are just a different `warehouse_id`. |
| `sales_order_lines` | no date column | Blocks netting. Migration required. |
| `respond_channels` | one `whatsapp_business` row | No WeChat. Suppliers are not Respond contacts. |
| SCM M0-M8 | merged to `main` via PR #13, 2026-07-18 | Engine, policies, cash stage, decisions, overrides all present and tested. |
| Import machinery | `validate_*` / `process_*` pairs for stock, product, order tracking, SPO, GRN listing, GRN lines, DO detail | New importers follow an established pattern. |
| project-sales | `order_inquiries`, `so_amendments`, `order_change_notices`, `so_line_allocations` exist on an **unmerged** worktree branch | Do not duplicate. See "Interlock" below. |

## Interlock with project-sales

The project-sales worktree already models the Project CS side of the flow: `order_inquiries`
and `order_inquiry_rows` (with verbs and a `covered_by` field), `so_amendments`,
`order_change_notices`, `so_line_allocations`, `allocation_claims`. It also already declares
`project_sales_orders.so_id -> sales_orders.id`, described in its own source as "the CORE
`sales_orders` row created on publish, which is what SCM reads as committed demand".

That is the same bridge this plan depends on. So:

- This plan **consumes** `sales_orders` and does not care who wrote the row. Upload and
  project-sales publish are two producers of one table.
- The demand delta in ADR-0012 is produced by *either* an upload restatement *or* a
  project-sales amendment. Both funnel through one service so exceptions are identical.
- **Do not** re-model order inquiries, amendments or allocation claims here. If project-sales
  merges during these two weeks, the delta producer gains a second caller and nothing else
  changes.

## Slices

**S0 lands first, on a base branch every worktree forks from.** Two worktrees each inventing the
priority policy and each editing `cash_ranking.py` produces two policies and a guaranteed
conflict, and two worktrees each writing a migration produces the alembic dual-head that has
already cost us a deploy once. One base, one alembic head, gated and merged before any fork. With
four worktrees at peak this stops being hygiene and becomes the thing the schedule rests on.

### S0. Shared base (day 1, gated, then fork)

- Migrations, all on one head: `sales_order_lines.required_date` (date, nullable),
  `sales_orders.demand_class`, `spo_allocations.po_line_id` (nullable FK to
  `purchase_order_lines`), `warehouses.counts_as_available` (boolean, NOT NULL, default true).
- **Two separate warehouse columns, because they answer two different questions.** Collapsing them
  into one flag breaks the pooled-netting case.
  - `warehouses.counts_as_available` (boolean, NOT NULL, **default true**) - does this location's
    stock count as available at all. **Config, not derived: every location starts sellable** and an
    admin turns one off. No suffix-based seeding, so nothing is silently excluded and no naming
    convention is baked into the engine. Risk direction is stated honestly: an over-stated
    availability figure under-buys, which surfaces as a stockout, and the correction is one edit on
    the warehouse screen.
  - `warehouses.pool_warehouse_id` (nullable self-FK) - which shared pool this location may draw
    on. This is the structural half, and it is what makes "use BRW" possible. Seeded from the
    existing naming convention (`BRW-BB` points at `BRW`; a code with no suffix points at itself)
    and admin-editable, so a client whose codes look nothing like Sorento's just repoints the rows
    instead of needing code.
- Both exposed on the warehouse admin screen. The Eling question drops from blocking to advisory:
  the defaults are safe and correctable, so no slice waits on it.
- `import_field_alias` table + seeds (English and Chinese aliases).
- `scm.priority_policy`, weighted, seeded to PO-document-sequence dominant.
- `cash_ranking.allocate_funding` generalised from cash to any scarce capacity, with fractional
  fill beside the existing all-or-nothing mode. Existing M4 goldens must not move.

Everything below forks from S0. Dependencies flow downward.

### Track 1 - Planning

**S1. Demand and supply feed** (UAC A, D2) - migrations and the alias table moved into S0
- `sales_orders.demand_class` resolved from the customer's `market_segment_code` at import, failing
  the row loudly when it cannot resolve rather than defaulting to retail.
- **Two uploaders, one mechanism, role-bounded scope**: Project CS is forced to projects they own,
  only planning may declare whole-book scope. Enforced server-side and asserted as an RBAC test.
- Alias admin CRUD screen (UAC I2) reading the S0-seeded table.
- `validate_outstanding_so_import` / `process_outstanding_so_import`, and the PO pair, in
  `app/tasks/import_tasks.py` following the existing shape.
- **Scope derived from the file, never asked for** (UAC A2): read which projects, customers and date
  span the file covers, state it in words on the preview, then bound it by the uploader's authority.
  Persisted on the import job so a re-run is reproducible. An override exists for a genuinely partial
  single-project export and is not the normal path.
- Uses the **shared `FileUploadZone`** component that resource attachments use. No new hand-rolled drop
  surface; the codebase already has several.
- Tests: the Tuju file at scope "one project" must not touch out-of-scope rows (AC-A5); same
  file twice is a no-op (AC-A8).

**S2. Engine unification** (UAC B, C; ADR-0011 including its same-day amendment)
- **Pooled netting, not per warehouse.** A location code is `SITE` or `SITE-SUFFIX`; the bare site
  is a shared pool available to every bin under that site, never across sites. Each demand line
  resolves by source preference (`own`, `brw`, `other_project`, `order`) reusing the existing
  `so_line_allocations.source_type` vocabulary rather than a new one. Regression case: `SRTWT7408`,
  demand 67 against bins with 4,397 in the pool, must return "use the pool" and never a buy of 67.
  This is in S2 and not a later slice, because buy-or-use-pool is the most common decision on the
  report and the day-one output is wrong without it.
- Cross-site cover is a transfer **proposal** carrying cost and lead time, never silent netting.
  That keeps genuine inter-warehouse transfer (the old M9) out of the critical path.
- `reorder_engine`: add the date axis. Bucket count from resolved policy; 1 means today's path
  untouched.
- Date-ordered running balance over demand events and supply events. Shortfall returns
  quantity **and** need-by date. Place-by derived from lead time.
- `scm.net_position_v` gains a dated sibling read model; the existing view stays for the
  1-bucket path.
- **Golden parity guard first, before the feature.** Extend `fixtures/golden_m3.json`; assert
  every existing case is byte-identical through the dated engine at one bucket. Test-first per
  the TDD rule: this assertion is written and seen to pass on unchanged code, then the date
  axis goes in and it must still pass.

**S3. Coverage Timeline** (UAC B) - **extends the existing page, does not add one**
- `/scm/reorder` already has `ReorderPlanningView` + `ReorderStatTiles` as a clickable view switcher
  (Buy, Stock allocation, Cash impact), a results grid per view, and `ReorderExplanationDialog` for a
  single row. **Everything here lands as views and dialogs on that page.** Shipping a second planning
  UI beside the first is the defect this avoids.
- Timeline extends `ReorderExplanationDialog`, opened from a row, with **previous and next** so a
  planner walks the shortfall list without closing it. Decision-making starts from the list.
- Plan exceptions and the PO worklist arrive as **new tiles** beside the existing three, so counts are
  visible without navigating.
- **`product_codes[]` multi-select added to `RunPlanningModal`** beside the existing warehouse picker, so a
  run can plan a single product. Empty means all products; the daily scheduled run is unchanged. Same
  `SearchableMultiSelect` component, one more field, no new pattern. Not a reinstatement of the removed
  `buy_scope` category filter.
- Fulfilment keeps its own pages: different job, different data.
- DataGrid rules apply: fixed layout, resizable, explicit sizes, truncate plus title.

**S3b. Summary Order Report and the order-quantity decision** (UAC C2, C3) - added after the
printed sheet was produced during review
- Item-level roll-up above the Coverage Timeline: on hand, project demand, dealer outstanding,
  **on order and in transit as separate columns**, shortfall, suggested, chosen quantity, supplier.
- Drill-downs: project demand to project and SO and date; dealer outstanding to dealer, SO and
  **days outstanding**, worst-first.
- Supplier as a choice, each candidate carrying last PO cost, **last PO date**, last incoming cost
  and the ordered-to-incoming variance, beside on-time and lead time.
- Chosen quantity may exceed the shortfall without being a warning; the consequence panel states
  cover, spare, cash and container volume. The engine figure stays visible and the delta is
  recorded with actor and time.
- Cost capture: stamp incoming cost and a **new currency column** on `inbound_shipment_lines` when
  an allocation is approved. The column exists and is populated in 0 of 1,015 rows today.

**S4. PO creation worklist** (UAC C, E2) - Joey executes, she does not decide
- Mr Loo has already chosen quantity and supplier, so this is a worklist, not a second decision point.
  Reuse the existing decision and override overlay; add need-by, place-by, late flag, last purchase
  cost, and who decided with a timestamp.
- **Manual keyed-into-AutoCount status per row** (not keyed / keying / keyed), because no integration
  exists and nothing can detect it. Uses the **shared status-pill component**, and the column is
  **visible in the list and filterable** - filtering to not-keyed is the primary use of the screen.
- A use-pool decision appears saying no PO is needed rather than being absent, so the worklist
  reconciles one-for-one against the decisions.
- Approved buys group by supplier into draft POs via the existing `decision_service` path.

**S5. Plan Exceptions** (UAC D, D2; ADR-0012 including its amendment)
- One `demand_delta` service, two callers (upload restatement, project-sales amendment). **The trigger
  that exists today is the SO re-upload**, so exceptions are produced as a batch on confirmation, not as
  ad-hoc individual signals. The upload preview's delta counts and the resulting exception count are the
  same facts at two stages and must reconcile; a delta becomes an exception only when it disagrees with
  supply already placed.
- **Item reading attached to every exception, and proposed actions ordered by it**: lifecycle
  (`products.is_discontinued`), velocity (`scm.item_classification`, 13,555 rows already populated),
  business (`market_segments`), last PO date. Wiring existing classification, not new maths. The
  inversion is the test: a discontinued C/Z retail surplus proposes keep-the-PO-and-pool FIRST,
  because that stock is the last obtainable and deferring risks the line closing.
- The reading is displayed with each signal's source field, so a reviewer can disagree with the
  reasoning rather than only the outcome.
- **Upload authority is role-bounded** (UAC D2): Project CS scope is forced to projects they own,
  only planning may declare whole-book scope, asserted as an RBAC test rather than left to the UI.
- Recompute affected product and location, diff against placed supply, emit typed exceptions to
  `scm.plan_exception`.
- Before-and-after timeline in the exception payload. Propose actions. Approve writes; reject
  closes with a reason.
- Test table over the eight source change cases (AC-D8), asserting exception type per case with
  no verb branch in the engine.

#### S5 as built (5 Aug 2026)

The classifier is a PURE module (`plan_exception_engine`) that never sees a verb. AC-D8 asks
for the eight source changes to produce the right type "with no branch keyed on the verb",
and the way to guarantee that is to keep the verb out of scope rather than to promise not to
look at it: a line added and a quantity increased arrive as the same input. The eight cases
are a parametrised table over positions alone.

Two precedence rules were decided while building and are worth naming:

- **A shortfall outranks a surplus** when a restatement produces both. Only one of the two
  can miss a customer date.
- **A gap the placed order still covers is not an exception.** The value of the screen is the
  reduction from deltas to exceptions, and a row somebody opens to find nothing to decide
  spends attention for nothing. Confirmed on real data: three PO lines landing 4-11 Aug
  against a shortfall on the 15th correctly produced NO exception.

Before and after come from the SAME engine, either side of the write - `snapshot` is called
once before `apply` writes and once after. The alternative was to reconstruct the old
position by inverting the diff's deltas, which is a second implementation of netting whose
only job is to agree with the first.

The batch is stamped with the run it contradicts. It is produced by an UPLOAD, so `run_id` is
nullable in the schema; but the exception screen is a view OF a run, and without the stamp it
filters by a run id no batch carries and shows nothing for ever while the rows sit in the
table.

Both the before-snapshot and the generation are best-effort around the write. The upload is
the operation the user asked for, and a defect in the exception path must cost them the
batch (which the next upload produces again), never the upload.

### Track 2 - Fulfilment

> **Track 2 is not free of the AutoCount dependency.** An earlier draft of this plan implied it
> was, on the grounds that `inbound_shipments` and `spo_allocations` hold real data. That is only
> half true: the Loading Plan **ranks outstanding PO lines** (AC-E4) and S9 allocates **to** PO
> lines, and `purchase_order_lines` is 16 demo rows. So the outstanding-PO extract gates both
> tracks; only the outstanding-SO extract is Track-1-only. What Track 2 can do with no extract at
> all is packing-list import plus warehouse-only allocation, since `po_line_id` is nullable by
> design.

**S6. Fulfilment Priority policy** (UAC H) - the policy table and the allocator moved into **S0**
because both tracks read them. What remains here is the weight-change preview showing rank deltas
before commit.

**S7. Supplier inventory and Loading Plan** (UAC E)
- Importer for the supplier inventory workbook: packed versus unfinished, per-unit volume.
- `scm.loading_plan` + lines. Capacity as container count times configurable container volume.
- Rank via S6, fill to capacity, partial fill allowed, deferral reasons recorded, factor
  contributions exposed per line.

**S8. Supplier Notice** (UAC F)
- `supplier_notices` (core). Channel-abstract sender: email live, chat declared and dark until a
  WeChat channel exists.
- Bilingual document generator in the supplier's own layout, plus download.
- Integration log per attempt, success or failure, mirroring `_send_and_log`.

**S9. Packing list and SPO allocation** (UAC G) - the `po_line_id` migration moved into S0
- Multi-block workbook importer: one inbound shipment per container block. Blank container
  number and bill of lading are valid. Duplicate identity must not depend on container number
  (identity rule fixed below under "Holes closed").
- Allocation suggestion per shipment line to (PO line, warehouse) ranked by the S0 policy, with
  alternatives. Approve advances `qty_received`; split across PO lines must sum to shipped
  quantity.

> **S9 under the 6 Aug supply decision.** Supply is the SPO allocation, never the purchase order
> (migration 337). That makes this slice the one that WRITES supply, not merely a bookkeeping
> step after it. Approving an allocation moves quantity from the Ordered tile to the Incoming
> tile in one action: the allocation raises `scm.on_order_v`, and the `qty_received` it advances
> lowers `scm.po_ordered_v`.
>
> Linking `po_line_id` is therefore worth doing even though nothing nets the two views: a LINKED
> allocation stops being counted as ordered the moment it is approved, so the Ordered figure
> sharpens from "everything placed" toward "placed and not yet shipped against". Historical
> unlinked rows keep the old, overstated reading. The progression is monotonic and safe because
> supply never includes ordered - see AC-G6a.

> **Most of S9's plumbing already exists outside SCM. Adopt it; do not re-port.** Surveyed
> 6 Aug 2026:
>
> - `InboundShipmentService.create_shipment` (`procurement_service.py`) already creates or
>   updates a shipment in place, resolving by `shipment_number`, then the container triple
>   (`shipping_container_number` + `estimated_arrival_date` + `shipment_date`, field-wise
>   `IS NOT DISTINCT FROM`), then `attachment_id`. That is **AC-G3** already satisfied, and
>   blank container / bill of lading already work, which is **AC-G2**. See
>   `documentation/plans/PLAN-packing-list-duplicate-detection.md`.
> - `SPOAllocationService` and `/api/v1/procurement/spo-allocations` already do allocation
>   CRUD.
> - `IncomingStockService` already reads shipments, allocations and per-warehouse
>   `unallocated_quantity`.
>
> So S9's genuinely new work is three things, not six:
>
> 1. **The multi-block WORKBOOK reader** (AC-G1). The existing path is n8n PDF extraction
>    posting one shipment at a time; nothing reads an Excel file carrying several container
>    blocks. This is the only new importer.
> 2. **The allocation SUGGESTION** (AC-G4, AC-H5): per shipment line, a ranked (PO line,
>    warehouse) with its reason and alternatives, scored by the SAME S0 Fulfilment Priority
>    policy the Loading Plan uses.
> 3. **Approve** (AC-G6/G6a/G7): write the allocations, advance `qty_received`, enforce that a
>    split sums to the shipped quantity.

## Holes closed during the plan grill

Six weaknesses were found in the first draft of this plan. Each is resolved here so a builder does
not have to rediscover it.

1. **The golden parity guard must not be vacuous.** A `if buckets == 1: return old_path()`
   short-circuit makes the parity assertion pass trivially while the project-SKU maths ships
   untested. The 1-bucket case **runs through the new dated code and the old path is deleted**, so
   parity is a real claim about the new implementation.
2. **Restatement line identity.** The extract has no line-number column and one SO routinely
   carries the same item at several dates, so neither
   `(so_number, item_code, location)` nor `(so_number, item_code, location, required_date)` works:
   the first collides, the second reads every date change as a close plus a new line, which
   contradicts the "date changed" count AC-A3 promises. Rule: group by
   `(so_number, item_code, location)`, then **pair old and new rows within the group by nearest
   date**; unpaired old rows are closed, unpaired new rows are new. That produces the counts a
   human would produce.
3. **Opening balance excludes unavailable locations** via `warehouses.counts_as_available` (S0).
4. **Unresolvable `demand_class` fails the row loudly.** Never defaulted to `retail`: a
   mis-classified project order is silently deprioritised, and a failed row with a reason is a
   five-minute fix to the customer record.
5. **Multi-company.** All 82 warehouses and 113 suppliers are Sorento; Mocha holds none, so the
   partition is inert today. Importers write through the ORM so `CompanyScopedMixin` auto-stamps.
   **No raw INSERT in any importer** - the auto-stamp fires only on ORM flush, and an unstamped row
   is invisible behind the fail-closed filter.
6. **Pre-load duplicate identity** is `(supplier, document date, item code, quantity, carton
   count)` per block, since container number and bill of lading are blank at pre-load stage. Once
   the real packing list arrives carrying a container number, it **supersedes** the pre-load
   shipment rather than creating a second one.

## Scope growth during review, stated before rescheduling

The original ten days were already full. The review round added work, and it came from the client's
own evidence (the printed Summary Order Report and the meaning of "BRW"), not from gilding. The
arithmetic, so the decision is made on numbers:

| Added | Where | Cost |
|---|---|---|
| `pool_warehouse_id` column, seeding, admin field | S0 | +0.5 d |
| Pooled netting + four-source resolution + its goldens | S2 | +1.5 d |
| Summary Order Report screen: roll-up, two drill-downs, supplier choice, consequence panel, four-outcome decision | S3b | +2.0 d |
| On-order vs in-transit split, dealer ageing, last PO date, supplier candidates, report reproducibility | S3b backend | +1.0 d |
| Incoming cost + currency migration + write on approval | S9 | +0.5 d |
| | | **+5.5 d** |

**The growth is not evenly spread.** 4.5 of the 5.5 days land on the planning track (S2 and S3b);
fulfilment absorbs only the +0.5 for cost capture. So the planning track, not the calendar, is the
constraint: its critical path goes from roughly 9 days of work to 13.5.

**Decided 2026-08-03: option 1.** Fan out to four worktrees and hold ten days, with every migration
confined to S0. The options are kept below because the reasoning behind the choice is the thing worth
re-reading if it starts slipping.

Two honest ways to hold ten days, and one to abandon it:

1. **Fan out to four worktrees instead of two** (recommended, and what the schedule below does).
   S2 moves earlier because both planning screens wait on it; once it merges, the timeline screen and
   the Summary Order Report are independent and build in parallel. This holds ten days **only**
   because every migration lives in S0, so no post-fork worktree writes one. That rule was a
   nice-to-have before; it is now load-bearing.
2. **Extend to thirteen working days** with the original two worktrees. Lower coordination risk,
   fewer merges to gate, no chance of an alembic collision.
3. **Cut.** The cut order further down applies, but note that the newly added work is the part the
   client reacted to most strongly, so cutting it is cutting the thing they asked for.

## Schedule

Ten working days, four worktrees at peak. S0 on day 1 is gated and merged before anything forks.

| Day | A - Feed | B - Engine | C - Fulfilment | D - Mr Loo |
|---|---|---|---|---|
| 1 | **S0 shared base, all four migrations on one head, alias table + seeds, priority policy, allocator generalisation, `pool_warehouse_id` seeding. Gate: reviewed and merged before any fork.** | | | |
| 2 | S1 SO importer + scoped restatement | S2 parity guard written and seen to pass on unchanged code | S7 supplier inventory importer | alias admin screen, warehouse admin fields |
| 3 | S1 PO importer, diff preview, confirm | S2 date axis in, old path deleted, parity still green | S7 loading plan engine + capacity | S6 weight-change preview |
| 4 | S1 tests: out-of-scope no-touch, idempotent re-upload | S2 pooled netting + four-source resolution | S7 loading plan screen | S3b contract against mocks |
| 5 | joins D | **S2 merges. Gate.** shortfall, need-by, place-by | S8 notice record + document generator | S3b roll-up + on-order/in-transit split |
| 6 | S3 timeline screen | S5 exceptions engine | S8 email send + outbox + download | S3b drill-downs: project, dealer ageing |
| 7 | S3 off-mocks | S5 eight-case table | S9 multi-block importer | S3b supplier choice, last PO date |
| 8 | S4 buy plan | S5 propose + approve | S9 allocation suggestion | S3b quantity consequence panel |
| 9 | S4 approval, draft PO grouping | S5 off-mocks | S9 approve + incoming cost capture | S3b four-outcome decision, use-pool path |
| 10 | All: merge in dependency order, browser verification, code review, prod build, PR | | | |

**Gatekeeper checks, not negotiable at merge:** one alembic head and **no migration authored outside
S0**; M3 and M4 goldens unmoved; the `SRTWT7408` pooled-netting case green; no raw INSERT in an
importer; every new route behind the module guard with a permission slug; tests run against a freshly
migrated empty scratch database, because CI has no seed data.

## External dependencies

These are not in our control. Each needs a named owner and a date, and the plan assumes the
stated fallback if it slips.

1. **AutoCount extracts, to the spec in `scm-autocount-extract-spec.md`, in our hands day 1.**
   The hard one. The **outstanding-PO extract gates both tracks**; the outstanding-SO extract gates
   Track 1 only. The exports as they stand are missing a debtor code and a UOM, which is why the
   spec exists and why it has to reach Josephine and Joey before day 1 rather than on it. If they
   arrive day 8, Track 1 ships a correct engine against an empty screen. Fallback: seed from the
   Tuju file plus a synthetic PO book so engine and screens are provable, and treat live
   reconciliation as day 11 onward.
1a. **Two answers, not files:** is the SO quantity column outstanding or originally ordered, and
   which stock-location suffixes hold unavailable stock. Both are in the spec. The second decides
   roughly 60k units of opening balance.
2. **Supplier inventory and pre-load list files, current versions.** We have July samples. If
   the format has drifted, the alias table absorbs it, which is part of why it exists.
3. **WeChat Official Account in Respond.io.** Not procured. Chat stays dark by design; email
   ships. No rework when it lands.
4. **Ms Tee's manual answer for one real shipment**, to check the seeded priority default
   reproduces it (AC-H2). Without this the day-one validation claim is untested.
5. **Mr Loo on the cost basis** (latest, average, landed). Parked in UAC Group K, but the buy row
   shows last purchase cost regardless, which answers his usual question.

## Test plan

Per the three-phase rule, tests land with the wiring, not after.

- **pytest**: golden parity for the 1-bucket path (S2, written first); date-ordered balance
  cases including the 25-Aug-PO-against-3-Aug-SO case (AC-B4); **the `SRTWT7408` pooled-netting
  case - demand 67 against customer bins with 4,397 in the same-site pool must return use-the-pool
  and never a buy (AC-B1c)**; **a cross-site case proving `MWH` stock is not offered to a `BRW-BB`
  shortage (AC-B1d)**; **a client-with-no-convention case proving repointed pool membership works
  without code (AC-B1a-ii)**; scoped restatement including the out-of-scope no-touch case (AC-A5);
  idempotent re-upload (AC-A8); the eight change cases (AC-D8); **the exception-reading inversion table, asserting a discontinued
  C/Z retail surplus proposes keep-and-pool first (AC-D10, AC-D11)**; **a CS-scoped upload unable to
  close a line outside its authority (AC-D2.2)**; allocator fractional fill with M4
  goldens unmoved (S6); multi-block import producing 5 shipments from the sample (AC-G1); split
  allocation summing to shipped quantity (AC-G7); **ordered cost never overwritten by incoming cost,
  and the variance surfacing (AC-C3.3)**; **an order quantity above the shortfall accepted without a
  warning state, with the delta recorded (AC-C2.7, AC-C2.8)**; RBAC denial on every new route
  (AC-J4).
- **Seeding rule**: every test seeds its own chain - policy, config, entity, tracker - with a
  marker prefix. No `LIMIT 1` off an existing table, no assertion about a production row. The
  suite is run against a freshly migrated empty scratch database before pushing, because CI has
  no seed data.
- **vitest**: timeline component in loading, empty, error and data states; loading-plan grid
  including the over-capacity and no-packed-stock deferral states; exception card before-and-after.
- **playwright**: the two golden paths as specs, using the real committed sample files as
  fixtures - upload the Tuju extract through preview and confirm to a timeline, and upload the
  pre-load list through allocation suggestion to approved SPOs.
- **Browser verification**: reached by clicking through the sidebar from `/`, never a deep URL,
  on a production build before any handoff.

## What gets cut first if it slips

Stated now so the decision is not made under pressure at day 8.

1. The weight-change preview (AC-H4). The flip-to-fair weighting still ships; only the
   side-by-side preview goes, and the switch is then an informed manual change.
2. The alias admin screen (AC-I2), falling back to seeded rows only. Costs onboarding
   ergonomics, not function.
3. Plan Exceptions (S5) reduced to detection and display without proposed actions. Joey still
   sees what changed and why, and acts by hand.

Not cuttable: the golden parity guard, scoped restatement with confirm, per-attempt integration
logging, and **pooled netting with the `SRTWT7408` case green**. Each of those guards a failure mode
that is expensive and quiet, and the last guards the one that would discredit the report on its very
first row.

## Verified state of these documents

Every claim here was checked against `main` and the dev database on 2026-08-03 rather than assumed.
The review round overturned five things that had already been written down as settled, which is the
entire point of reviewing before building:

1. Track 2 was described as free of the AutoCount dependency. It is not: the loading plan ranks
   outstanding PO lines.
2. Supply was one number. It is two, on order and in transit, and the split is what the decision
   maker actually reads.
3. Cost was one figure. It is two, ordered and incoming, and the variance between them is the finding
   rather than either figure alone.
4. The shortfall was treated as the answer. It is a floor; the order quantity is a separate decision
   that is routinely larger, and four outcomes exist where I had modelled one.
5. Netting was per warehouse. It is per site pool. ADR-0011 carries a same-day amendment recording
   the error and why it mattered.

## Amendment: the project-vs-dealer split reads `order_type`, not `demand_class` (4 Aug 2026)

Recorded while scoping S3b, whose whole roll-up is built on separating project demand from
dealer outstanding. Checked against the dev database (a copy of production) before building:

- `sales_orders.demand_class` (added by migration 311) is NULL on every row. Nothing writes
  it, and the only reader is a label fallback in `coverage_service`.
- `customers.market_segment_code` is NULL on 3,276 of 3,284 customers: 7 `retail`, 1
  `project`. S1's rule as written ("resolved from the customer's `market_segment_code` at
  import, failing the row loudly when it cannot resolve rather than defaulting to retail")
  would therefore fail almost every row it touched. That line is wrong against the data.
- `sales_orders.order_type` already carries the split and is populated: 9 `project`,
  5 `dealer`, 3 null. It is the field the business actually fills in.

So: **`order_type` is the source of truth for the project-vs-dealer split**, and S3b's
columns read it directly. `demand_class` stays as the PLANNING classification, because
`scm.priority_policy.demand_class_weights` is keyed on it, but it must be STAMPED from
`order_type` at import instead of resolved from a segment code that does not exist. One
definition, derived from the populated field, rather than two fields drifting apart.

Consequence for S1: the loud failure belongs on `order_type` being absent, not on a missing
market segment. Three existing orders have no `order_type` and would be the first to report.

## Amendment: what the consequence panel can actually state (4 Aug 2026)

AC-C2.7 requires the panel to state, on entry of a chosen quantity: shortfall covered, spare
created and where it lands, resulting months of cover, cash committed, and container volume
added. Measured against the dev database before building, over the 3,123 distinct products
carrying a reorder recommendation:

| Figure | Source | Coverage |
| --- | --- | --- |
| Shortfall covered, spare created | computed from the plan | every row |
| Cash committed | `purchase_order_lines.unit_cost` / supplier cost | wherever a cost exists |
| Months of cover | `scm.demand_stat.avg_daily_demand` | **1,933 of 3,123 (62%)** |
| Container volume added | `products.dimensions_*` (millimetres) | **511 of 3,123 (16%)** |

Two consequences for the build:

1. `scm.demand_stat` has **no network-level row**: all 13,555 rows are per (product, warehouse).
   A network-wide months-of-cover therefore SUMS `avg_daily_demand` across warehouses rather
   than reading a single row, and 3,448 of those rows are non-zero, so a product can carry
   stats that are all zero and still have no usable rate.

2. Where an input is missing the panel **names the missing input**; it never prints 0.
   A container volume of 0 reads as "no space needed" and a cover of 0 months reads as
   "already out of stock", and both are decisions made on a figure nobody measured. For 84%
   of items the honest line is "dimensions not recorded", which also makes the gap visible to
   whoever can fix it. This is the same rule the transfer proposals already follow for an
   unconfigured cost or lead time.

### Follow-up: the extract cannot classify a NEW order, and that is an external dependency

Found while writing the failing tests for the amendment above. The `outstanding_so` alias set
is twelve rows and none of them is an order type, so `read_workbook` never sees one. The
consequence splits by case:

- A document that ALREADY exists in the CRM carries `order_type`, so the stamp works as
  described (14 such rows today: 9 project, 5 dealer).
- A document the upload CREATES has no order type anywhere, so it takes the customer-segment
  fallback, which is NULL for 3,276 of 3,284 customers, and then the report path. On a first
  bulk load of the AutoCount extract that is every document.

Handled in two parts, so the code stops being the blocker:

1. `order_type` becomes an alias-mapped OPTIONAL column on the sales-order extract (an
   `import_field_alias` row plus a reader field). Absent, it changes nothing and the file is
   still valid; present, it classifies on import with no code change, because the alias table
   is data. This is the same reason the reader is alias-driven in the first place: onboarding
   a differently-worded export should be an INSERT, not a release.
2. Until the export carries that column, an unclassifiable document is REPORTED against its
   first row rather than defaulted. `retail` by default is the failure the original AC warned
   about: it under-prioritises project orders invisibly, and nobody finds out until a project
   misses its date.

**Ask for the business**: add an order-type (project / dealer) column to the outstanding
sales-order export. Until then the classification only covers orders the CRM already knows.

## Amendment: incoming cost has no source, so C3 splits in two (4 Aug 2026)

AC-C3.2 says incoming cost is captured from the packing list when an SPO allocation is
approved. Traced end to end before implementing, the slot exists at every point and is empty
at every point:

- `inbound_shipment_lines.unit_cost` exists and is populated in 0 of 1,015 rows.
- `InboundShipmentLineBase` accepts it and `create_shipment` would persist it.
- The frontend `packingList.types.ts` declares `unit_cost` and references it nowhere: no
  input, no column, no writer.
- The n8n ingest, which is how packing lists actually arrive, CANNOT supply it.
  `PackingListProduct` is `product_code` plus `quantity`, and the endpoint collapses those to
  `{product_code: quantity}` before building the line. Even if the document extraction read a
  price off the PDF, there is no field to receive it.

So stamping "incoming cost" at allocation time today is a copy of a NULL column onto itself,
and the ordered-to-incoming variance (AC-C3.3) is permanently non-computable.

Split accordingly:

* **Built now, because we own it**: the `inbound_shipment_lines.currency` column (which is
  what makes any cost comparable to `purchase_order_lines.unit_cost` at all), `po_line_id` on
  the allocation create schema (the model column exists, the schema drops it, so an allocation
  is written with no link to the ordered line), the stamp itself, and a derived
  `cost_variance` that refuses to produce a number across two currencies rather than
  subtracting different units. All of it is inert until a cost arrives, and correct the day
  one does.
* **Not built, and not faked**: anywhere the incoming cost or the variance would be shown, the
  honest line is "no incoming cost recorded". A supplier comparison that invents one is worse
  than one that admits the gap, because the whole point of the variance is catching a supplier
  who repriced after we committed.

**Ask for the business**: to get incoming cost, the packing-list extraction must read a unit
price and `PackingListProduct` must carry it. That is an n8n and extraction change, not a CRM
change. This is the second such dependency, alongside the order-type column on the sales-order
export.

## Amendment: the Summary Order Report reads a frozen run, so the run has to freeze a dated shortfall (4 Aug 2026)

AC-C2.1 puts `shortfall` on every row of the Summary Order Report, and the contract the Phase 1
prototype documents is explicit that it is "the dated shortfall from the Coverage Timeline (AC-C1),
NOT on hand + on order - demand". Traced before implementing, the number does not exist anywhere
the report could read it:

- `reorder_run_service` / `reorder_engine` never mention the timeline. The run is still the M3
  dateless engine: `net_position` against `reorder_point`. So the reorder page's buy quantities are
  dateless while the coverage panel beside them is dated, and the two disagree today.
- `coverage_service.coverage_for` produces the dated figure, but per product over ONE pool. The
  report is one row per product NETWORK wide, over roughly 3,100 products carrying a
  recommendation. Calling it per product per request is three queries each, so about 9,400 queries
  on the request path.

Two ways out, and only one of them keeps a single engine:

* **Rejected: a set-based dated shortfall in SQL.** A window function over the union of demand and
  supply events, grouped by product, taking the running-balance minimum. It works, and it puts a
  second implementation of the timeline in SQL next to the Python one. The moment the two differ,
  the report and the coverage panel state different shortfalls for the same product on the same
  screen, which is the one class of disagreement that ends trust in a planning tool.

* **Chosen: the run freezes it.** `run_reorder` computes the dated network shortfall per product and
  persists it on the recommendation. `build_timeline` is untouched and stays the only implementation;
  what is added is a BATCH event reader (all products in three queries, grouped in Python) so the
  background job pays about three queries rather than 9,400, and the pure timeline runs per product
  over in-memory events.

The chosen route also settles AC-C2.9 (a past week is reproducible) by construction rather than by
a second mechanism: the report IS the frozen run, so `run_id` + `as_of` return what the decider saw
because nothing is recomputed against today's book.

Consequences worth stating:

- `suggested_qty` on a row is the SUM of the run's `rounded_qty` for that product. A network-scope
  run has one recommendation per product so the sum is that figure; a warehouse-scope run has one
  per location and the sum over-states against a single network rounding (MOQ and order-multiple
  apply once per location), never under-states. It is a suggestion a person overrides, and the
  alternative - re-rounding across locations at read time - would make the report disagree with the
  reorder page's own numbers for the same run.
- Nothing new is invented for the decision itself. `scm.recommendation_override` already is
  append-only with `original_qty` / `override_qty` / `override_supplier_id` / `overridden_by` /
  `overridden_at`, which is AC-C2.8 exactly, and `decision_service.adjust_recommendation` already
  writes it. The order-quantity decision maps onto that rather than adding a parallel table.

## Amendment: shortfall and suggested answer different questions, so the report names both (4 Aug 2026)

Found by running S3b against the real book rather than the fixtures. A full network run produced
1,969 recommendations over 317 products, and every one of those 317 rows froze a shortfall of
**zero** beside a **non-zero** suggested quantity. ACC6002 reads: on hand 0, no demand, no supply,
short 0, suggested 838.

Nothing is wrong with either number. They are answers to different questions:

* `shortfall` is the DATED gap against **committed orders**. The whole order book is 17 sales
  orders, so almost nothing is committed and almost nothing is uncovered.
* `suggested_qty` is the M3 reorder policy against **forecast** demand - safety stock plus
  lead-time demand off `scm.demand_stat` history. It fires whether or not an order exists.

What was wrong is the screen. Two bare adjacent columns headed "Shortfall" and "Suggested" put
"0" next to "838" on 317 of 317 rows, and a planner reads that as the tool contradicting itself.
Being right in the data and unreadable on the row is the same failure as the plan-exception tile
that printed a fabricated 4.

So the columns now name the demand each is about - **Short vs orders** and **Suggested
(policy)** - with the distinction on the cell rather than as prose in the page. The labels are
the fix; there is no new arithmetic.

Worth stating for S4: the PO worklist inherits this. Joey executes what Mr Loo chose, and if the
chosen quantity came from the policy column while the shortfall column read zero, the worklist
must not re-derive a need from the shortfall.

## Amendment: the SCM order book carries no project name (4 Aug 2026)

AC-C2.3 asks the project drill to show a project name per contributing line. `sales_orders` holds
customer, order type, priority, status and two dates, and nothing else; the project-sales module's
`project_sales_orders` is a separate book with no link to this one. So there is no project name to
read.

The drill labels the line with its **customer**, which on a project order is the main contractor
and is therefore the closest true label, and the gap is recorded here rather than filled with a
fabricated name.

**Ask for the business**: this is the third data dependency outside the CRM, alongside the
order-type column on the outstanding sales-order export and a unit price in the packing-list
extraction. Either the outstanding SO export carries a project reference, or project orders are
raised through the project-sales module so the link exists.

## Amendment: "still to key" includes a row somebody is mid-way through (4 Aug 2026)

AC-E2.4 says filtering to not-keyed is the primary use of the PO worklist. Built literally as
`keyed_status = 'not_keyed'`, the screen contradicted itself the first time a status was set in
a browser: marking a row `keying` dropped it out of the default filter, so the tile read "1 not
yet keyed into AutoCount" one line above a list saying "No row matches this search and filter".
The same figure, disagreeing with itself.

What the filter is actually asked for is **what is left to do**, and a row somebody is part-way
through keying is still left to do. On a shared queue it is the row you most want to see: it is
how the second person knows not to start it, which is the whole reason `keying` exists as a
value rather than a two-state flag.

So the default is **Still to key** = `not_keyed` OR `keying`, matching what the tile counts, with
`Not keyed` / `Keying` / `Keyed` / `All statuses` all still selectable. A use-pool decision
(quantity zero) is excluded from the outstanding set because it carries no purchase order, and
remains reachable under All statuses so the worklist still reconciles one-for-one against the
decisions (AC-E2.5).
