# PLAN: Start Plan pre-selects the orders whose inquiries were raised in a window (22 Sep 2026)

Status: BUILT 22 Sep 2026, review in progress; browser AC-RF-9 queued (no slot). Small feature (one endpoint field, one
modal field, no migration, no run change).
UAC: `reorder-plan-raised-filter-acceptance-criteria.md`.
Lane: worktree `../sorento_crm-plan-raised-filter`, branch `feat/reorder-plan-raised-filter`
off `origin/main` d57fd367c. Backend tests on `sorento_buc_ci` via
`SORENTO_ENV_FILE=.env.ci-tests` (export `DATABASE_URL` too); FE vitest through the
symlinked `node_modules`. No stack slot; browser pass queued.

## 1. Journey

Purchasing's weekly routine: CS adds rows to the ORDER INQUIRY book on Wednesday and
Thursday, uploads it, and purchasing plans "the inquiries raised on 17 and 18 Sep with
delivery up to end of October". Today Start Plan (Demand = Project) pre-selects every open
project order with a row in the delivery range, so the buyer has to hand-pick the week's
orders out of hundreds. With an "Inquiries raised from / to" pair the modal pre-selects
exactly the orders that gained a row in that window; the buyer can still add or remove.

## 2. Measured facts (origin/main d57fd367c, DB `sorento_ai_automation_0921`)

- The workbook carries no raise date (owner, 22 Sep). A row's first upload is
  `projects.order_inquiry_rows.created_at`; a re-upload of the same row is skipped as
  `ALREADY_RAISED` (`_restates`), so `created_at` is stable. `order_inquiries.raised_at` is
  the header's first raise and is re-stamped by later confirms, so it is NOT the row's date.
  Rows first uploaded 17-18 Sep on the copy: 436.
- `GET /api/v1/scm/reorder-runs/candidate-orders?from&to` (`reorder_runs.py:503-645`)
  returns one row per open project SO with `rows_total`, `rows_in_range` (delivery range),
  `rows_awaiting`, `first_delivery`, `last_delivery` (`schemas/scm_reorder.py:235`).
- `RunPlanningModal.tsx:174-189` fetches it while Demand = Project (query key includes the
  delivery range) and pre-selects `rows_in_range > 0` until the buyer touches the list
  (`touchedOrdersRef`). Service: `reorder/services/reorderRunService.ts:361`
  `getCandidateOrders({from, to})`. Tests: `RunPlanningModal.test.tsx`,
  `tests/test_reorder_plan_demand_scope.py::test_t9..t11`.
- The run itself is scoped by `so_numbers` only; nothing about the raise window needs to
  reach `create_run` or the run row.

## 3. Rulings (owner, 22 Sep 2026)

- R1: raise date = the row's first upload day in Asia/Kuala_Lumpur (`created_at`, stored
  naive UTC, converted the app-wide way), because the book has none. Meaningful when the
  book is uploaded the day rows are added.
- R2: the window only drives PRE-SELECTION. The list still shows every candidate order; the
  buyer adds or removes as today.

## 4. Slices

- S1 Backend: `candidate-orders` gains `raised_from` / `raised_to` (date, optional, open
  bounds like `from`/`to`) and a new `rows_raised_in_window: int` on `CandidateOrder`,
  counted over the SAME candidate rows (`count(*) FILTER (WHERE created_at::date BETWEEN)`;
  an omitted bound is open, both omitted = every row counts, same shape as `rows_in_range`).
  `candidate_rows` needs `oir.created_at` added to both legs. No new query, no paging.
- S2 Frontend: `RunPlanningModal` gains "Inquiries raised" From / To date inputs under the
  delivery range, shown only while Demand = Project, helper "Empty = any raise date". Both
  ride into `getCandidateOrders({from, to, raised_from, raised_to})` and the query key.
  Pre-selection becomes `rows_in_range > 0 && rows_raised_in_window > 0` (with no raise
  window every row counts, so behaviour is unchanged). The picker option DESCRIPTION
  appends "raised N" only when a window is set - the accessible name (the option label)
  stays stable either way. `touchedOrdersRef` semantics unchanged.
- S3 Service: `getCandidateOrders` passes the two new params through `buildDataGridParams`
  or the existing param builder used there (no hand-rolled URLSearchParams).

## 5. Test list (tester first)

Backend (`tests/test_reorder_plan_demand_scope.py`, beside t9-t11):
- Two SOs, rows created 17 Sep and 20 Sep (set `created_at` explicitly): `raised_from=
  2026-09-17&raised_to=2026-09-18` -> first SO `rows_raised_in_window` 1, second 0; both
  still listed; `rows_in_range` unchanged.
- No raise bounds -> `rows_raised_in_window == rows_total` for both.
- Open lower bound (`raised_to` only) counts everything up to it.
- `response_model` carries the field (assert it in the JSON).
Frontend (`RunPlanningModal.test.tsx`):
- With Demand = Project and a raise window typed, pre-selected orders are exactly those with
  `rows_in_range > 0 && rows_raised_in_window > 0`.
- Without a window, pre-selection unchanged from today (mock returns
  `rows_raised_in_window == rows_total`).
- The inputs are hidden while Demand is Dealer or empty.
- Service test: params serialised as `raised_from` / `raised_to`.

## 6. Out of scope

Storing the raise window on the run; a raise-date column on the plan header; the green
"took from stock" rows (separate lane on #1120).
