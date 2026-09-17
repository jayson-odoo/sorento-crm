# PLAN: Loading plan - Project column nets SPO placements only, not PO

Status: APPROVED - owner rulings 18 Sep 2026; building. Track: small fix (switched mid-lane, 18 Sep; tester already ran, so second reviewer + lane DB are what it saves here)
Domain: scm
Branch: feat/loading-plan-project-spo-only
Worktree: ../sorento_crm-lp-project-spo-only
Test DB: sorento_lpsp_ci
UAC: loading-plan-project-spo-only-acceptance-criteria.md
Owner feedback: 18 Sep 2026, loading plan d7192c99 (CHAOZHOU JINBAICHUAN), CWB242, SO414033.

## What the owner saw

SO414033 has six open CWB242 lines of 234 each. Three fall before the plan's cut-off
(31/10/2026) but the Project popup (503) did not list them. Measured on the prod copy: each
of the three carries `projects.order_inquiry_links` rows totalling 234, on PO 202608-S0052
(the 14/09 line: 233 on the PO + 1 on SPO-2026/09-0063). `_project_open_need` nets every
link regardless of document kind, so all three netted to zero and vanished.

## Rulings (owner, 18 Sep 2026)

- R1: **A PO link means nothing to the loading plan.** Only a shipping order (SPO) is supply
  the loading plan may subtract from a project requirement. A PO tells the supplier what
  was bought; the loading plan asks what to SHIP. A PO-placed line is still open demand.
- R2: **Loading plan only.** The reorder run legs (`demand.py`), `scm.committed_v`
  (migration 511) and the demand breakdown drill keep netting both PO and SPO links. Named
  trigger for widening: the owner rules on the SPO planner separately.
- R3: **Partly covered by SPO: show the open quantity WITH the balance.** The popup lists
  the line with its full open qty and the balance left after SPO placements. The Project
  column and the popup footer count the BALANCE (what is still to ship), so the number that
  opened the dialog and the rows inside it still agree (R8 of the p4 plan). A line whose
  SPO links reach its open qty has balance 0 and is not listed.

## Simplest thing that works

One predicate, one seam. `_PLACED_ON_LINE_SQL` in
`app/services/scm/container_request_service.py` gains `AND l.spo_allocation_id IS NOT NULL`
and is renamed to say what it now counts. `_project_open_need` and `_open_lines` both read
it, so the column and the popup move together. `_open_lines` additionally emits `open_qty`
(the gross open quantity, before SPO netting) next to the existing `qty` (the balance).
No new table, no flag, no migration.

## Slices

### S1 backend (tester-first)

- `_PLACED_ON_LINE_SQL` -> `_SPO_PLACED_ON_LINE_SQL`: same LATERAL, filtered to
  `l.spo_allocation_id IS NOT NULL`. Docstring says why PO links are out (R1).
- `_open_lines` SELECT adds `{_OPEN_QTY_SQL} AS open_qty`; serializer emits
  `"open_qty": float(r["open_qty"] or 0)` beside `qty`.
- `qty` stays the balance (`open - spo_placed`, floored at 0); the `WHERE qty > 0` stays.
- Comments in the module that say "placed on a PO or an SPO" are corrected at the three
  sites (`_PLACED_ON_LINE_SQL` header, `_project_open_need` docstring, `_stock_context` S5
  note). The S5 residue note about PO-placed stock landing in a project bin is now narrower
  (SPO-placed only) and is reworded, not deleted.
- Existing tests that model a PO placement (`_place` in
  `tests/scm/test_container_request_universe.py`, `test_build_on_hand_nets_a_placed_projects_bin_stock_against_retail_demand`
  in `test_container_request.py`) are rewritten to the new rule; the tester adds an SPO
  placement helper next to `_place`.

### S2 frontend

- `ContainerRequestSoLine` (`services/fulfilmentService.ts`) gains `open_qty: number`.
- `PlanDemandLineRow` (`components/PlanRowDialog.tsx`) gains `open_qty: number`;
  `toDemandLines` in `loading-plan/components/ContainerRequestSection.tsx` maps it.
- The Open tab of the Project / Retail / Need lightbox shows `Open` (open_qty) then
  `Balance` (qty) in place of the single `Qty` column; footer under Balance is the tab's
  total (unchanged arithmetic). Retail lines: `open_qty === qty` always, both shown, no
  special case.
- The reorder lane's own `PlanRowDialogs.tsx` / `PlanDemandPopover.tsx` are NOT touched
  (R2): they read the run, not this build.

### S3 review + browser + guide

- reviewer + security-reviewer (light: no auth surface) + agent-browser pass on the lane
  stack: CWB242 on the CHAOZHOU JINBAICHUAN loading plan shows SO414033 x3 in the popup,
  Project = 503 + 701 = 1,204 (233 + 234 + 234; the 14/09 line keeps 1 on an SPO), To request moves by the same 701.
- Guide line in the loading plan user guide: "Project counts open project lines less what
  is already on a shipping order; a purchase order does not reduce it."

## Out of scope

- Reorder run / SPO planner netting (R2).
- Showing fully SPO-covered lines greyed in the popup (not asked).
