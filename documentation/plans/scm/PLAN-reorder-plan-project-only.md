# PLAN: A Project plan buys for the order inquiries alone (22 Sep 2026)

Status: BUILT 22 Sep 2026, review in progress; browser AC-PO-11 queued (no slot). Feature track (two seams in one
service, no migration; tests on the run's own fixtures).
UAC: `reorder-plan-project-only-acceptance-criteria.md`.
Lane: worktree `../sorento_crm-plan-project-only`, branch `fix/reorder-plan-project-only`
off `origin/main` d57fd367c. Tests on `sorento_buc_ci` via `SORENTO_ENV_FILE=.env.ci-tests`
(export `DATABASE_URL` from it too for `tests/scm/`).

## 1. Journey

Purchasing opens Start Plan, picks Demand = Project, a delivery range, and the 13 or 14
sales orders off the week's ORDER INQUIRY sheet. The plan must list exactly the inquiry
rows on those orders that still need buying (ORDER / ORDER BACK, acknowledged, not linked to
a PO or SPO, owed > 0), one line per product, and nothing else. On 22 Sep the same run
returned 492 lines and RM 34,141 (run "Plan 22/09/2026 17:13", Demand: Project, 13
orders). The owner expects under 50.

## 2. Measured facts (origin/main d57fd367c, DB `sorento_ai_automation_0921`)

- `_planning_rows` (`reorder_run_service.py:805-1075`) admits a product through TWO legs
  OR'd in `product_admit_join`: (1) `committed > 0` in `cv_all`, which is
  `demand.horizon_committed_select_sql(demand_class, so_scoped)` and so honours the
  Demand / orders scope; (2) "below reorder level and not dead": dealer-pool on hand
  under `COALESCE(scm.reorder_level.level, products.reorder_level)` with a
  `scm.consumption_v` movement inside `dead_stock_days` (180). Leg 2 ignores
  `demand_class` and `so_numbers` entirely. Leg 2 admits 1157 products on the copy.
- `_emit_pool` (`:1835-1975`) sizes every admitted product with the RETAIL policy
  (`eng.trigger` on the dealer net against reorder point / min-max / reorder level), then
  adds `pool_project_need` on top; `triggered` is forced true only when the retail trigger
  did not fire and project need > 0. So a below-level product with no project need still
  emits a retail Buy inside a Project run. The owner's pasted rows (MPW800 level 150 on
  hand 0 -> Buy 150; SRTBT1863-15 level 2 on hand 0 -> Buy 2) are all leg 2.
- `_apply_unlocated_demand` is already skipped for a project run (`:1624`), the one place
  the run already knows to be project-only.
- Leg 1 alone for the owner's 14 orders on the copy: 45 inquiry rows (ORDER/ORDER_BACK,
  raised/partly_linked, acknowledged/changed, owed > 0), 16 of them with delivery on or
  before 31 Oct. That is the owner's "not more than 50".

## 3. Rulings (owner, 22 Sep 2026)

- R1: "Limit to what I have selected, order inquiries, require buy." A Project run
  (Demand = Project, with or without orders picked) admits products through leg 1 ONLY,
  and sizes each line as the project need alone: no retail reorder-point / min-max /
  reorder-level top-up, no leg 2 admission. Dealer and All runs are unchanged.
- R2 (open, asked 22 Sep): an "inquiries raised from / to" filter on Start Plan. Deferred
  until the owner says which sheet column or upload carries the raise date; `raised_at`
  on the copy is the upload date and the picked orders spread 17-21 Sep.
- R3 (open, asked 22 Sep): green-highlighted sheet rows (supplied from on-hand stock, no
  purchase) to be read on upload and recorded against a stock transfer. Separate lane.

## 4. Slices

- S1 Admission: in `_planning_rows`, when `demand_class == "project"`, `product_admit_join`
  is leg 1 alone (`SELECT DISTINCT product_id FROM cv_all WHERE committed > 0`), no UNION.
  Rows of an admitted product are still every location row, as today (the pool needs its
  members' stock to net a borrow). The `:rl_sources` / `:dead_days` binds are only added
  when leg 2 is in the SQL.
- S2 Sizing: thread `demand_class` from the recommendation loop (`:1596-1660`) into
  `_emit_pool`. When `demand_class == "project"`: `retail_recommended = 0`, `triggered =
  pool_project_need > 0`, `recommended = pool_project_need`, `reason_label = "project buy:
  ..."` (the existing label), `rounded` still applies MOQ / multiples. Everything else in
  the function (allocation by deficit, supplier choice, basis) unchanged. A single-location
  product that is not pooled goes through the same function today (one-member pool), so
  one branch covers both.
- S3 Header: the run's Counts / Cash on the Header tab need no change; they sum what S1/S2
  emit.

## 5. Test list (tester writes these red first; `tests/scm/test_reorder_plan_project_only.py`,
built on `tests/test_reorder_plan_demand_scope.py`'s fixtures)

- A product below its reorder level (level 150, dealer on hand 0, moved last week) with
  NO project inquiry row: Project run -> no recommendation; Dealer run -> Buy (unchanged).
- A product WITH an acknowledged unlinked ORDER row (qty 20) AND below level (level 150,
  on hand 0): Project run -> exactly one line, Buy 20, reason label starts "project buy";
  Dealer run -> the retail Buy as today.
- A product with an ORDER row on an order NOT in `so_numbers`: Project run scoped to other
  orders -> no line.
- A product whose ORDER row is fully linked to a PO line: Project run -> no line.
- MOQ 50 on the supplier, project need 20: Project run -> Buy 50 (rounding still applies).
- Pooled product (two dealer locations in one pool) with project need 10 at one member and
  on hand 100 at the other: Project run -> Buy 10 (a Project run does NOT net the sibling's
  stock against a firm project Buy; that is what `pool_project_need` already does today).
- Existing `tests/scm/test_pool_netting_parity.py`, `test_reorder_run_product_scope.py`,
  `test_reorder_run_scope_isolation.py`, `tests/test_reorder_plan_demand_scope.py` stay green.

## 6. Out of scope

R2 raised-date filter, R3 green rows / stock transfers, the demand drill gap already noted
in `PLAN-oi-order-back-not-capped.md`.
