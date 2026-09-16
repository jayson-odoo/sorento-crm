# PLAN - Planning change confirm balances against the plan quantity (#971)

Status: **BUILT 17 Sep 2026, review READY, PR pending.** Issue #971. UAC: `scm-planning-change-plan-qty-acceptance-criteria.md`.
Diagnosis (Opus, read-only, 17 Sep) posted on the issue.

## 0. What the browser walk hit

On the 0915 production copy, SO289628, amend a line qty 3210 -> 3200. The Planning changes
banner appears. Confirming the recalculated line fails with
`The components add up to 3200 and the line is open for 2562`. The Buy the whole line toggle then
never flips (`aria-checked` unchanged). `so_supply_decisions` still holds one active revision.

## 1. Why (measured)

- Core line: `qty_ordered 3200, qty_delivered 638`. Owed = 2562. Plan quantity = 3200.
- `planning_change_service._row_open_qty` (`:2441-2450`) reads `proposal_json["qty_outstanding"]`
  (owed). Every other arm reads the plan quantity: the board (`project_fulfilment_board_service.py:1430`),
  the apply recheck (`project_supply_service.py:4781`, seeded `plan_qty_of` at `:7462`), the draft
  service, the FE (`boardAmend.ts:193,257`). The 14 Sep plan-quantity ruling (85e0279fe) touched
  all of those and not `planning_change_service.py`.
- The 422 is raised at `:2654-2658` inside `_validate_composition_shape`, reached from
  `fulfilment_planning.py:646-709` `_confirm_a_planning_change` -> `set_row_decision(..., "amend", composition)`.
- The toggle is a separate mechanism, not a bug of its own: `BoardLineDecisionPanel.tsx` keeps
  `locked = covered && !decision` (`:119-121`) and the switch is `disabled={locked}` (`:633`); it
  unlocks on a successful save or the explicit Amend button. The 422 keeps the planner clicking a
  control that needs Amend first. No FE change in this lane.
- Blast radius: 974 of 18,536 open lines on the copy are partly delivered (5.3%). Any of them whose
  qty or date changes can never have its planning change confirmed.

## 2. Journey

CS amends a partly delivered line (or a book re-upload changes it). The Planning changes banner
shows the row. CS presses Confirm. The decision posts a new revision covering the plan quantity.
CS never sees the mismatch error for a composition the board itself pre-filled.

## 3. Design (simplest thing that works, one seam)

`_row_open_qty` prefers `proposal["qty"]` (plan quantity) over `qty_outstanding`, keeping
`to_json["qty"]` as the last resort. Same flip for the `owed` fallback in
`composition_from_proposal` (`:2507-2511`), which is the same wrong reader (fires only when
`qty_proposed_buy` is absent). About four lines. No migration: the stored `proposal_json` already
carries `qty`. Apply's own recheck already uses the plan quantity, so both ends agree after the flip.

Not in scope: softening the covered-line lock on the toggle for a changed line (owner's call, separate
issue if wanted); the project mirror line still reading 3210 after a manual SCM edit (cosmetic, no
arm reads it here; folds into #969's mirror work if the owner wants it).

## 4. Tests (captain's list, tester first)

| AC | test | assertion |
| --- | --- | --- |
| PQ1 | `test_confirm_on_a_partly_delivered_line_balances_against_the_plan_quantity` | qty_down 3210 -> 3200 with qty_delivered 638; `PUT /planning-changes/{batch}/rows/{row}` decision=confirm returns 200, `composition_json["buy_qty"] == "3200"` |
| PQ2 | `test_amend_at_the_plan_quantity_is_accepted` | hand composition summing to 3200 on the same line: 200 |
| PQ3 | `test_amend_short_of_the_plan_quantity_is_still_refused` | composition summing to 2562: 422 `planning_change_composition_mismatch` |
| PQ4 | `test_row_open_qty_is_the_plan_quantity_on_a_delivered_line` | unit: proposal `qty=3200, qty_outstanding=2562` -> 3200; proposal without `qty` falls back to `to_json["qty"]` |
| PQ5 | `test_board_confirm_of_a_planning_change_on_a_delivered_line_writes_revision_2` | `POST /sales-orders/{pso_id}/confirm` with `batch_id`: a new `so_supply_decisions` revision exists |
| PQ6 | `test_fully_delivered_closed_line_confirms_its_change` | qty_ordered 1, qty_delivered 1 (owed 0, plan 1): confirm posts |
| PQ7 | two delivered-variant sibling tests (700 -> 900 shape) next to the existing confirm/amend tests, since the 134/234 shapes cannot take a 638 partial delivery | both arms green |

## 5. After merge

Owner re-tests SO289628 on the copy: Confirm posts, toggle unlocks after the save. Guide line in
`sales-order-changes.md` only if the wording there mentions the open quantity (guide-writer checks).
