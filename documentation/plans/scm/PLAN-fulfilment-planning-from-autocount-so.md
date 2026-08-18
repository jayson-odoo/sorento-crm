# PLAN: Fulfilment Planning driven by the AutoCount sales order

**Status:** Sections 0 to 12 are APPROVED, 18 August 2026. Both design questions are decided by the
captain (section 11): the **adopted mirror** is the shape ("yeah we can do that no problem"), and the
**fulfilment location is the core sales-order line's own `warehouse_id`** - nobody is asked for it.
Phase 1 frontend prototype is built against mocks; no backend code written yet.

**Section 13 (the multi-order planning board) is DESIGN, awaiting the captain.** It adds a
cross-order board above the per-order sheet and changes nothing in sections 0 to 12; no AC is
superseded. Its own criteria become Group F once it is confirmed. Nothing in it is built until then.

**Classification:** MIXED, and no new schema location. Core `public.sales_orders` stays exactly as it
is (finding G5: the core table stays ignorant of the module). Everything this slice adds lives in
`projects.*`, which is module-owned and purgeable. No new table.

**Depends on (hard):** Stage 1B (PR #209, `app/api/v1/projects/fulfilment_planning.py`,
`app/services/project_so_reconciliation_service.py`) and Stage 1C (PR #214,
`projects.so_supply_decisions`, `app/services/project_supply_service.py`). Neither is on
`origin/main` at `42a61fd6a` - verified: `git cat-file -p origin/main:.../project_so.py | grep -c
SOSupplyDecision` is 0 and `fulfilment_planning.py` is absent. This plan is a stack on top of both
and cannot be implemented before they land.

**Contract it amends:** `PLAN-scm-front-planning.md` sections 1, 3.1, 4, 6.1;
`STAGE1B-scm-front-planning-reconciliation.md` sections 1 to 4;
`STAGE1C-scm-front-planning-promising.md` sections 1, 5, 6. Where this plan and those disagree,
this plan wins for the AutoCount-driven path and they stand unchanged for the authored path.

**UAC:** section 1 of this file, on the captain's instruction (one file). There is deliberately no
separate `*-acceptance-criteria.md`: two files holding one contract is how the contract drifts.

## The captain's decision, verbatim

> "i think it is too much coupling for the fulfilment planning to depend on a autocount sales order
> that depend on the sales order being published, can i just upload whatever autocount has for
> project sales order, then do the fulfilment planning without this coupling?"

> "the autocount sales order should be able to come from http://localhost:3050/scm/sales-orders
> right? so this has to drive the fulfilment planning ... like for example, in
> http://localhost:3050/project-sales/fulfilment-planning, i should be able to choose the
> outstanding project SO from sales order, then perform the fulfilment planning".

> "okay I am okay with the flow, cool, the fulfilment location should be specified at the scm sales
> order line like for example this http://localhost:3050/scm/sales-orders/... the location is my
> fulfilment location that i need to plan against"

> On the adopted mirror: "yeah we can do that no problem"

> "i think the planning is okay for single sales order, but what if it is based on multiple sales
> order, like the user might want to plan against multiple sales order ... I should be able to plan
> multiple sales order also, so I can see something like delivery schedule, across the dates, what
> are the products to be fulfilled, and where will I need to source to fulfil ... then in each cell
> right, there should be a dropdown where your supply composition is broken down, like this quantity
> comes from which sales order, which customer, which project, the quantity, where should it be
> supplied from, in a table, then the user will have to approve / amend / reject the decision like
> your mock right now"

That last one is section 13, the multi-order planning board. It ADDS a surface above the per-order
sheet and takes nothing away from it.

The dependency inverts: the CORE sales order is the subject of planning, and a project-authored
Project SO becomes an optional counterpart rather than the entry ticket. The interim
"publish anyway" override (`POST /sales-orders/{pso_id}/publish` with `acknowledge_blocking`,
`app/api/v1/projects/sales_orders.py:420`) is not depended on anywhere below and is not extended.

---

## 0. Journey (design before schema)

**Actor:** Customer Service. **Arrives from:** the sidebar, Project Sales -> Fulfilment Planning.
Nobody arrives from the projects pipeline for this journey, and nobody has to have published
anything.

**What the system already knows before CS does anything** (measured on the live scratch DB
`sorento_scm_e2e_stack`, section 12):

- 605 project-class sales orders in the core book (`sales_orders.demand_class = 'project'`), every
  one of them still outstanding, carrying their lines with product, quantity, required date and the
  fulfilment location. 318 arrived through CS's weekly outstanding-SO upload
  (`source_system = 'scm_upload'`) and carry a location on **every one** of their 8,854 open lines;
  287 came through the Order Inquiry sheet (`source_system = 'scm_order_inquiry'`) and carry one on
  none of their 2,312 open lines (section 12, re-measured 18 August 2026).
- The customer on each, and the project string the sheet named
  (`internal_note`: "Order Inquiry project: PEMBINAAN TEGUH MAJU / PASAR BESAR CHERAS ...").
- Free unclaimed stock per location, the BRW pool, per-location reorder levels, dealer
  hot-selling classification, incoming SPO quantities and arrival dates, product lifecycle.
- Which of those orders somebody has already planned, and what they decided.

Nothing on that list is asked for. **No new upload is built:** the weekly outstanding-SO upload is
already the AutoCount project sales-order feed, and it is where the 318 came from. "Upload whatever
AutoCount has" is a thing CS already does; what was missing is that planning could not see it.

### The steps

1. **First screen: one worklist of everything that needs planning**, ordered by the earliest
   outstanding required date across its lines, because that is the order the work is actually due
   in. A row states: sales order number, customer, project, earliest required date, outstanding
   quantity, lines, and one whole-order state pill. The pill has four values and the first is new:
   **Not started** (nobody has planned this order), **Awaiting reconciliation**, **Needs CS
   review**, **Confirmed**. The 605 core orders appear as Not started rows from day one; no row
   was written to make them appear.
2. **CS picks one and presses Start planning.** That is the whole decision at this step: which
   order. Everything else is derived - the lines, the products, the quantities, the required dates,
   the locations, the customer. The order opens straight into the planning sheet; there is no form
   in between, no project to choose, no reference to invent.
3. **The sheet opens on the supply composition** (Stage 1C, unchanged): one card per line with open
   quantity, required date, fulfilment location, and a proposed Reserve / timely SPO / Buy split
   with the reason beside each quantity. The reconciliation card above it says, in one sentence,
   that this order came from the AutoCount sales-order book and there is no separately authored
   Project SO to compare it against. The card is rendered, never hidden, with that as its empty
   state and Re-sync as its action.
4. **The fulfilment location is the line's own, and is never asked for.** Each core sales-order line
   carries the location it is to be fulfilled from (`sales_order_lines.warehouse_id`), and that is
   what the sheet plans against, line by line. The captain's words: "the fulfilment location should
   be specified at the scm sales order line ... the location is my fulfilment location that i need
   to plan against". So there is no "Fulfil from" question at order level, no per-line override
   invented at planning time, and above all no default warehouse: a guessed location is a silent
   wrong answer inside a promise to a customer.

   The re-measurement in section 12 is what makes that safe. Counting **open lines of open
   project-class orders only**, every one of the AutoCount book's 8,854 open lines has a location -
   100 per cent - so for the orders this feature is built for, planning needs no extra input at all.
   The 2,312 open lines that came from the Order Inquiry sheet have none, and for those the honest
   answer is that the source record is incomplete: the line is shown as **needing a location on the
   SCM sales order**, with a link straight to that sales order, and it is fixed there. The fix
   belongs on the record that is wrong, not in a prompt that papers over it at planning time.
5. **CS adjusts components and presses Confirm Project SO once** (Stage 1C, unchanged): atomic,
   rechecked against live facts, one refusal naming every failing line by line number and item code.
   The pill flips to Confirmed.
6. **Purchasing opens Order Inquiry** and sees one Buy row per line with a confirmed residual,
   quantity exactly that residual, traceable to the sales order, line number, item code, required
   date and decision revision. Reserve, Borrow and timely SPO never appear there. Unchanged.
7. **Next week's upload moves the book.** A quantity, date or line changed; the sheet says so, the
   active decision is challenged, the pill reads Needs CS review again, and Re-sync brings the
   planning record back in step with the book. Nothing placed is silently deleted.
8. **Months later somebody authors and publishes a Project SO for the same AutoCount number.** The
   publish reconciliation does not fail and does not double-count: it reports, by reference, that
   this AutoCount order is already being planned as an adopted order, and offers Detach there.

**What CS holds at the end:** a confirmed supply decision, per line, for a real AutoCount sales
order that nobody in the projects module authored, with purchasing told exactly what to buy and
nothing else. **What every other stakeholder is told:** purchasing gets the Buy-only rows; the SCM
plan stops counting that order's sheet-leg demand and counts the confirmed Buy instead; the core
sales-order book is untouched.

