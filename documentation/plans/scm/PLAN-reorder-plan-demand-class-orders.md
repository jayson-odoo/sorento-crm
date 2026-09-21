# PLAN: Start Plan scoped by demand class and by sales order (21 Sep 2026)

Status: BUILT 21 Sep 2026, Phase 3 fix round 1 folded; browser pass pending. Feature
track (one seam plus a 2-column migration plus one list endpoint; too wide for the small
fix track because of the migration and the browser pass).
UAC: `reorder-plan-demand-class-orders-acceptance-criteria.md`.
Lane: worktree `../sorento_crm-plan-orders`, branch `feat/reorder-plan-demand-class-orders`
off `origin/main` cc6c09f19. Stack slot :3086 / :8086 on DB `sorento_ai_automation_0921`
(prod copy of 21 Sep; the run only INSERTs `scm.reorder_run*` rows). Tests on `sorento_ci`
via `SORENTO_ENV_FILE=.env.ci-tests`.

## 1. Journey

Tomorrow (22 Sep) purchasing plans the immediate project orders from the weekly ORDER
INQUIRY sheet, delivery dates Aug to Oct. The owner opens Start Plan, picks **Demand =
Project**, From = 01/08/2026, To = 31/10/2026, and the modal lists the project sales orders
the plan is about to count. The list must tally with the sheet; where it does not, the
owner deselects an SO that should not be bought for, or adds one the range missed, before
pressing Start Plan. Dealer (retail) planning stays as it is today: pick Demand = Dealer,
a range, done; no order list.

## 2. Measured facts (main 170d6ece3, DB `sorento_ai_automation_0921`)

- Demand is gathered by `demand.horizon_committed_select_sql()` (`demand.py:623-812`),
  three legs in one UNION: retail = `sales_order_lines.required_date` where
  `so.demand_class IS DISTINCT FROM 'project'`; confirmed project + form project =
  `projects.order_inquiry_rows.delivery_date`, `ack_state IN ('acknowledged','changed')`.
  The run binds `:horizon` / `:horizon_start` in `_planning_rows`
  (`reorder_run_service.py:885-888`) and again in `_apply_project_supply_reduction` (622)
  and `_plan_per_warehouse` (658). The demand drill mirrors the predicates in
  `demand_breakdown_service.py:266-290, 545, 570`, reading the window off
  `scm.reorder_run`.
- `demand_class` vocabulary is closed: `project` | `retail` (`demand_class.py:33-42`).
  "Dealer" is retail. A NULL class reads as retail.
- Every open OI row resolves to ONE core sales order:
  `oir.order_inquiry_id -> projects.order_inquiries.project_sales_order_id ->
  projects.sales_orders.so_id -> sales_orders.id` (5,127 of 5,127 open rows, 321 SOs).
- Open OI rows with `delivery_date IS NULL`: 0. G2 (undated always counts) stays as is;
  nothing to change, nothing to test.
- The sheet's 9 SOs on the prod copy: SO402757 27 rows spanning 07/2026-03/2027;
  SO418869/SO419517/SO420946/SO420955 acked, dates as on the sheet; **SO420374** dated
  02/11 and 04/01/2027 in the CRM but 05/10 + 03/11 on the sheet; **SO420745** (7) and
  **SO421287** (6) all `awaiting`; SO417310 closed.
- `CreateReorderRunRequest` / `ReplanReorderRunRequest` (`scm_reorder.py:31-80`) carry
  `warehouse_codes`, `product_codes`, `plan_horizon_date`, `plan_horizon_start` only. The
  RQ job receives a run id and reads scope off the `scm.reorder_run` row
  (`reorder_run_service.py:170-203`, `610-660`), so a new scope must be stored there.
- No sales order picker exists in the FE; `GET /scm/sales-orders` returns DataGrid rows,
  not `{value,label}` options. `RunPlanningModal.tsx:82-269` holds the four fields.
- `alembic heads` = `523_so_line_no`.

## 3. Rulings (owner, 21 Sep evening)

- R1 Order key = **SO number**, whole SO. Scope is the INTERSECTION of warehouses, products,
  orders and dates: a product outside the product selection does not appear even when it
  is on a chosen SO; a row on a chosen SO outside the date range does not count either.
  Consequence stated to the owner: SO420374 stays out of an Aug-Oct run until its OI
  delivery dates are corrected; adding it from the list does not pull rows dated November.
- R2 Awaiting-ack rows keep the 27 Aug ruling: never bought against. The owner
  acknowledges in OI first. The list shows the awaiting count per SO so this is visible
  before Start.
