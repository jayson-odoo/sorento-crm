# UAC: Start Plan scoped by demand class and by sales order

Plan: `PLAN-reorder-plan-demand-class-orders.md`. Status: drafted 21 Sep 2026, owner
rulings R1-R5 taken.

## Journey

J1 Owner opens Reorder planning from the sidebar, clicks Start Plan, picks Demand =
Project, From 01/08/2026, To 31/10/2026. The Orders field lists every open project SO
with an OI row, the ones with a row in range pre-selected, each with its in-range line
count and its awaiting-ack count. Owner unticks one, ticks another, presses Start Plan.
The run counts only rows on the selected SOs that are inside the range, acknowledged,
and on the selected warehouses/products.

J2 Owner picks Demand = Dealer and a range. No Orders field. The run counts only retail
SO lines in range (today's book leg).

J3 Owner leaves Demand = All. The modal and the run behave exactly as before this change.

## Backend acceptance (pytest, `tests/test_reorder_plan_demand_scope.py`)

- T1 `POST /reorder-runs` with `demand_class='project'`, `so_numbers=['SO1']` stores both
  on `scm.reorder_run`; `GET /reorder-runs/{id}` returns them.
- T2 `so_numbers` non-empty with `demand_class` omitted or `retail` -> 422.
- T3 `POST /reorder-runs/{id}/replan` carries `demand_class` + `so_numbers` onto the new
  run.
- T4 Seed: one retail SO line (required_date in range), one acked OI row on project SO A
  (delivery in range), one acked OI row on project SO B (in range), one acked row on SO A
  dated outside the range, one awaiting row on SO A in range. Run with
  `demand_class='project'`, `so_numbers=['A']`, range set: `inputs.committed` for the
  product = SO A's single in-range acked qty only.
- T5 Same seed, `demand_class='project'`, `so_numbers=[]`: committed = A + B in-range
  acked qtys; retail line excluded.
- T6 Same seed, `demand_class='retail'`: committed = the retail line only.
- T7 Same seed, no `demand_class`: committed = retail + A + B (unchanged behaviour).
- T8 Demand drill (`demand_breakdown_service`) for the T4 run lists SO A's in-range acked
  row only and its total equals `inputs.committed`.
- T9 `GET /reorder-runs/candidate-orders?from&to` returns SO A and SO B with
  `rows_total`, `rows_in_range`, `rows_awaiting`, `first_delivery`, `last_delivery`
  matching the seed; a closed SO and a retail SO are absent.
- T10 candidate-orders with no bounds: `rows_in_range == rows_total`.
- T11 candidate-orders is company scoped (another company's SO absent) and needs
  `scm.reorder.run`.
- T12 `horizon_committed_select_sql()` with no args renders SQL with no `:so_numbers`
  bind (other callers unchanged).

## Frontend acceptance (vitest, `RunPlanningModal.test.tsx`)

- V1 Demand defaults to All; Orders field absent for All and Dealer, present for Project.
- V2 With Project + range, options come from `getCandidateOrders(from, to)`; SOs with
  `rows_in_range > 0` are pre-selected; the label shows the SO number and project label,
  the description the in-range count and, when > 0, the awaiting count.
- V3 Submit sends `demand_class` and `so_numbers` (only the user's final selection;
  `[]` when everything was unticked); Dealer sends `demand_class='retail'` and no
  `so_numbers`; All sends neither.
- V4 Changing the range re-derives the pre-selection until the user edits the list, then
  the user's list is kept.

## Browser (agent-browser, sidebar navigation, evidence PNGs at 375 and 1280)

- B1 J1 end to end on the lane stack: modal, Orders list populated, one untick, Start
  Plan, run completes, header shows `Demand: Project, N orders`, a recommendation's
  demand drill shows only rows on the selected SOs.
- B2 J2 and J3: no Orders field, run completes.
- B3 375px: modal scrolls, Orders list usable, nothing clipped.