**Decisions asked of the user across the whole journey:** which order (step 2), and the component
composition (step 5, pre-proposed). That is two, down from three: the fulfilment location used to be
the third and is now read off the line (step 4). Everything else is derived.

**Planning several orders at once** is the same journey with "which order" becoming "which orders",
and is designed in section 13. It is a second way in, not a replacement: this journey stands.

---

## 1. User Acceptance Criteria

Every AC traces to a journey step. Tags: `[FE]` Phase 1, `[BE]`/`[T]` Phase 2, `[E2E]` the recorded
agent-browser evidence run (no new Playwright spec, per CLAUDE.md "Persisted Playwright spec").

### Group A: the worklist (steps 1, 2)

**AC-FP01 [FE][BE][S1] An outstanding project sales order appears without anyone publishing
anything.** Given a core `sales_orders` row with `demand_class = 'project'`, `status = 'open'` and
at least one line still owed, and no planning record of any kind, when CS opens Project Sales ->
Fulfilment Planning, then the order appears as one row reading **Not started**, identified by its
sales-order number and customer, with no Project SO reference and no AutoCount-document column
claiming an upload that never happened.

**AC-FP02 [BE][S1] "Outstanding" means exactly what the netting engine means.** Given the worklist
query, when it selects core orders, then it applies `app.services.scm.demand.is_open_demand()`
unchanged plus `sales_orders.status = 'open'` plus `demand_class = 'project'`, and a project-class
order whose every line is delivered, closed or `purchasing_status = 'covered'` does not appear.
A retired provisional row (`status = 'closed'`) never appears.

**AC-FP03 [FE][BE][S1] The worklist still shows an authored order that has no AutoCount order yet.**
Given a published or amended Project SO with `so_id IS NULL`, when the worklist loads, then that
order appears reading **Awaiting reconciliation** with its exception count, exactly as Stage 1B
shows it today, and it appears exactly once (never twice, once per arm).

**AC-FP04 [FE][BE][S1] The worklist is ordered by earliest outstanding required date, ascending,
nulls last.** Given rows from both arms, when no filter is applied, then the row whose earliest
still-owed line is due soonest is first, and the order is total (tie-broken on sales-order number)
so no row lands on two pages or on neither.

**AC-FP05 [FE][BE][S1] The state filter covers the new value.** Given the `review_state` filter,
when CS selects **Not started**, then only unplanned core orders are listed; an unknown value is a
422, not an empty 200.

**AC-FP06 [BE][S1] The worklist is company-scoped on both arms.** Given two companies, when CS of
company A loads the worklist, then no core sales order and no planning record of company B appears,
and the count agrees with the rows.

### Group B: adoption (step 2)

**AC-FP07 [FE][BE][S2] Start planning is one decision and writes one record.** Given a Not started
row, when CS presses Start planning, then a planning record is created for that core sales order
with one mirror line per open core line, each mirror line already carrying its
`core_sales_order_line_id`, and the sheet opens on it with no further question asked - no project,
no reference, no date, no confirmation dialog (nothing is destroyed).

**AC-FP08 [BE][S2] Adoption is idempotent.** Given a core sales order that already has a planning
record, when Start planning is called again (double click, retry, second user), then the existing
record is returned, no second record and no duplicate mirror line is created, and the response says
which record it is.

**AC-FP09 [BE][S2] Adoption changes no demand.** Given the demand readers, when an order is adopted
and nothing else happens, then `scm.committed_v` returns byte-identical rows, `is_plan_demand_order()`
selects the same orders, and zero `projects.order_inquiry_rows` exist for the new record.

**AC-FP10 [BE][S2] A core sales order can be planned once.** Given a core sales order with a
planning record, when anything attempts to point a second `projects.sales_orders` row at it
(adoption, publish reconciliation, a script), then the write is refused at the database by a partial
unique index and the caller gets a named, human-readable refusal rather than an IntegrityError 500.

**AC-FP11 [BE][S2] Adoption never crosses a company.** Given a core sales order of company B, when
CS of company A calls adopt with its id, then the call is refused (404, as if the row did not exist)
and nothing is written.

**AC-FP12 [BE][S2] Line numbers are stable.** Given an adopted record, when a later core line is
mirrored, then existing mirror lines keep their `line_no` and the new one takes the next number.

### Group C: the sheet on an adopted order (steps 3, 4)

**AC-FP13 [FE][S3] Reconciliation is present and honest.** Given the sheet of an adopted order, when
it renders, then the reconciliation card is present, states in one sentence that the order came from
the AutoCount sales-order book with no separately authored Project SO to compare against, shows the
core sales-order number as the link, offers **Re-sync**, and shows no exception list when the mirror
is in step. The section is never hidden.

**AC-FP14 [FE][BE][S3] An adopted order is immediately reviewable.** Given a freshly adopted order,
when the review state is derived, then it reads **Needs CS review**, because there is nothing to
reconcile; it never reads Awaiting reconciliation.

**AC-FP15 [FE][BE][S4] The line's own location is what it is planned against, and nobody is asked
for one.** Given an adopted order whose core lines carry a `warehouse_id`, when the sheet loads,
then each line's proposal is computed against that line's own location, the location is shown on the
line's card by warehouse code, and the sheet asks no location question anywhere - no "Fulfil from"
select at order level, no per-line override, no defaulted warehouse.

**AC-FP16 [FE][BE][S4] A line whose source record states no location is named, not guessed.** Given
an adopted order with a core line carrying no `warehouse_id`, when the sheet loads, then that line
carries `fulfilment_location_missing`, states "No fulfilment location on the sales order line",
offers a link to that SCM sales order as the way to fix it, and contributes nothing to the proposal;
Confirm is blocked naming that line by line number and item code. No component of any kind is
proposed for it - a Reserve of zero presented as a plan is worse than a refusal.

**AC-FP17 [FE][S3] Confirm behaves identically to the authored path.** Given an adopted order in
Needs CS review, when CS confirms, then the Stage 1C dialog, atomicity, refusal shape
(`failing_lines` with line number and item code, no UUID) and Confirmed pill are the same, and the
Buy-only Order Inquiry handoff produces the same rows.

### Group D: drift and collision (steps 7, 8)

**AC-FP18 [BE][S7] Re-sync is additive and idempotent.** Given an adopted order and a later upload
that added a core line, changed a quantity or a required date, when CS presses Re-sync, then a new
core line is mirrored, a changed one is restated on the mirror, and pressing Re-sync again changes
nothing.

**AC-FP19 [BE][S7] A core line that went away is reported, never silently dropped.** Given a mirror
line whose core line is closed or deleted, when Re-sync runs, then the mirror line is hard-deleted
only if it carries no allocation row at all; otherwise its core link is cleared and it is reported as
an exception naming the line number and item code, Confirm is blocked, and a **Remove line** action
(confirmation dialog, "This action cannot be undone") is the way out.

**AC-FP20 [BE][S7] Drift challenges an active decision.** Given an adopted order with an active
decision, when the core facts behind a snapshot move (open quantity, core line, required date), then
the existing Stage 1C challenge path flips it to `challenged`, the pill reads Needs CS review, and
placed Buy stays in the ledger with an exception row when the new need is lower.

**AC-FP21 [BE][S8] A later authored publish is told the truth.** Given an adopted planning record for
core sales order `SO414033`, when an authored Project SO carrying `autocount_doc_no = 'SO414033'` is
published, then the header reconciliation reports outcome "already adopted" naming the adopted
record's reference, links nothing, writes nothing, and no IntegrityError reaches the client.

**AC-FP22 [FE][BE][S8] Detach is destructive and says so.** Given an adopted record, when CS
detaches it, then a confirmation dialog states the sales-order number and what is discarded
(mirror lines, and the decision revision count when any exist), the record and its mirror lines are
hard-deleted, unplaced Order Inquiry rows for it are cancelled with a reason, the core sales order
and its lines are untouched, and the row returns to **Not started**. Given an active decision exists,
then the detach is refused unless the request carries an explicit acknowledgement and a reason.

### Group E: invariants (all steps)

**AC-FP23 [BE][T] The core table gains nothing.** Given the migration, when it runs, then
`public.sales_orders` and `public.sales_order_lines` have no new column, no new index and no new
constraint, and `tests/test_projects_module_purge_invariants.py` still derives the purge list from
the model files with no new table in it.

**AC-FP24 [BE][T] `scm.committed_v` semantics are unchanged.** Given the view SQL constant
(`app/services/scm/demand.py:188`), when this slice lands, then the constant is byte-identical, and
a test proves that confirming an adopted order moves that core order from the sheet leg to the
confirmed leg exactly once (never both, never neither).

