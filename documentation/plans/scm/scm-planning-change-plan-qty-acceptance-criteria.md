# UAC - Planning change confirm balances against the plan quantity (#971)

Plan: `PLAN-scm-planning-change-plan-qty.md`.

## Journey

CS amends a partly delivered sales order line (or a book re-upload changes it). The Planning changes
banner shows the row. CS presses Confirm and the decision posts. No composition mismatch error for
a composition the board pre-filled.

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-PQ1 | [BE] | Given an adopted order with a core line `qty_ordered 3210, qty_delivered 638` and an active decision, when the line is amended to 3200 and the raised planning-change row is confirmed via `PUT /planning-changes/{batch}/rows/{row}` with `decision=confirm`, then the response is 200 and the row's `composition_json["buy_qty"]` is `"3200"`. |
| AC-PQ2 | [BE] | Given AC-PQ1's row, when the decision is `amend` with components summing to 3200, then 200. |
| AC-PQ3 | [BE] | Given AC-PQ1's row, when the decision is `amend` with components summing to 2562, then 422 with code `planning_change_composition_mismatch`. |
| AC-PQ4 | [BE] | Given a proposal `{qty: 3200, qty_outstanding: 2562}`, when `_row_open_qty` reads it, then it returns 3200; given a proposal with no `qty`, then it falls back to `to_json["qty"]`. |
| AC-PQ5 | [BE] | Given AC-PQ1's order, when the board confirm `POST /sales-orders/{pso_id}/confirm` runs with the batch id, then `so_supply_decisions` holds a second revision for the order and the first is superseded. |
| AC-PQ6 | [BE] | Given a line `qty_ordered 1, qty_delivered 1` (owed 0) with a raised planning change, when it is confirmed, then 200. |
| AC-PQ7 | [BE] | Given the existing delta-seam confirm and amend tests, when parametrized over `qty_delivered in (0, 638)`, then every arm passes. |
| AC-PQ8 | [FE, browser] | Given SO289628 on the 0915 copy after the fix, when CS confirms the recalculated line, then the confirm posts and the Buy the whole line toggle is enabled afterwards. Evidence screenshot in `documentation/plans/scm/evidence/planning-change-plan-qty/`. |
