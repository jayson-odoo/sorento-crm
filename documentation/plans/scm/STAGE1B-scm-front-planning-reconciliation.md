# Stage 1B slice note: AutoCount upload and reconciliation

**Status:** IN PROGRESS, 17 August 2026. Branch `fm/scm-stage1b-reconciliation`, stacked on
`fm/scm-stage0-1a-land` (PR #204).

**Contract:** `PLAN-scm-front-planning.md` section 7 "Stage 1B", sections 3.1 and 4, and
`UAC-scm-front-planning.md` Group A (AC-A01 to AC-A04). This note is the slice detail the coder
and tester work from; where it and the plan disagree, the plan wins.

**Not in this slice:** suggestions, Reserve / Borrow / Buy, hot-selling, atomic confirmation,
revision supersession, Buy-only inquiry rows (Stage 1C); channel breakdown and Product grain
(Stage 2).

## 1. Journey (J03, this slice)

Actor: Customer Service. Arrives from the sidebar: **Project Sales -> Fulfilment Planning**.

What the system already knows: every published or amended Project SO, its provisional reference,
the AutoCount document number the P8a upload adopted (`autocount_doc_no`), the core `sales_orders`
row that carries that number (`so_id`, from the outstanding SO book or the renumbered sheet row),
and the core `sales_order_lines` under it (product, quantity, required date, warehouse).

1. **First screen: Fulfilment Planning list.** One row per published or amended Project SO
   across projects: project, Project SO reference, AutoCount doc no, customer, customer PO,
   area group, lines, and one **review state** pill for the whole SO. Two values in this slice:
   - **Awaiting reconciliation** - the header or at least one line is not yet uniquely linked
     (the pill carries the count: "3 exceptions").
   - **Needs CS review** - header linked and every line has exactly one core line. Entered only
     here, never earlier (plan 7, AC-A02).
   No line-level state exists anywhere; nothing reads "partially confirmed", "confirmed" or
   "purchasing-ready" (AC-A03).
2. **CS opens a row -> the side sheet** (`Sheet` from `@/components/ui/sheet`, right side).
   Header strip: Project SO reference, AutoCount doc no (or "not uploaded"), project, customer,
   customer PO, area group, review state pill, "Reconciled at" when known.
   **Reconciliation card:** core SO link (linked SO number, or why not), lines linked `n / m`,
   and the exception list - each entry names the Project line number and item code and one
   human-readable reason. Actions: **Re-run reconciliation** (idempotent), and a link to the
   order's AutoCount upload screen (`/project-sales/{projectId}/sales-orders/{psoId}/divergence`)
   when no document has been uploaded yet.
   **Lines table** (`DataGrid`, fixed layout): line no, item code, description, qty + UOM,
   required date, location, core line (Linked / Missing / Ambiguous (k candidates)).
   Empty states are explicit: no lines, no core SO yet, no exceptions ("every line is linked").
3. **CS resolves an exception outside the sheet** (upload the AutoCount document on the
   order's divergence screen, or the weekly outstanding SO book, or answer a divergence row) and
   presses Re-run. When the last exception clears the pill flips to **Needs CS review**.
4. **End state:** the whole SO reads Needs CS review in the list row, the SO detail header, and
   the side sheet; every Project line carries `core_sales_order_line_id`; no purchase
   requirement was created (AC-A04). Stage 1C picks up from here.

The upload itself is the existing P8a route (`POST /project-sales/sales-orders/ingest-file`
and its JSON twin), which already adopts the document number and links `so_id`
(`ProjectSOIngestService._reconcile_core_order`). This slice adds the line half and the review
state on top of it; it introduces no second upload path.

## 2. Line mapping rule (deterministic, AC-A02)

Given the Project SO's `so_id`, the candidate core lines are `public.sales_order_lines` rows with
`sales_order_id = so_id` and `line_status <> 'closed'`. Links are stable: a Project line whose
existing `core_sales_order_line_id` still points at one of those candidates keeps it and that
core line is taken. The remaining Project lines are mapped against the remaining core lines
inside each `product_id` group, in the same two passes `app/services/scm/outstanding_diff.py`
already uses to identify a line across weekly uploads:

1. exact required-date match pairs first (`sales_order_lines.required_date` against
   `projects.sales_order_lines.delivery_date`);
2. what is left pairs in date order (both sides sorted by date, then zipped).

Outcomes per Project line: **linked** (exactly one core line), **missing** (no candidate left),
**ambiguous** (in pass 1 the same product and date has more than one Project line or more than
one core line, so no pair is unique; nothing is written for them). A core line no Project line
takes is a **surplus** exception naming its item code (the AutoCount document has a line the
Project SO does not - answer it in AutoCount Differences). A previously linked core line that
is now closed or on another SO makes that Project line **missing** again (the stale link is
cleared).

Header outcomes: **no document** (`autocount_doc_no` is null - upload it), **no core SO**
(`so_id` is null after `_reconcile_core_order` - the outstanding SO book has not carried this
number yet), **linked**.

Review state (derived, never a stored column in this slice):

```text
needs_cs_review   iff so_id is set AND lines_total > 0 AND every line linked AND no surplus
awaiting_reconciliation  otherwise
```

Stage 1C adds `confirmed` on top of this when an active `so_supply_decisions` row exists.

Every exception is reported by Project line number and item code, or by item code alone for a
surplus core line. No UUID appears in a message.

## 3. API contract (Phase 1 mock is built against this; Phase 2 must match)

All under the existing `/api/v1/project-sales` router, permission `projects.projects.view` for
reads and `projects.projects.edit` for the rerun.

```text
GET  /project-sales/fulfilment-planning?page&limit&query&review_state&project_id
     -> ListResponse<FulfilmentPlanningRow>

FulfilmentPlanningRow {
  id, provisional_ref, autocount_doc_no?, project_id, project_code, project_name,
  customer_name?, po_number?, area_group?, status,           // status = existing SO status
  line_count, lines_linked, exception_count,
  review_state: 'awaiting_reconciliation' | 'needs_cs_review',
  updated_at?
}

GET  /project-sales/sales-orders/{pso_id}/reconciliation -> ReconciliationSummary
POST /project-sales/sales-orders/{pso_id}/reconcile     -> ReconciliationSummary (after writing)

ReconciliationSummary {
  project_sales_order_id, provisional_ref, autocount_doc_no?, project_id, project_code,
  project_name, customer_name?, po_number?, area_group?, status,
  review_state,
  header: { outcome: 'no_document' | 'no_core_so' | 'linked', core_so_number?: string,
            reason: string },
  lines: [{ id, line_no, product_code?, description?, qty, uom?, delivery_date?,
            stock_location?, link: 'linked' | 'missing' | 'ambiguous',
            candidate_count: number, reason: string }],
  exceptions: [{ line_no?: number, item_code?: string, kind: 'header' | 'missing' |
                 'ambiguous' | 'surplus', message: string }],
  lines_total, lines_linked
}
```

`ProjectSalesOrderRow` and `ProjectSalesOrderDetail` (existing) gain `review_state` and
`exception_count` so the project's SO list and the SO detail header read the same state.

The mock lives behind the existing `NEXT_PUBLIC_PROJECT_SO_MOCK=1` switch in
`app/(protected)/project-sales/_shared/services/`, and covers: a Needs CS review SO, an SO with a
missing line and a surplus core line, an SO with an ambiguous pair, an SO with no document, an
empty list, and a failed request.

## 4. Backend shape (Phase 2)

- `app/services/project_so_reconciliation_service.py`: `evaluate(order)` (pure read, returns
  the summary and the writes it would make), `reconcile(order)` (evaluate + persist links + clear
  stale ones + flush), `review_states_for(order_ids)` (one grouped query for list rows).
- `ProjectSOIngestService.ingest` calls `reconcile` right after `_reconcile_core_order` when
  `so_id` is set, so the P8a upload lands with the lines linked in the same transaction.
- No new table, no migration, no new setting. `derive_for_sales_order` is not called anywhere
  on this path (AC-A04).
- AC-A04 read side, pinned rather than built: `app/services/scm/demand.py` already counts a
  Project-class core SO only when it is the sheet leg (`PLAN_DEMAND_ORDER_SQL`:
  `demand_class IS DISTINCT FROM 'project' OR demand_origin = 'scm_order_inquiry'`), and
  `projects.order_inquiry_rows` gains no `ORDER` / `RESERVE_AND_ORDER` row from publish, ingest
  or reconcile. The sheet leg staying counted before confirmation is plan section 4's own rule
  ("read only for SOs with no confirmed CS decision"); Stage 2 rebases the Project column onto
  confirmed Buy. The Stage 1B test pins both halves for a reconciled Needs CS review SO.
- Routes in `app/api/v1/projects/sales_orders.py` (or a sibling module mounted the same way).

## 5. Tests (Phase 2, TDD)

pytest `tests/test_project_so_reconciliation.py` on Postgres via `tests/_pg_fixture.py`, seeding
its own chain (company, project, PO, Project SO + lines, core SO + lines):

- exact-date pass, date-order pass, missing, ambiguous, surplus, stable relink, stale link
  cleared, closed core line ignored, cross-company core SO never linked;
- review state derivation (AC-A02, AC-A03), only entered when header and all lines link;
- ingest triggers reconciliation (AC-A01);
- zero `order_inquiry_rows` with verb `ORDER` / `RESERVE_AND_ORDER` after reconcile (AC-A04);
- routes: happy, 403 without permission, 404 unknown id, rerun idempotent.

Vitest: list client (rows, pill per state, empty, error), side sheet (header strip,
reconciliation card, exceptions, lines table, empty and error states, rerun action), hook and
service (mock and real paths).

agent-browser evidence run: sidebar Project Sales -> Fulfilment Planning -> row -> sheet, console
and network checks, 1280x800 and 375x812.

## 6. AC-H03 test report

Filled at the end of the slice.