**AC-FP25 [BE][T] AC-A01, AC-A03 and AC-A04 of the Stage 1B contract still hold.** One whole-order
state and no per-line workflow state anywhere (AC-A03) - "Not started" is a whole-order value, not a
line value; a Needs CS review order of either origin contributes zero purchase requirement
(AC-A04); the authored journey through ingest and reconcile is unchanged (AC-A01), proven by the
existing Stage 1B tests staying green untouched.

**AC-FP26 [BE][T] No new permission.** Given the new routes, when they are gated, then they reuse
`projects.projects.view` and `projects.projects.edit`, so no role grant sweep is required and no
feature silently 403s.

**AC-FP27 [E2E] The whole journey is walked in a browser.** Sidebar Project Sales -> Fulfilment
Planning, a Not started row, Start planning, the sheet, Fulfil-from, Confirm, the Confirmed pill,
Re-sync, Detach with its dialog; network shows the expected `/api/v1/project-sales/*` calls;
`console` and `errors` clean; 1280x800 and 375x812.

---

## 2. The design decision, and the two it beats

The subject of planning must become the core sales order. Three ways to do that were on the table.

**Chosen: the planning record is adopted from the core sales order.** `projects.sales_orders` gains a
status `adopted` and a nullable `project_id`; adopting a core sales order writes one such row with
`so_id` set and one mirror line per core line with `core_sales_order_line_id` already filled in.

Why this one:

- **Every planning fact already comes from the CORE line, not the project line.** Verified in
  `app/services/project_supply_service.py:1299` (`_facts_for`): product, warehouse, required date and
  open quantity are all read off `SalesOrderLine`; the project line contributes `line_no`, its id as
  the payload key, a `delivery_date` fallback, display text and `stock_location`. The mirror line is
  therefore an addressing shim, not a second source of truth, and it cannot disagree with the book
  about anything that matters.
- **Nothing downstream changes.** `projects.so_supply_decisions`, `projects.so_line_allocations`,
  `projects.order_inquiries`, `projects.order_inquiry_rows`, `scm.committed_v`, the Stage 2 channel
  columns and the whole Stage 1C sheet keep working verbatim, because they all reach the core line
  through `projects.sales_order_lines.core_sales_order_line_id` - which the mirror fills in at
  adoption. The confirmed leg of `COMMITTED_V_SQL` (`app/services/scm/demand.py:234-247`) and the
  `decided` CTE (`:190`) both light up for an adopted order with no view edit at all.