- R3 Undated rows: no change (0 exist; G2 stands).
- R4 Dealer == retail. Demand select offers `Project` / `Dealer` / `All` (default All =
  today's behaviour, both legs).
- R5 New stack slot, run concurrently with the two live lanes.

## 4. Design (simplest that satisfies the journey)

### Backend

1. Migration `524_reorder_run_demand_scope`: `scm.reorder_run` gains
   `demand_class VARCHAR(16) NULL` (CHECK in `('project','retail')`) and
   `so_numbers JSONB NULL` (list of SO numbers; NULL = no order scope asked for).
   `down_revision = 'ptag_0013_r10'` (main moved past `523_so_line_no` before the lane
   landed; re-parented at merge time). Model columns beside `plan_horizon_start`
   (`scm.py:291`).
2. `CreateReorderRunRequest` and `ReplanReorderRunRequest` gain
   `demand_class: Optional[Literal['project','retail']] = None` and
   `so_numbers: List[str] = []`. Validator: `so_numbers` non-empty requires
   `demand_class == 'project'` (422 otherwise). `create_run` / `replan_run` stamp both on
   the row; the replan route passes them through like the horizon pair.
3. `horizon_committed_select_sql(demand_class=None, so_scoped=False)`: keyword args, no
   new binds unless asked, so every other caller (`container_request_service`,
   `summary_order_service`, `loading_plan_service`) compiles and binds unchanged.
   - `demand_class='project'`: the retail leg is dropped from the UNION.
   - `demand_class='retail'`: both project legs are dropped.
   - `so_scoped=True`: both project legs add
     `JOIN projects.order_inquiries soi ON soi.id = oir.order_inquiry_id
      JOIN projects.sales_orders spso ON spso.id = soi.project_sales_order_id
      JOIN sales_orders sso ON sso.id = spso.so_id AND sso.so_number = ANY(:so_numbers)`.
   `_planning_rows`, `_apply_project_supply_reduction`, `_plan_per_warehouse` and
   `demand_breakdown_service` read the two columns off the run and pass/bind them beside
   `horizon` / `horizon_start` at every site listed in section 2, so the drill popover
   and the frozen `inputs.committed` speak the same scope (the "run the whole inquiry
   family" lesson).
4. `GET /api/v1/scm/reorder-runs/candidate-orders?from=&to=` (permission
   `scm.reorder.run`, company scoped). Fix round 1 (reviewer S1/S2, security N2): the
   population is the SAME one `horizon_committed_select_sql`'s two project legs draw from,
   minus `ack_state` and `delivery_date` - reusing `_OWED_SQL`/`_OWED_FORM_SQL` (a row with
   nothing left owed does not count, matching the run's own predicate) and the form leg's
   retail-shadow `NOT EXISTS` guard, never restating the arithmetic. No `so.status='open'`
   or `so.demand_class='project'` predicate - the legs carry neither, so adding either
   would narrow the picker's universe past what the run itself counts. Each row leg pins
   `so.company_id = oir.company_id`, and the outer `projects.projects` join pins
   `pj.company_id`, so a same-numbered SO or project in another company can never surface.
   Grouped by SO: `{so_number, project_label, customer_name, rows_total, rows_in_range,
   rows_awaiting, first_delivery, last_delivery}`; `rows_in_range` uses the same date rule
   as the legs (an omitted bound is open). Ordered by `so_number`. ~321 rows on the prod
   copy, one call, no paging, no search param (the FE filters client-side).
5. `GET /reorder-runs/{id}` and the run list serializer (`reorder_runs.py:327, 531`)
   expose `demand_class` and `so_numbers` so the header shows the scope and a replan
   pre-fills it.

### Frontend

6. `RunPlanningModal`: new **Demand** `SearchableSelect` (Project / Dealer / All, default
   All, clearable = All) above the date row. When Project: an **Orders**
   `SearchableMultiSelect` appears under the dates, options from
   `getCandidateOrders(from, to)` (new function in `reorderRunService.ts`, one
   `useQuery` keyed on the range). Option label `SO419517 - OTM GROUP / TAT LIAN`,
   description `7 lines in range` or, when `rows_awaiting > 0`, `7 lines in range, 7
   awaiting ack` (the awaiting count renders in the warning colour). Pre-selected = every
   SO with `rows_in_range > 0`; the
   selection is re-derived when the range changes until the user has touched the list,
   then kept. Empty selection with Project chosen = "plan every project order in range"
   (send `[]`); the helper copy says so. Dealer / All: no Orders field.
7. `ManualPlanInputs` and `createReorderRun` carry `demand_class` and `so_numbers`
   (sent only when set / non-empty, like `product_codes`). The plan header
   (`PlanHeaderTab.tsx`) shows `Demand: Project, 6 orders` beside the window, and the
   replan form re-submits both.
8. No on-screen explanation beyond the existing one-line helper per field.

### Not built

- Per-line picking, ack override from the picker, a dealer order list, a generic SO
  select endpoint. Trigger for the last: a second screen needing an SO picker.

## 5. Slices and tickets

- S1 BE: migration + model + schemas + `create_run`/`replan_run` stamping (tests T1-T3).
- S2 BE: `horizon_committed_select_sql` args + every bind site + drill mirror (T4-T8).
- S3 BE: candidate-orders endpoint (T9-T11).
- S4 FE: modal fields, service, header, replan (V1-V4), Phase 1 against mocks first.
- W: browser pass 375 + 1280 via sidebar, evidence under
  `documentation/plans/scm/evidence/reorder-plan-demand-class-orders/`.

Tests are listed in the UAC. Tester writes T1-T11 and V1-V4 red before the coder's Phase 2.
