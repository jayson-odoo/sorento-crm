# Stage 1B slice note: AutoCount upload and reconciliation

**Status:** DONE, 17 August 2026 (Group A delivered; PR stacked on #204). Branch `fm/scm-stage1b-reconciliation`, stacked on
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
   customer PO, area group, review state pill. Nothing states when reconciliation last ran:
   this slice stores no such column, so the sheet would be printing a moment it does not have.
   **Reconciliation card:** core SO link (linked SO number, or why not), lines linked `n / m`,
   and the exception list - each entry names the Project line number and item code and one
   human-readable reason. Actions: **Re-run reconciliation** (idempotent), and a link to the
   order's AutoCount upload screen (`/project-sales/{projectId}/sales-orders/{psoId}/divergence`)
   when no document has been uploaded yet.
   **Lines table** (`DataGrid`, fixed layout): line no, item code, description, qty + UOM,
   required date, location, core line (Linked / Missing / Ambiguous (k candidates) /
   Duplicate).
   Empty states are explicit: no lines, no core SO yet, no exceptions ("every line is linked").
3. **CS resolves an exception outside the sheet** (upload the AutoCount document on the
   order's divergence screen, or the weekly outstanding SO book, or answer a divergence row) and
   presses Re-run. When the last exception clears the pill flips to **Needs CS review**.
4. **End state:** the whole SO reads Needs CS review in the list row, the SO detail header, and
   the side sheet; every Project line carries `core_sales_order_line_id`; no purchase
   requirement was created (AC-A04). Stage 1C picks up from here.

The upload itself is the existing P8a route (`POST /project-sales/sales-orders/ingest-file`
and its JSON twin), which already adopts the document number and links `so_id`
(`ProjectSOIngestService.reconcile_core_order`, public since this slice so the reconciliation
service can attempt the header link on a re-run). This slice adds the line half and the review
state on top of it; it introduces no second upload path.

## 2. Line mapping rule (deterministic, AC-A02)

Given the Project SO's `so_id`, the candidate core lines are `public.sales_order_lines` rows with
`sales_order_id = so_id`, `line_status <> 'closed'`, and not already held by a
`projects.sales_order_lines` row of ANOTHER Project SO. Links are stable: a Project line whose
existing `core_sales_order_line_id` still points at one of those candidates keeps it and that
core line is taken. The stability pass keeps an existing link on candidacy alone - it does not
re-check the product or the date, so a link a person has already read never reshuffles under
them. The remaining Project lines are mapped against the remaining core lines
inside each `product_id` group, in the same two passes `app/services/scm/outstanding_diff.py`
already uses to identify a line across weekly uploads:

1. exact required-date match pairs first (`sales_order_lines.required_date` against
   `projects.sales_order_lines.delivery_date`);
2. what is left pairs in date order (both sides sorted by date, then zipped).

Outcomes per Project line: **linked** (exactly one core line), **missing** (no candidate left),
**ambiguous** (in pass 1 the same product and date has more than one Project line or more than
one core line, so no pair is unique; nothing is written for them), **duplicate** (the core line
for this item is already linked to another Project SO, named by its provisional reference and
line number - two sales orders adopted the same AutoCount document, and one of them is wrong).
`uq_projects_so_line_core_line` allows exactly one holder per core line, so `duplicate` is the
outcome that keeps a second Project SO reporting the conflict rather than dying on the index.

A missing line says which of the three it is, and each sentence is one CS can go and
check: the document has no line for the item at all; it has fewer lines for the item than
this sales order does; or it has as many and they are all accounted for by other lines on
this sales order (a pass-1 ambiguity spends its core lines, so the line left over is not
owed a "fewer lines" it could disprove by counting).

A core line no Project line takes is a **surplus** exception naming its item code (the AutoCount document has a line the
Project SO does not - answer it in AutoCount Differences). A previously linked core line that
is now closed or on another SO makes that Project line **missing** again, and its reason
names the core line's current state ("Its previous core line is now closed") rather than
the clearing: `evaluate` is a pure read, so a message about a link having been cleared
would describe a write the reader has not asked for. That reason also wins over the
`duplicate` fallback, because a line that HELD a core line is not told about a core line
it never touched.

Header outcomes: **no document** (`autocount_doc_no` is null - upload it), **no core SO**
(`so_id` is null after `reconcile_core_order` - the outstanding SO book has not carried this
number yet, OR the row `so_id` names is not visible under this company's scope), **linked**.
`so_id` is what decides **linked**, ahead of the document number: the review state turns on the
header outcome, so an order carrying a core SO must not read "nothing uploaded yet" beside a
Needs CS review pill.

Review state (derived, never a stored column in this slice):

```text
needs_cs_review   iff the header is linked AND lines_total > 0 AND every line linked
                  AND no surplus
awaiting_reconciliation  otherwise
```

Only a published or amended order has a review state at all. A draft or a blocked order is
reconciled against nothing, so its list row and its detail carry `review_state: null` and
`exception_count: 0` rather than an "awaiting reconciliation" it has not earned.

Stage 1C adds `confirmed` on top of this when an active `so_supply_decisions` row exists.

Every exception is reported by Project line number and item code, or by item code alone for a
surplus core line. No UUID appears in a message.

## 3. API contract (Phase 1 mock is built against this; Phase 2 must match)

All under the existing `/api/v1/project-sales` router, permission `projects.projects.view` for
reads and `projects.projects.edit` for the rerun.

```text
GET  /project-sales/fulfilment-planning?page&limit&query&review_state&project_id
     -> ListResponse<FulfilmentPlanningRow>
     query matches provisional ref, AutoCount doc no, area group, project code,
       project title and customer name (everything the row prints)
     review_state is a closed set: awaiting_reconciliation | needs_cs_review,
       anything else is a 422

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
            stock_location?, link: 'linked' | 'missing' | 'ambiguous' | 'duplicate',
            candidate_count: number, reason: string }],
  exceptions: [{ line_no?: number, item_code?: string, kind: 'header' | 'missing' |
                 'ambiguous' | 'duplicate' | 'surplus', message: string }],
  lines_total, lines_linked
}
```

`ReconciliationSummary.review_state` is NULLABLE for the same reason the list row and
the detail are (section 2): an order that is not published or amended is reconciled
against nothing. `POST .../reconcile` on one of those is a READ - it answers with the
same summary the GET does and writes no line links, because linking a draft to a core
sales order it has not been published against would be the system deciding on its own.

An exception's `message` carries the reason ALONE. The screen prints the subject itself from
`line_no` and `item_code` ("Line 2, SRT501-CP"), so a message that repeats the subject renders
the same fact twice.

`POST .../reconcile` also performs the HEADER link when `so_id` is still null and a document
number is known: it calls `ProjectSOIngestService.reconcile_core_order`, so a re-run may
renumber a sheet-created provisional core row or retire it in favour of the outstanding book's,
exactly as the P8a ingest does. That is why the re-run takes `projects.projects.edit` and the
read does not.

The shape carries no `reconciled_at`. It was added during Phase 1 and removed in the Phase 2
review: nothing in this slice stores when reconciliation last ran, so the only honest value was
"now" on a write and null on a read, which is a timestamp about the request rather than about
the order.

`ProjectSalesOrderRow` and `ProjectSalesOrderDetail` (existing) gain `review_state` (nullable,
see section 2) and `exception_count` so the project's SO list and the SO detail header read the
same state.

The Phase 1 mock lived behind the existing `NEXT_PUBLIC_PROJECT_SO_MOCK=1` switch in
`app/(protected)/project-sales/_shared/services/` and covered a Needs CS review SO, an SO with a
missing line and a surplus core line, an SO with an ambiguous pair, an SO with no document, an
empty list and a failed request. It was deleted when Phase 2 landed: the component tests carry
their own fixtures, and a second source of these shapes drifts from the real one.

## 4. Backend shape (Phase 2)

- `app/services/project_so_reconciliation_service.py`: `evaluate(order)` (pure read, returns
  the summary and the writes it would make), `reconcile(order)` (attempt the header link when
  `so_id` is null, then evaluate + persist links + clear stale ones + flush),
  `review_states_for(order_ids)` (one grouped query for list rows, published and amended orders
  only - a draft carries no review state at all, and its row and detail read null).
- `ProjectSOIngestService.ingest` calls `reconcile` right after `reconcile_core_order` when
  `so_id` is set, so the P8a upload lands with the lines linked in the same transaction.
  Best effort, inside a SAVEPOINT: adopting the document number and recording the
  divergence are what the upload was for, so a line write that loses a race on
  `uq_projects_so_line_core_line` is logged as a warning and the upload still lands (the
  lines are one Re-run away). Without the savepoint an `IntegrityError` would leave the
  transaction unusable and take the divergence record down with it.
- No new table, no migration, no new setting. `derive_for_sales_order` is not called anywhere
  on this path (AC-A04).
- AC-A04 read side, pinned rather than built: `app/services/scm/demand.py` already counts a
  Project-class core SO only when it is the sheet leg (`PLAN_DEMAND_ORDER_SQL`:
  `demand_class IS DISTINCT FROM 'project' OR demand_origin = 'scm_order_inquiry'`), and
  `projects.order_inquiry_rows` gains no `ORDER` / `RESERVE_AND_ORDER` row from publish, ingest
  or reconcile. The sheet leg staying counted before confirmation is plan section 4's own rule
  ("read only for SOs with no confirmed CS decision"); Stage 2 rebases the Project column onto
  confirmed Buy. The Stage 1B test pins both halves for a reconciled Needs CS review SO.
- Routes in `app/api/v1/projects/fulfilment_planning.py`, mounted ahead of the sales-order
  router for the same reason `divergences` is, with schemas in
  `app/schemas/project_so_reconciliation.py`.

## 5. Tests (Phase 2, TDD)

pytest `tests/test_project_so_reconciliation.py` on Postgres via `tests/_pg_fixture.py`, seeding
its own chain (company, project, PO, Project SO + lines, core SO + lines):

- exact-date pass, date-order pass, missing, ambiguous, duplicate (two Project SOs on one
  core SO, no `IntegrityError`), surplus, stable relink, stale link cleared, closed core line
  ignored, cross-company core SO never linked (through `reconcile`, which is what attempts the
  header link), core SO outside the company scope reported as no core SO;
- review state derivation (AC-A02, AC-A03), only entered when header and all lines link, and
  absent entirely on a draft or blocked order;
- ingest triggers reconciliation (AC-A01);
- zero `order_inquiry_rows` with verb `ORDER` / `RESERVE_AND_ORDER` after reconcile (AC-A04);
- routes: happy, 403 without permission, 404 unknown id, rerun idempotent.

Vitest: list client (rows, pill per state, empty, error), side sheet (header strip read from
the summary, reconciliation card, exceptions, lines table including Duplicate, empty and error
states, rerun action), hook and service (the three documented URLs and their failures).

agent-browser evidence run: sidebar Project Sales -> Fulfilment Planning -> row -> sheet, console
and network checks, 1280x800 and 375x812.

## 6. AC-H03 test report (Group A, Stage 1B)

Measured on 17 August 2026 at the branch head. Backend: Postgres via `tests/_pg_fixture.py`
(`blank_session`, every test seeds its own chain, marker-prefixed). Frontend: Vitest + jsdom.
Browser: headless `agent-browser` 0.27.0, private session `scm-stage1b-reconciliation`,
short-lived stack (backend `uvicorn` on 8121, frontend `npm run dev` on 3021), login with the
`E2E_EMAIL` / `E2E_PASSWORD` pair (legacy alias names in this worktree's `.env.local`), sidebar
clicks from `/`, `get url` before every read.

| AC | Result | Evidence |
|---|---|---|
| AC-A01 accepted demand reaches one review journey | PASS (pytest + browser, sheet half by pytest) | `tests/test_project_so_reconciliation.py::test_ingest_links_so_id_and_every_line_in_the_same_call` (P8a ingest links header and every line in one call, specific core line ids asserted); `tests/test_project_so_reconciliation_more.py::test_ingest_of_a_divergent_document_still_links_the_project_lines`; browser: sidebar Project Sales -> Fulfilment Planning renders and `GET /api/v1/project-sales/fulfilment-planning` 200 (real empty state: every local Project SO is blocked, so no published row exists to open; the sheet and Re-run were exercised against mock in Phase 1 and against pytest routes in Phase 2). No inquiry row is written on the path (see AC-A04). |
| AC-A02 header and line reconciliation is mandatory | PASS (pytest) | `test_project_so_reconciliation.py`: exact-date pass, date-order pass, missing, ambiguous (candidate_count), surplus, duplicate across two Project SOs (no IntegrityError, other Project SO ref and line named), stable relink, stale link cleared, closed lines not candidates, cross-company core SO never linked (`reconcile()` path), header outcomes no_document / no_core_so / linked, `needs_cs_review` only when header and every line link and no surplus or duplicate; messages carry line number and item code, never a UUID (`test_..._no_uuid...`). Routes: `test_project_so_reconciliation_routes.py` GET reconciliation / POST reconcile happy, 403, 404, idempotent rerun. |
| AC-A03 the whole SO has one pre-confirmation state | PASS (pytest + Vitest + browser) | pytest: `review_state` derived per SO, per-line fields never read confirmed / partial / purchasing; drafts and blocked SOs carry `review_state: null` (`_more.py` draft detail, build and regroup rows). Vitest: `FulfilmentPlanningSheet.test.tsx` AC-A03 assertion (no rendered text matches confirmed / partial / purchasing, whole-SO pill reads "Needs CS review"), `ReviewStatePill.test.tsx`, `SalesOrdersPanel.test.tsx` and `SalesOrderDetailClient.test.tsx` pill present / absent. Browser: project PRJ-000002 Sales orders tab rows and PSO-000001 detail header show only the Blocked status pill after the fix (phase2b screenshots at 1280x800 and 375x812), consistent list row <-> detail header. |
| AC-A04 pre-confirmation demand is excluded | PASS (pytest) | `test_project_so_reconciliation.py::test_a_reconciled_needs_cs_review_so_creates_no_order_inquiry_demand_and_stays_excluded`: after ingest + reconcile, zero `projects.order_inquiry_rows` with verb ORDER / RESERVE_AND_ORDER for the SO, and `app.services.scm.demand.is_plan_demand_order` excludes the linked project-class core SO that is not the sheet leg. `derive_for_sales_order` has no caller in `app/`. The legacy sheet leg stays counted before confirmation by plan section 4's own rule; the Project column rebase onto confirmed Buy is Stage 2. |
| AC-G02 / AC-G04 (as they apply to J03) | PASS (Vitest + browser) | Sheet empty states for no lines, no core SO, no exceptions, error + Try again; human-readable identifiers throughout; console and `errors` clean on every screen visited; all `/api/v1/project-sales/*` calls 200. |
| AC-G06 | PASS (pytest) | `test_an_so_of_another_company_never_appears_in_the_list`, `test_a_core_sales_order_outside_the_company_scope_reads_no_core_so`, cross-company header link refused. |
| AC-H02 | PASS | Phase 1 mock (commit `eda1503d0`) preceded any backend code (`bec2f6ab3`); the mock fixtures were deleted when Phase 2 landed. |
| AC-H04 | PASS (review) | No LLM, optimizer, rules engine, second approval, automatic ordering, worklist state or configuration knob; no migration; both reviews confirm nothing from Stage 1C or Stage 2 leaked in. |

Counts at head: backend `tests/test_project_so_reconciliation*.py` all green (see PR body for the
number); frontend `npx vitest run "app/(protected)/project-sales"` all green; `tsc --noEmit`
clean on every Stage 1B file; `tests/test_alembic_revision_ids.py` green with the single head
`373_merge_scm_stage0_1a` (this slice adds no migration).

### Browser evidence runs

**Phase 1 (mock, 17 Aug 2026):** stack FE 3021 (`NEXT_PUBLIC_PROJECT_SO_MOCK=1`) + BE 8121; sidebar
Project Sales -> Fulfilment Planning; five fixture rows opened one by one (needs review,
missing + surplus, ambiguous, no document, request failure), list empty and list error via query
param, Re-run success and warning toasts, review pill on the project's SO list row and SO detail
header; `errors` empty, console clean of app errors; no `/fulfilment-planning` network call (mock
served without a backend); 18 screenshots at 1280x800 and 375x812.

**Phase 2 (real stack, 17 Aug 2026, before and after the review fixes):** login, sidebar Project
Sales -> Fulfilment Planning (`GET /api/v1/project-sales/fulfilment-planning?page=1&limit=25` 200,
real empty state "No published Project SO yet" with the pipeline CTA; typing "PSO" fires exactly
one debounced `...&query=PSO` request); Project Sales -> Pipeline -> PRJ-000002 -> Sales orders tab
(`GET .../projects/{id}/sales-orders` 200; three Blocked rows, no review pill after the fix) ->
PSO-000001 detail (`GET .../sales-orders/{id}` 200, header Blocked only); `errors` empty at every
checkpoint, console only debug / Fast Refresh lines; screenshots at 1280x800 and 375x812. The
sheet + Re-run half could not be reached live because no local Project SO is published and the
run was forbidden from publishing one; that half is covered by the route and service tests above.
Regression guard for the flow is logged in `documentation/backlogs/backlog.md` per the standing
"no new Playwright spec" order.