- **Purge and ownership stay right.** The planning record is module brain state in the module's own
  schema (ADR-0011); purge deletes it and the core sales order survives (ADR-0009's purge clause).
  Core carries no module column (finding G5, AC-FP23).

**Rejected: re-key the decision tables onto the core sales order** (nullable
`project_sales_order_id`, new `sales_order_id` on `so_supply_decisions`, new
`core_sales_order_line_id` on `so_line_allocations` and `order_inquiry_rows`, `NOT NULL` dropped on
`so_line_allocations.so_line_id` and `order_inquiries.project_sales_order_id`, two unique indexes
rebuilt, `scm.committed_v` rewritten with a two-arm join, the whole of
`project_supply_service.py` re-keyed, the Stage 1C FE payload key `project_line_id` renamed). This is
the theoretically cleaner inversion and it is a rewrite of a lane that shipped yesterday, across a
view Stage 2 is concurrently extending. Verified `NOT NULL` on both blocking columns in the live DB.
It buys correctness we can get without it, and its blast radius crosses three in-flight lanes.

**Rejected: eagerly materialise all 605.** It removes the union from the worklist query, and it
costs 605 + 16,879 rows nobody asked for, a resync daemon, and either a hook in
`outstanding_import_service` (which ADR-0010 pins as unchanged and module-ignorant) or a scheduled
job. Also worse for the journey: the captain asked to *choose* the order.

**A mirror is duplication, and the plan says so out loud.** The mitigation is that it is
write-once-plus-resync, never authoritative: the sheet reads the core line, Re-sync restates the
mirror, and drift on a fact that matters challenges the decision through the path Stage 1C already
built (`challenge_if_drifted`, `project_supply_service.py:500`).

### Consequential decisions

| Question | Decision | Why |
|---|---|---|
| Worklist rows: core SOs, or a union? | Union of two arms, one row per subject | An authored order with no core SO yet (Stage 1B's Awaiting reconciliation, AC-FP03) has no core row to be a row of. The arms are disjoint by construction: arm 1 is core orders LEFT JOINed to their planning record, arm 2 is planning records with `so_id IS NULL`. |
| Row identity in the API | `row_kind` plus the id that exists (`sales_order_id` on arm 1, `id` on arm 2) | Addressing only, like `ReconciliationLine.id` and `source_warehouse_id`; never rendered. |
| How is "adopted" marked? | A `status` value, not an `origin` column | Fifteen sites already branch on the `(published, amended)` pair; they need a verdict on adopted either way, so a status value costs one sweep and no new column. The pair is consolidated into `LIVE_SO_STATUSES` / `CONFIRMABLE_STATUSES` in `app/models/project_so.py` in the same change, because fifteen copies of one tuple is a latent drift bug. |
| `provisional_ref` for an adopted record? | The core `so_number`, `NOT NULL` kept | The column is `NOT NULL UNIQUE(company, ref)` and is read as the display key in a dozen places; making it nullable is a bigger audit than filling it. The FE never shows it twice: an adopted row shows one "Sales order" column and an empty "Project SO" cell. |
| `autocount_doc_no` and `so_id`? | Both set at adoption: `so_id` = the core row, `autocount_doc_no` = its `so_number` | For an order that came out of the book, the AutoCount document number IS the sales-order number. The Stage 1B header outcome for it is `linked` on the strength of `so_id`, which section 2 of that note already makes the deciding fact. |
| What does reconciliation MEAN with no authored document? | A one-way SYNC, not a diff | There is no second document to disagree with. `reconcile()` dispatches on status: authored keeps the two-pass mapping (`project_so_reconciliation_service.py:319`), adopted mirrors the book. Same route, same button, same summary shape. |
| Is the (customer PO no, area group) match promoted to a suggestion? | No, it is impossible from this side | The outstanding-SO extract carries `so_number`, `item_code`, `qty_outstanding`, `required_date` and an optional location (`app/services/scm/outstanding_reader.py:36`). It carries no customer PO number, so the natural key of `_candidates` (`project_so_ingest_service.py:464`) has nothing to match on. The suggestion that IS available is `autocount_doc_no` equality, which the publish path already uses; that is why AC-FP21 is a collision report rather than an auto-merge. |
| An unmatched P8a upload | Gains a real answer, stores no new row | When `doc_no` names a core sales order, the ingest returns a new outcome `in_sales_order_book` with the sales-order number and a link to Fulfilment Planning, so the upload is not a silent no-op. When it names nothing, `unmatched` still stores nothing. Storing rejected documents is open question 3. |
| Where does the fulfilment location come from? | The core sales-order line's own `warehouse_id`, always | Captain's decision, section 11. It is stated on the record the customer's order actually is, and it is present on 100% of the AutoCount book's open lines, so planning asks nothing. A line without one is an incomplete source record and says so; the module writes no location of its own and invents no default. `projects.sales_order_lines.stock_location` stays a mirrored copy for display, never the source. |
| Authorisation with no project | Module permission alone | `assert_can_edit_project` cannot run without a project. Adopt / Re-sync / Detach / Confirm on a record with `project_id IS NULL` are gated on `projects.projects.edit` only, and the check is kept for records that DO have a project. Recorded as an accepted narrowing, not an oversight. |
| Header uniqueness on `so_id` | New partial unique index | Free today: 0 of the 16 project SOs carry a `so_id`. It is what makes the double-confirmed-leg count impossible (AC-FP10, AC-FP24) instead of merely unlikely. |

---

## 3. What "outstanding" is, exactly

One definition, reused, not restated:

```python
# app/services/scm/demand.py
is_open_demand()   # line_status == 'open' AND purchasing_status != 'covered'
                   # AND greatest(coalesce(qty_required, qty_ordered) - qty_delivered, 0) > 0
```

plus, at header level, `SalesOrder.status == 'open'` and `SalesOrder.demand_class == 'project'`.

Justification for each part: `is_open_demand()` is what `scm.committed_v` counts and what the
existing `outstanding=true` filter on `GET /api/v1/scm/sales-orders` already means
(`app/services/scm/sales_order_service.py:304`), so the SO book screen the captain pointed at and
this worklist cannot disagree about which orders are still owed. `status = 'open'` is the header half
of the same view predicate and is what keeps a retired provisional row
(`project_so_ingest_service.py` `RETIRED_ORDER_STATUS`) out of a planning screen. `demand_class`
lives on the core table and is stamped by the importer from the file's demand-split column; reading
it from the module is a read of core, which is allowed and adds nothing to core.

`demand_origin` is deliberately NOT part of the filter. Today all 605 project-class rows carry
`demand_origin = 'scm_order_inquiry'`, so all 605 are counted by the sheet leg. A project-class order
the sheet never named (origin NULL) is **set aside** from planning demand entirely by S13b
(`PLAN_DEMAND_ORDER_SQL`, `demand.py:67`) and is invisible to purchasing today. Those orders are the
ones this feature helps most, and after confirmation their Buy residual becomes demand for the first
time through the confirmed leg. That is intended, and AC-FP24 pins it.

---

## 4. Data model and migration

One revision. Revision id `383_adopted_autocount_planning` (30 chars, under the 32 limit).
`down_revision` is main's single head at implementation time - re-check `alembic heads` immediately
before merge, and do NOT chain onto the disposable e2e stack's merge revisions
(`382_merge_loading_plan_stack` exists only on `fm/scm-e2e-integration-stack`). `depends_on =
('374_so_supply_decisions',)` so it cannot run before Stage 1C's table exists.

All DDL guarded per object (`sqlalchemy.inspect` on the bind), the pattern Stage 1C already uses for
its parallel-lane collision.

### `projects.sales_orders`

1. `project_id` -> **NULLABLE** (`ALTER COLUMN DROP NOT NULL`). The FK and `ON DELETE RESTRICT`
   stay. An adopted order has no project registration and must not invent one: auto-creating 605
   registrations would pollute the pipeline and collide with ADR-0004 registration exclusivity, and
   asking CS to pick one would add a decision per order for a fact the source document does not
   carry.
2. Partial unique index `uq_projects_so_core_order` on `(so_id) WHERE so_id IS NOT NULL`. Verified
   safe: 0 rows carry `so_id`.
3. New status value `adopted` (a model constant `SO_STATUS_ADOPTED`; the column is
   `String(24)` with no DB enum, so no DDL). `published_by` / `published_at` stay NULL on an adopted
   row, which is the truth: nobody published it.

No new column. `origin` is not added (section 2).

### `projects.sales_order_lines`

Nothing. `core_sales_order_line_id`, `stock_location`, `line_no`, `delivery_date` and
`uq_projects_so_line_core_line` (`app/models/project_so.py:521`) are all already there and are
exactly what the mirror needs.

### Status-tuple consolidation (code, not DDL)

`LIVE_SO_STATUSES` and `CONFIRMABLE_STATUSES` move into `app/models/project_so.py` and every site
below imports them. The fifteen current sites get an explicit verdict:

| Site | Adopted in? | Why |
|---|---|---|
| `project_so_reconciliation_service.py:113` `LIVE_SO_STATUSES` (worklist, evaluate, reconcile) | IN | It is a live order with a core SO. |
| `project_supply_service.py:91` `CONFIRMABLE_STATUSES` | IN | Confirming it is the point. |
| `project_so_delta_service.py:549` (amendment publish) | OUT | There is no authored document to amend. |
| `project_so_ingest_service.py:476` `_candidates` | OUT | An adopted record was never exported to AutoCount, so it is not a match-back candidate. |
| `project_po_service.py:623,:661`, `project_order_inquiry_service.py:472`, `project_so_draft_service.py:1966,:2166,:2219,:2365,:2527,:2581,:2587,:2676,:2953` | OUT (authoring / worksheet / draft-findings / publish paths) | Each is about a document this system authored. An adopted record is not editable, not amendable and never appears in a release worksheet. |

Every OUT site keeps the explicit `(published, amended)` pair under a named constant
`AUTHORED_LIVE_STATUSES`, so "why is adopted not here" is answered by the name.

### Backfill

- The 16 existing project SOs: nothing. They are authored; no new column touches them.
- The 605 core project-class orders: **deliberately no backfill**. Adoption is lazy by design
  (section 2). This is not a DoD gate 2 miss: no column was added to those rows and no engine reads
  a value they lack. Stated here so a reviewer does not have to guess.
- The unique index is created non-concurrently and is allowed to fail loudly if a duplicate `so_id`
  ever exists, rather than being created with a silent dedupe.

---

## 5. Backend

### 5.1 `app/services/project_so_adoption_service.py` (new, small)

- `adopt(sales_order_id, actor_user_id) -> ProjectSalesOrder`. Loads the core order inside company
  scope (404 when out of scope, AC-FP11); refuses when it is not project-class, not `open`, or has
  no open-demand line; returns the existing planning record when one already points at it
  (AC-FP08); otherwise inserts the record (`status = 'adopted'`, `so_id`, `autocount_doc_no =
  so_number`, `provisional_ref = so_number`, `project_id = NULL`) and one mirror line per core line
  with `line_status = 'open'`, taking `product_id`, `qty = qty_ordered`, `unit_price`,
  `delivery_date = required_date`, `uom` from the product base UOM, `description` from the product
  name, `stock_location` from the core warehouse code, and `core_sales_order_line_id`. Initial
  `line_no` by (`required_date` nulls last, product code, core line id) so it is deterministic;
  later lines take `max + 1` (AC-FP12). Insert catches the unique-index violation and re-raises it
  as a named `AppException` (AC-FP10).
- `resync(order) -> list[str]` (the changes it made, as sentences). Additive: mirror missing core
  lines, restate qty / date / price / location on existing ones, hard-delete a mirror line whose
  core line is gone ONLY when it has no `so_line_allocations` row, otherwise clear its core link
  (AC-FP19).
- `detach(order, acknowledge, reason)`. Refuses with 409 when an active decision exists and
  `acknowledge` is false; otherwise supersedes the decision through
  `ProjectSupplyService.supersede_for_material_change` (`project_supply_service.py:482`), cancels
  unplaced Order Inquiry rows for it with a note, then hard-deletes the record (mirror lines go by
  CASCADE). Never touches core (AC-FP22).

### 5.2 `project_so_reconciliation_service.py`

- `reconcile(order)` (`:319`) dispatches on status: `adopted` -> `resync` then evaluate; authored ->
  unchanged two-pass mapping. Same route, same response shape.
- `evaluate(order)` (`:279`) for an adopted order returns header outcome **`adopted`** with a reason
  sentence, `lines_total`/`lines_linked` from the mirror, and exceptions ONLY for a mirror line whose
  core link was cleared. `review_state` is `needs_cs_review` when every mirror line is linked
  (AC-FP14), `confirmed` when an active decision exists (Stage 1C rule, unchanged).
- `review_states_for(order_ids)` (`:284`) widens its status filter to the new `LIVE_SO_STATUSES`.
- `list_fulfilment_planning` (`:892`) becomes the union of section 6's two arms. Paging stays in SQL
  when `review_state` is not filtered and moves to Python when it is, for the reason already
  documented there (the state is derived and has no column). The order-by becomes earliest
  outstanding required date, tie-broken on the sales-order number (AC-FP04).

### 5.3 `project_supply_service.py`

Two changes only:

- `_facts_for` (`:1299`) resolves the fulfilment warehouse as `core.warehouse_id`, full stop
  (AC-FP15). The `warehouse_code = line.stock_location` lookup stays only as the authored path's
  existing fallback, and no new location is ever written by this slice.
- A core line with no `warehouse_id` is not silently proposed as all-Buy and is not asked about: the
  proposal payload carries `fulfilment_location_missing: true` on that line, no component is
  proposed for it, and Confirm refuses it through the existing `SupplyLinesRefused` shape with reason
  "No fulfilment location on the sales order line" (AC-FP16). The way out is the SCM sales order,
  which the sheet links to.
- `_header_fields` and `_review_state` tolerate `project_id IS NULL` (project code and name come
  back null; the row's project label falls back to the core order's `internal_note` project string).

`propose_line`, `confirm`, `attribute_sources`, the snapshots, the allocations and the Buy handoff
are untouched.

### 5.4 `project_so_ingest_service.py`

- `reconcile_core_order` (`:259`) gains a fifth outcome: the real number's core row is already held
  by another planning record. Log, link nothing, and surface header outcome `core_so_adopted` with
  the holding record's reference (AC-FP21). This is checked BEFORE the write so the unique index is
  a backstop, not the error path.
- `ingest` (`:168`) returns `in_sales_order_book` instead of bare `unmatched` when `doc_no` names a
  core sales order (section 2 table).

### 5.5 Routes (`app/api/v1/projects/fulfilment_planning.py`)

Additive, on the same router, mounted ahead of `sales_orders.router` as the file already requires.
`GET` reads `require_permission_with_api_key("projects.projects.view")`; writes
`require_permission("projects.projects.edit")` and keep `assert_can_edit_project` when the record
has a project (section 2).

---

## 6. API contract (Phase 1 builds the mock against this; Phase 2 must match)

```text
GET /project-sales/fulfilment-planning
    ?page&limit&query&review_state&project_id&sales_order_id
    -> ListResponse<FulfilmentPlanningRow>
    review_state closed set: not_started | awaiting_reconciliation | needs_cs_review | confirmed
    query matches sales-order number, customer name, the project string, project code and title,
      provisional ref, AutoCount doc no, area group

FulfilmentPlanningRow {                      // additive to the Stage 1B row
  row_kind: 'sales_order' | 'planning_record',
  id?: string,                               // planning record id; absent when not started
  sales_order_id?: string,                   // core sales_orders id; absent on the arm-2 rows
  so_number?: string,                        // the AutoCount / core number, the human key
  origin?: 'authored' | 'adopted',           // absent when not started
  provisional_ref?: string,                  // absent for a not-started row
  autocount_doc_no?: string,
  project_id?: string,                       // NULLABLE now
  project_code?: string, project_name?: string,
  project_label?: string,                    // project name, else the core order's project string
  customer_name?: string, po_number?: string, area_group?: string,
  status?: string,                           // draft | published | amended | adopted
  line_count: number, lines_linked: number, exception_count: number,
  outstanding_qty: string,                   // decimal string
  earliest_required_date?: string,
  review_state: 'not_started' | 'awaiting_reconciliation' | 'needs_cs_review' | 'confirmed',
  updated_at?: string
}

POST /project-sales/fulfilment-planning/adopt
    body { sales_order_id }
    -> { project_sales_order_id, so_number, review_state, already_adopted: boolean }
    409 when another planning record holds that core order, naming its reference

POST /project-sales/sales-orders/{pso_id}/reconcile      // unchanged route, dispatches on status
    -> ReconciliationSummary
       header.outcome gains 'adopted'
       ReconciliationSummary gains synced: string[]      // what the re-sync changed, as sentences

POST /project-sales/sales-orders/{pso_id}/detach
    body { acknowledge_supersede: boolean, reason?: string }
    -> { detached: true, sales_order_id, discarded: { lines, decisions, cancelled_inquiry_rows } }
    409 { message, code: 'adopted_order_has_active_decision' } when acknowledge is false

// No fulfilment-location endpoint exists, by decision: the location is the core line's own
// warehouse and this module never writes one (section 11, question 2).

GET /project-sales/sales-orders/{pso_id}/supply          // unchanged; three additive fields
    SupplyLine gains fulfilment_location_missing: boolean // the core line states no warehouse
    SupplyProposal gains sales_order_number: string       // the human key
    SupplyProposal gains sales_order_id: string           // addressing only, for the /scm link
    SupplyProposal.project_id becomes nullable
```

Removed from the FE's assumptions: `FulfilmentPlanningRow.project_id` and `provisional_ref` are no
longer guaranteed. Both were required in
`app/(protected)/project-sales/_shared/types/fulfilmentPlanning.types.ts` and must be widened in
Phase 1.

---

## 7. Frontend

Layering as enforced: grid / sheet -> `useFulfilmentPlanning` and new
`useFulfilmentPlanningMutations` -> `app/(protected)/project-sales/_shared/services/fulfilmentPlanningService.ts`
-> `lib/api` -> FastAPI. `extractApiError` and `buildDataGridParams` only, both already used in that
service. New selects use `SearchableSelect` with `clearable` where optional.

- `FulfilmentPlanningClient.tsx`: columns become Sales order (`so_number`), Customer, Project
  (`project_label`), Earliest required, Outstanding qty, Lines, Review state, the row action, then
  Project SO (`provisional_ref`, empty state "Not authored here"), Customer PO, Area group,
  Updated. Grid keeps `tableLayout={{ width: 'fixed', columnsResizable: true }}` with explicit
  `size` per column and `truncate` + `title` on text. Row action on a Not started row is **Start
  planning**; on any other row it is Open, and clicking the row itself opens the sheet only when a
  planning record exists (a row click must never be what writes one).
- **The `listingKey` stable id is bumped to `...::project-fulfilment-planning-v2`.** Four columns
  are new and one (`autocount_doc_no`) is gone, so this is not the same listing it was: a config
  saved against the old set interleaves the new columns into an order nobody chose. Measured in the
  browser during Phase 1 - the screen came up as Sales order, Project SO, Review state, action,
  Lines with Customer and both dates pushed off to the right, and only Columns -> Reset fixed it.
  Bumping the id hands everyone the new defaults once, which is the honest answer to "the columns
  changed". Anyone who had resized this grid sets it again; that is the whole cost.
- `ReviewStatePill` and `REVIEW_STATE_LABELS` gain `not_started` -> "Not started". The Project SO
  status label / pill maps gain `adopted` -> "Adopted" in the same change (grep the SO status label
  map used by the project's Sales orders panel and the SO detail header; a status with no label
  renders the raw code, which is the "no UUIDs / human-readable" rule failing quietly).
- `FulfilmentPlanningSheet.tsx`: the reconciliation card gains its adopted variant (one sentence,
  the core sales-order number, Re-sync, the `synced` sentences after a run, an explicit "nothing to
  reconcile" empty state) and a **Detach** action in the sheet header with `ConfirmDeleteDialog`
  copy naming the sales order and the counts.
- `SupplyCompositionSection.tsx` / `SupplyLineCard.tsx`: each line states its own fulfilment location
  by warehouse code, and a line carrying `fulfilment_location_missing` renders the blocked state with
  a link to its SCM sales order. There is no location select anywhere on this screen.
- Every state rendered: loading skeletons, empty worklist, request error with Try again, not-started
  row, adopted-with-no-exceptions, adopted-with-a-vanished-line, a line whose sales order states no
  location, confirmed frozen view, detach refused by an active decision.
- Column-preference gotcha: CONFIRMED in Phase 1, and answered by the `listingKey` bump above
  rather than left for Phase 2. `useListingColumnPreferences` keeps a saved order for the columns it
  knows and appends the rest, so a changed column set reads as a scrambled screen and not as a
  missing feature.

---

## 8. Invariants this must not break

1. **Core stays module-ignorant** (finding G5, ADR-0009). No column, index or constraint on
   `public.sales_orders` / `sales_order_lines`. AC-FP23.
2. **Module purge list is unchanged** (ADR-0009 purge clause, ADR-0011). No new table, so
   `tests/test_projects_module_purge_invariants.py` needs no edit and must stay green untouched.
3. **`scm.committed_v` is byte-identical** (`COMMITTED_V_SQL`, `demand.py:188`) and stays one
   aggregate row per `(product_id, warehouse_id)`. AC-FP24. The Stage 2 channel columns are not
   touched.
4. **One confirmed leg per core order.** The partial unique index on `so_id` is what guarantees
   confirmed Buy cannot be counted twice for one core sales order. AC-FP10.
5. **AC-A03: one whole-order state, never a per-line one.** "Not started" is an order-level value.
   No cell anywhere reads partially confirmed, confirmed or purchasing-ready per line.
6. **AC-A04: pre-confirmation demand is excluded.** Adoption writes no `order_inquiry_rows` and no
   allocation. AC-FP09.
7. **AC-A01: the authored journey is untouched.** Ingest -> reconcile -> Needs CS review keeps
   working, proven by the Stage 1B suites staying green with no edits.
8. **Company scoping is fail-closed** (AC-G06). Both worklist arms scoped; adoption across companies
   refused; `reconcile_core_order`'s existing cross-company refusal untouched.
9. **ADR-0010: `outstanding_import_service` stays unchanged and module-ignorant.** Nothing in this
   plan hooks it. The `demand_origin` literal `scm_order_inquiry` is not renamed.
10. **ADR-0011: module tables stay in `projects` with cross-schema FKs.** The new FK usage
    (`projects.sales_orders.so_id`, already present) is unchanged.
11. **No new Playwright spec** (standing order). A recorded agent-browser evidence run stands in and
    the missing regression guard is logged in `documentation/backlogs/backlog.md`.

Not affected, stated so a reviewer does not have to check: no `list_query_registry` entry (this
screen has its own route), no embedding-pipeline change (sales orders are answered by SQL, never
embedded), no RQ task and no worker restart, no MCP tool or catalog change, no new setting.

---

## 9. Phasing

### Phase 1 - frontend against a mock (no backend code, no tests)

Mock behind `NEXT_PUBLIC_FULFILMENT_MOCK=1`, the same switch idiom as the Stage 1B
`NEXT_PUBLIC_PROJECT_SO_MOCK`, in
`app/(protected)/project-sales/_shared/services/fulfilmentPlanningService.ts`, with the fixtures in
`app/(protected)/project-sales/_shared/services/__mocks__/fulfilmentPlanning.fixtures.ts`. The
fixtures are **real-shaped**: the sales-order numbers, customers, project strings, products,
quantities, required dates and warehouse codes are read out of the live scratch DB
`sorento_scm_e2e_stack`, so the captain recognises the rows rather than reading invented ones.
Fixtures: Not started rows from the AutoCount book, an adopted needs-review order, a line whose
sales order states no location, a confirmed adopted order, an authored awaiting-reconciliation row,
an empty worklist, a failed request. Verify by sidebar clicks in agent-browser at 1280x800 and
375x812; screenshot the golden path and every edge state.

**Throwaway by design:** these fixtures and the mock switch branch are deleted when Phase 2 lands.
The component tests carry their own fixtures; a second source of these shapes drifts from the real
one (the Stage 1B note records the same deletion).

### Phase 2 - backend, test-first, then FE off the mock

Order: migration -> model constants and the status sweep -> adoption service -> reconciliation
dispatch -> worklist union -> supply-service location fallback -> ingest outcomes -> routes -> FE
swap (one line per call at the service boundary).

Tests, all written red first, all landing in this phase:

- **pytest**, Postgres via `tests/_pg_fixture.py`, every test seeding its own chain with a marker
  prefix and never borrowing a row (`LIMIT 1` off a live table is what makes a suite pass locally and
  fail in CI's empty database):
  `tests/test_project_so_adoption.py` - adopt happy, idempotent adopt, cross-company refusal,
  non-project refusal, fully-delivered refusal, line-number stability, second-record refusal by the
  unique index mapped to a named error, resync add / change / vanished-line-with-allocation /
  vanished-line-without-allocation, detach refused with an active decision, detach with
  acknowledgement cancelling unplaced inquiry rows, core rows untouched after detach.
  `tests/test_fulfilment_planning_worklist.py` - both arms present exactly once, outstanding
  definition (a covered / delivered / closed order absent), ordering total and by earliest date,
  `not_started` filter, unknown filter 422, company scoping, pagination totals.
  `tests/test_adopted_order_demand_invariants.py` - `committed_v` byte-identical after adoption;
  after confirmation the core order leaves the sheet leg and appears once in the confirmed leg; a
  set-aside (origin NULL) project order becomes demand only through confirmed Buy; zero inquiry rows
  before confirmation.
  `tests/test_project_so_reconciliation_adopted.py` - header outcome `adopted`, review state
  `needs_cs_review` immediately, `core_so_adopted` on a later authored publish with no
  IntegrityError.
  Route tests for every new endpoint: happy, 403 without permission, 404 unknown id, 422 bad body,
  409 on the two named conflicts.
  Plus: the existing Stage 1B and 1C suites must pass with zero edits (AC-FP25, AC-FP07 regression).
- **vitest**: worklist client (four pills, not-started row action, ordering column, empty, error),
  sheet adopted variant, detach dialog copy, fulfil-from select and the blocked state, service tests
  for each new URL and its failure. `useListingColumnPreferences` mocked, per the CLAUDE.md note.
- **agent-browser evidence run** against the real stack, recorded step by step in the test report
  section of this file (AC-FP27), with `get url` before every read and the session closed at the end.

### Phase 3 - review

`/code-review ultra` (the diff crosses three lanes), then `documentation/reference/PR-CHECKLIST.md`
plus the DoD gate. PR body carries the Phase 1 screenshots, the Phase 2 test counts and the evidence
run.

---

## 10. Risks

| Risk | Control |
|---|---|
| The mirror drifts from the book and somebody plans against a stale quantity | The sheet reads the core line for every fact that matters (`_facts_for`); drift on a snapshotted fact challenges the active decision through Stage 1C's existing path; Re-sync is one button and idempotent. |
| A line whose sales order states no fulfilment location cannot be planned | For the AutoCount book this does not arise: 8,854 of 8,854 open lines carry one (section 12). Where it does arise (the Order Inquiry sheet's 2,312), the line is blocked and named rather than guessed at, and the sheet links to the SCM sales order where the location belongs (AC-FP16). Nothing is defaulted. |
| Confirmed Buy counted twice for one core order | Partial unique index on `so_id`, plus the invariant test. |
| The status sweep misses a site and an adopted order enters an authoring path | The `(published, amended)` pair is consolidated into two named constants and every one of the fifteen sites gets an explicit verdict in section 4; a test asserts an adopted order is rejected by amendment publish and never appears in `_candidates`. |
| Three in-flight lanes (1B, 1C, Stage 2) touch the same files | This plan is stacked and cannot start before 1B and 1C merge; it edits `demand.py` not at all, which is where Stage 2 collides. |
| Migration chains onto the wrong head | `depends_on` on Stage 1C's revision, and `alembic heads` re-checked immediately before merge; never chain onto the e2e stack's merge revisions. |
| 605 Not started rows read as noise | Default order is earliest outstanding required date, so the top of the list is the work that is due; the state filter narrows to Not started in one click. |

## 11. Decisions taken, and what is still open

### 1. DECIDED: the adopted mirror (captain, 18 August 2026)

> "yeah we can do that no problem"

Adopting a core sales order writes one thin `projects.sales_orders` row (`status = 'adopted'`,
`so_id` set to the core order, `project_id` NULL, `provisional_ref` and `autocount_doc_no` both the
core `so_number`) plus one mirror line per open core line, each already carrying its
`core_sales_order_line_id`. **The mirror holds no facts of its own**: product, quantity, required
date and fulfilment location are every one of them read off the core line at read time
(`_facts_for`), so the mirror cannot disagree with the book about anything that matters. It is an
addressing shim, and Re-sync is what keeps its addresses current.

**Re-keying the decision tables onto the core sales order is REJECTED FOR NOW**, not rejected
forever. Rejected because it rewrites Stage 1C the day after that lane shipped (drop `NOT NULL` on
`so_line_allocations.so_line_id` and `order_inquiries.project_sales_order_id`, add
`core_sales_order_line_id` to two more tables, rebuild two unique indexes, re-key the whole of
`project_supply_service.py`, rename the FE payload key `project_line_id`) and because it changes
`scm.committed_v` while Stage 2 is concurrently extending that same view. It stays available later
as a pure migration: the mirror rows ARE the mapping, so a future re-key reads
`projects.sales_order_lines.core_sales_order_line_id` and rewrites the pointers, with no information
to recover from anywhere else. Nothing in this slice forecloses it.

### 2. DECIDED: the fulfilment location is the core sales-order line's own (captain, 18 August 2026)

> "the fulfilment location should be specified at the scm sales order line like for example this
> ... the location is my fulfilment location that i need to plan against"

Planning reads `sales_order_lines.warehouse_id` per line and plans against it. Nobody is asked for a
location: no "Fulfil from" at order level, no per-line override, no default warehouse anywhere in
this slice. Journey step 4, AC-FP15 and AC-FP16 are written to this.

What makes it safe is the re-measurement in section 12, and the earlier "8,011 of 16,879 lines have
no location" figure in this plan is **superseded**: it counted closed lines of the whole book.
Counting only OPEN lines of OPEN project-class orders, the AutoCount upload's 318 orders carry a
location on 8,854 of 8,854 open lines - 100 per cent - so for the book this feature exists to plan,
there is no extra input to ask for. The Order Inquiry sheet's 287 orders carry one on 0 of their
2,312 open lines; those lines still appear in the worklist, and each states that its sales order has
no fulfilment location with a link to that sales order. The fix belongs on the source record.

### 3. Still open, and answerable later

Should an unmatched P8a upload be STORED (a new `projects.autocount_documents` row, which lands on
the module purge list), or is the new `in_sales_order_book` outcome plus a link enough?
Recommendation: the outcome and the link; a table for rejected files buys diagnostics and costs a
purge entry. Nothing in Phase 1 or Phase 2 blocks on this - it only decides whether section 5.4
grows a table later.

That is the only one left. Everything else in this plan is decided.

## 12. Facts measured, not assumed

Live scratch DB `sorento_scm_e2e_stack`, 18 August 2026:

| Fact | Value |
|---|---|
| `sales_orders` rows | 13,856 |
| ... with `demand_class = 'project'` | 605, all `status = 'open'`, all `demand_origin = 'scm_order_inquiry'` |
| ... by `source_system` | 318 `scm_upload`, 287 `scm_order_inquiry` |
| Project-class orders still outstanding by `is_open_demand()` | 605 of 605 |
| Project-class core lines, ALL statuses | 16,879: 8,868 with `warehouse_id`, 16,740 with `required_date` |
| **OPEN lines of OPEN project-class orders, by source** (re-measured 18 August 2026) | `scm_upload`: 318 orders, 8,854 open lines, **8,854 with a warehouse (100%)**. `scm_order_inquiry`: 287 orders, 2,312 open lines, **0 with a warehouse (0%)**. |
| SUPERSEDED: "8,011 of 16,879 lines have no location" | Counted closed lines too, so it understated the AutoCount book's coverage badly. The open-line split above is the figure the location decision (section 11, question 2) rests on. |
| `projects.sales_orders` rows | 16: 15 `blocked`, 1 `published`; **0** with `so_id`, 0 with `autocount_doc_no` |
| `projects.sales_order_lines` rows | 377 |
| `projects.so_supply_decisions` rows | 0 |
| `so_line_allocations.so_line_id` | `NOT NULL`, FK CASCADE to `projects.sales_order_lines` |
| `order_inquiries.project_sales_order_id` | `NOT NULL`, FK CASCADE, unique per sales order |
| `origin/main` at `42a61fd6a` | has neither `fulfilment_planning.py` nor `SOSupplyDecision` |

The open-line warehouse split is the one figure a decision rests on, so here is the query that
produced it. Re-run it rather than trusting the number:

```sql
SELECT so.source_system,
       count(DISTINCT so.id)     AS orders,
       count(*)                  AS open_lines,
       count(sol.warehouse_id)   AS lines_with_warehouse
FROM sales_orders so
JOIN sales_order_lines sol ON sol.sales_order_id = so.id
WHERE so.demand_class = 'project' AND so.status = 'open'
  AND sol.line_status = 'open'
  AND coalesce(sol.purchasing_status, '') <> 'covered'
  AND greatest(coalesce(sol.qty_required, sol.qty_ordered) - coalesce(sol.qty_delivered, 0), 0) > 0
GROUP BY so.source_system;
```

The `WHERE` is `is_open_demand()` written out, plus the header predicate of section 3, which is why
it may be compared with the netting engine's own counts.

---

## 13. The multi-order planning board

**Status of this section:** DESIGN, awaiting the captain. Sections 0 to 12 are approved and are not
changed by it: the per-order sheet stays exactly as it is, and the board sits ABOVE it as a second
way in. Nothing in section 13 is built until this section is confirmed.

### 13.1 Journey (before any grid)

**Actor:** the same Customer Service person, in the same place. **Arrives from:** the worklist,
having ticked more than one order.

**What the system already knows before CS does anything:** everything section 0 lists, plus, for
every selected order, each open line's product, still-owed quantity, required date and fulfilment
location. Nothing new is asked for and no new upload exists.

1. **CS ticks the orders to plan together on the worklist** and presses **Plan together (N)**. The
   worklist is already filtered and sorted by the work that is due, so the tick is a confirmation of
   a set CS can see, not a query CS has to compose.
2. **The board opens: dates across the top, products down the side.** A cell is the quantity of that
   product owed by that date, summed across every selected order. This is the answer to "what are
   the products to be fulfilled, across the dates".
3. **The cell states where it would come from before CS opens anything**: a compact source strip
   under the quantity ("BRW-BB 366 · BRW-IB 216", or "Buy 140"), so the board answers "where will I
   need to source to fulfil" at a glance rather than only on click.
4. **CS clicks a cell and gets the breakdown table**: one row per contributing sales-order line, with
   sales order, customer, project, quantity, fulfilment location, and the proposed composition for
   that row (Reserve at a location / incoming SPO with its date / Buy), each with the reason its rule
   wrote. This is the same explanation the per-line card already owes - the captain's screenshot,
   "23 open = 0 incoming + 0 reserve + 0 borrow + 23 buy" - restated per contributing order.
5. **CS approves, amends or rejects, per row or for the whole cell.** Amending a row's Reserve moves
   the difference into that row's Buy and asks for a reason, exactly as the per-line card does today.
6. **CS commits.** The commit is still per sales order and still atomic (13.4). The board says which
   orders are now fully decided and confirms those; an order the board has only half-decided is
   named as such and is not confirmed.
7. **Purchasing is handed the same Buy-only rows it is handed today.** The board changes what CS
   looks at, not what purchasing consumes.

**Decisions asked of the user:** which orders (step 1), and the composition (step 5, pre-proposed).
Still two. The board does not add a third.

### 13.2 How the orders are selected

**Recommendation: explicit multi-select on the worklist, with the existing filters as the way to
make that selection fast.** Checkbox column, a "Plan together (N)" button in the toolbar, selection
capped at **50 orders** with the cap stated when it bites.

Why, and why not the alternatives:

- **Not "plan everything due in a window" with no explicit selection.** The board writes decisions.
  A decision set the user did not compose is a set they cannot audit, and the first time an order
  they had never looked at gets Reserve taken off it, the feature has done something behind their
  back. The captain's words are "the user might want to plan against multiple sales order" - a
  choice, made by a person.
- **Not a customer/project filter as the selection mechanism.** It is a fine way to NARROW (and the
  worklist already searches customer, project string and area group), but a filter is a query, not a
  set: it silently changes underneath the board when the next upload lands, and the board would then
  be planning something other than what CS ticked. Filter to find, tick to select.
- **The cap is not arbitrary.** Section 13.9 measures the whole book at 862 distinct products across
  349 distinct required dates. A board of everything is roughly 300,000 cells and is not a screen. A
  bounded selection is what makes the board legible, so the bound is part of the design rather than a
  guard bolted on.

The selection lives in the URL (`?orders=SO391698,SO324265,...` by sales-order number, never by id)
so a board can be linked to and reloaded.

### 13.3 What the date axis is

**Recommendation: bucketed by ISO week by default, switchable to month, never exact dates.** Plus
two special columns that are not buckets at all.

Measured on the live scratch DB (13.9): 11,166 open project lines carry **349 distinct required
dates** but only **114 distinct weeks** and **35 distinct months**, spanning 2022-07-03 to
2030-01-01. Exact-date columns would be hundreds of mostly-blank columns; weeks are the coarsest
bucket that still separates "this week" from "next week", which is the distinction fulfilment
actually turns on.

The two columns that are not buckets:

- **Overdue**, pinned first. Any line whose required date is already past goes here, whatever its
  date. **4,183 of the 11,166 open lines are overdue** - 37 per cent - so this is not an edge case,
  it is the biggest column on the board. Splitting those across their historical weeks would push
  the columns CS can still act on off the right-hand edge behind three years of the past. They are
  all equally late; what matters is what they need now.
- **No date**, pinned last. 63 lines carry no required date. They are neither dropped nor guessed
  into a bucket, because a guessed date is the same class of silent wrong answer as a guessed
  warehouse (section 11, question 2). The column states what it is, and its cells plan normally.

A bucket's header shows the week's start date, formatted through `formatDateInMalaysia`, with the
exact dates inside it available on the cell's breakdown rows (which carry the line's real
`required_date`). Bucketing is a display choice; nothing is ever stored bucketed.

### 13.4 Who owns the decision: the board is a LENS

**Recommendation: the board is a lens. The decision stays where Stage 1C put it, and the board
writes no new decision object.** I agree with the prior, and reading Stage 1C makes the case
stronger than "purchasing consumes it per line":

- `projects.so_supply_decisions` is keyed **per sales order**, and the DB enforces it: partial unique
  index `uq_so_supply_decisions_active` on `(project_sales_order_id) WHERE state = 'active'`
  (STAGE1C section 2). One active decision per order, by construction.
- Confirmation is **atomic across the whole order** (AC-C01): every line commits or none does, and a
  refusal names each failing line.
- A board **cell cuts across orders**. So a cell can never be a unit of persistence without either
  dropping that unique index or making confirmation per line - which is a rewrite of the lane that
  shipped, and it would also break AC-A03 (one whole-order state, never a per-line one).

So: **the cell is where CS decides; the order is still what commits.** Cell-level approve/amend/
reject writes into a **cross-order draft** held by the board, not into a per-line workflow status,
and not into any new table. When every line of a given order has been decided in the draft, that
order is confirmable and the board offers to confirm it through the existing per-order confirm.

**The honest consequence, stated rather than hidden:** approving one cell will usually leave several
orders only partly decided, because a cell holds one product on one date and an order has many lines
across many dates. The board must therefore show, per selected order, a plain "4 of 12 lines
decided" and a Confirm that is disabled until it reads 12 of 12. This is the one place the board's
shape and the commit's shape genuinely disagree, and no design makes that disappear - it can only be
made visible. **This is the question I would most want the captain to look at**, because the
alternative (per-line confirmation) is available, it is what would let a cell commit on its own, and
it costs the Stage 1C rewrite plus AC-C01 and AC-A03.

Where the draft lives is deliberately left to Phase 2 (client state is enough for Phase 1). If it
needs to survive a reload it becomes a `projects.so_planning_drafts` row keyed on the selection,
which lands on the module purge list and nowhere near the decision tables.

### 13.5 Allocation when free stock cannot cover the cell

This is the genuinely new logic, and today it is a latent race the board makes visible. Verified in
`project_supply_service._free_stock`: free stock nets on-hand minus reserved minus **CONFIRMED**
holds only. Two orders composed separately therefore both see the same free stock and both propose
Reserve against it; whoever confirms first wins and the second is refused at recheck. Nobody sees the
conflict until the refusal. On the board both orders are in the same cell, so it has to be resolved
up front.

**Default rule, applied within a cell, per (product, location):**

1. **Earliest required date first** (the real date on the line, not the bucket). The work that is due
   soonest gets the stock. Overdue lines sort by their own date, so the latest-overdue is served
   first.
2. **Then `sales_order_lines.priority`** when it is set, high before medium before low. Measured:
   **14 rows of 90,548 carry a priority** (8 high, 3 medium, 3 low). It is therefore a genuine
   override where somebody has bothered to state one, and it must NOT be the primary key, because
   for 99.98 per cent of lines it would decide nothing.
3. **Then sales-order number ascending**, so the rule is TOTAL and reproducible. The same tie-break
   the worklist already uses (AC-FP04); a non-total rule gives a different answer on each refresh.

Whatever the rule cannot cover becomes **Buy** on the losing rows, with the reason naming why
("Free stock at BRW-BB went to SO324265, required 2024-12-03; the residual is bought").

**Explicitly NOT pro-rata.** Splitting 100 free units across five orders needing 100 each gives five
short deliveries instead of one complete one and four honest Buys. Short-shipping everybody is the
worst available outcome, and it is what an "even split" quietly chooses.

**How the user overrides:** in the breakdown table, per row, by editing the Reserve quantity. The
board recomputes every other row in that cell against the same free pool and moves the difference to
Buy. An override is recorded with a reason, the same mandatory-reason shape Borrow already uses
(AC-B09), so the decision snapshot says a person chose this and why.

### 13.6 Is cell-level approve atomic?

**No, and it must not claim to be.** Per 13.4 the atomic unit is the order. A cell approve stages
every contributing row in that cell into the draft; nothing is written to the database at that
moment, so there is nothing to be atomic about yet. That is what lets a cell hold rows from six
orders without inventing a six-order transaction.

At commit the board runs **one existing per-order confirmation per order**, each atomic in itself.
Partial refusal reports **per order**: the orders that committed stay committed, the ones that
refused are listed with their `failing_lines` (line number and item code, never an id), and the board
keeps the draft for the refused ones so CS fixes and re-commits only those. Confirming five orders
where one is stale must not roll back the four good ones - they are five separate decisions about
five separate customer commitments, and tying them together would create a cross-order atomicity
this system does not otherwise have and cannot honour.

### 13.7 Locations in a cell

The location is the core sales-order line's own warehouse (section 11, question 2), so **one cell can
legitimately span several source locations**, and this is common rather than exotic: measured across
the eight fixture orders, `WESERP10B` is owed by four different orders out of both BRW-BB and BRW-IB
(13.9).

- The **cell** shows the total, then a source strip listing each location with its share
  ("BRW-BB 366 · BRW-IB 216"), truncated with a `title` when it does not fit.
- The **breakdown table** carries the location per row, because that is where it is a fact.
- **Allocation is computed per (product, location)**, never across locations: free stock at BRW-IB
  cannot cover a line that must be fulfilled from BRW-BB. Moving stock between locations is a
  transfer, which is M9's job and a non-goal here (13.8).
- A contributing row whose sales-order line states **no location** renders the blocked state already
  designed (AC-FP16): it contributes its quantity to the cell total so the demand is not hidden, is
  marked as unplannable, links to its SCM sales order, and blocks its own order's confirm. The cell
  shows "1 line needs a location" rather than silently under-sourcing.

### 13.8 What the board does NOT do

- **It does not replace the per-order sheet.** The sheet stays as the way to plan one order end to
  end, and remains the only place the reconciliation card lives.
- **It does not create a cross-order decision object**, table or status (13.4).
- **It does not move stock between locations.** Transfers are `PLAN-scm-m9-stock-allocation-transfer`.
- **It does not re-open the fulfilment-location question.** No location is ever chosen on the board.
- **It does not plan the whole book.** Selection is explicit and bounded (13.2).
- **It does not introduce a per-line workflow state.** AC-A03 stands; the draft is a working set.
- **It does not change what purchasing receives.** Buy-only rows, per confirmed line, unchanged.

**ACs superseded: none.** Every criterion in Groups A to E stands unchanged, which is the test that
this is an addition rather than a redesign. The board's own criteria are new (Group F, to be written
into section 1 when this section is confirmed, as AC-FP28 onward).

### 13.9 Facts measured for this section

Live scratch DB `sorento_scm_e2e_stack`, 18 August 2026, open lines of open project-class orders:

| Fact | Value | Why it decides something |
|---|---|---|
| Open project lines | 11,166 | The board's population. |
| Distinct required dates | 349 | Exact-date columns are not a screen (13.3). |
| Distinct ISO weeks | 114 | The default bucket. |
| Distinct months | 35 | The coarse bucket. |
| Distinct products | 862 | With 349 dates, a whole-book board is ~300,000 cells (13.2). |
| Required date range | 2022-07-03 to 2030-01-01 | Seven and a half years wide; the past has to be collapsed. |
| **Overdue lines** | **4,183 of 11,166 (37%)** | The Overdue column is the biggest one on the board (13.3). |
| Lines with no required date | 63 | Small, and still never dropped or guessed (13.3). |
| `sales_order_lines.priority` populated | **14 of 90,548** (8 high, 3 medium, 3 low) | Priority cannot be the primary allocation key (13.5). |
| Free stock nets confirmed holds only | `project_supply_service._free_stock` | Two unconfirmed orders both propose the same stock today (13.5). |
| Products shared across the 8 fixture orders | e.g. `WESERP10B` in 4 orders over BRW-BB + BRW-IB (1,774), `CKS1050` and `CKSW015` in 4 each (517), `SRTSC03-ABS-NL` in 2 where one states no location | The mock aggregates visibly, and covers the multi-location and blocked cells (13.7). |

Reproduce the axis figures with:

```sql
WITH ol AS (
  SELECT sol.required_date, sol.product_id
  FROM sales_orders so JOIN sales_order_lines sol ON sol.sales_order_id = so.id
  WHERE so.demand_class = 'project' AND so.status = 'open' AND sol.line_status = 'open'
    AND coalesce(sol.purchasing_status, '') <> 'covered'
    AND greatest(coalesce(sol.qty_required, sol.qty_ordered) - coalesce(sol.qty_delivered, 0), 0) > 0)
SELECT count(*), count(DISTINCT required_date), count(DISTINCT date_trunc('week', required_date)),
       count(DISTINCT date_trunc('month', required_date)),
       count(*) FILTER (WHERE required_date IS NULL),
       count(*) FILTER (WHERE required_date < CURRENT_DATE),
       count(DISTINCT product_id)
FROM ol;
```

### 13.10 Frontend shape

The board is the **delivery-schedule matrix idiom**, which is what the captain is pointing at:
`app/(protected)/project-sales/[projectId]/delivery-schedules/components/DeliveryScheduleMatrix.tsx`.
That lane's transposition **has landed** and was read before this section was finalised: its
docstring now says "The schedule, TRANSPOSED: dates across the top, products down the side ... it now
reads the way people ask about it instead". That is exactly the board's axis, so the board matches it
rather than inventing a second grid language, and none of its files are edited here.

One vocabulary warning taken from it: in that lane a `column` in the code and the API means a
PRODUCT (the customer's own word for the strip on their printed sheet) even though a product is now a
ROW on screen, and they deliberately did not rename it. The board has no such inherited API, so it
names its axes for what they are on screen - `dateBuckets` across, `productRows` down - and must not
borrow that file's `ColumnState` naming, or the two grids will use the same word for opposite things.

That file is also the precedent for the one convention the board knowingly departs from. The
code-review hard-fail list forbids a hand-rolled table and requires the shared `DataGrid`, and the
matrix documents why it is not one: **here the COLUMNS ARE DATA** - there are as many as there are
date buckets, and no column config, sort or resize applies to them. The board is the same shape and
takes the same carve-out, with the same three obligations the matrix already meets:

- the whole table scrolls **inside its own container** (`overflow-auto`, `max-h`,
  `overscroll-x-contain`), so the page body never scrolls sideways;
- the product column is `sticky left-0` and the header row `sticky top-0`, with the corner cell on a
  higher layer than either, and every pinned cell **opaque** (`color-mix(in oklab, ...)`, never an
  alpha token, which Tailwind v4 resolves to `oklch(...)` and the browser drops);
- fixed cell widths on a `w-max` table, never `table-fixed`, which overlaps its columns as soon as
  content exceeds the declared width.

**A blank cell is not a zero**: it means no selected order owes that product by that date. It renders
blank and stays blank, exactly as the schedule matrix's blank means "this phase does not take this
product".

The worklist gains a selection column and a "Plan together (N)" toolbar action; the board is a route
under the same screen so it can be linked (13.2). The breakdown is a shared `DataGrid` - there the
columns are fixed and known (sales order, customer, project, quantity, location, composition,
decision), which is exactly when `DataGrid` is right.
