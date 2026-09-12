# UAC: planning change raised only for a held or inquired line

Plan: `PLAN-scm-planning-change-gate-held-or-inquiry.md`. Supersedes AC-R01 / AC-R03 of
`PLAN-so-book-diff-replanning.md`.

**AC-G1 (undecided line is silent).** Given an adopted project SO line with no active supply
decision covering it and no non-cancelled Order Inquiry row, when its required date, quantity
or open state changes through any of the three triggers (SO book upload, ESB ingest, manual SO
edit), then no `planning_change_rows` row is written for it, and if it was the only changed
line no batch exists at all (`build_batch` returns `None`, the manual-edit envelope's
`planning_change_batch` is `None`).

**AC-G2 (held line still raises).** Given a line frozen in the order's active decision, when it
changes, then exactly one row is written for it with `held_json` populated and the existing
suggestion rules (keep / release / replan / reduce / retire) unchanged.

**AC-G3 (inquiry without active decision still raises).** Given a line with a raised or placed
Order Inquiry row whose decision is no longer active, when it changes, then one row is written
with `held_json` null and `inquiry_rows_json` non-empty.

**AC-G4 (mixed order counts only kept rows).** Given one order with one held line and one
undecided line both changed in one upload, then the batch has `line_count == 1`,
`order_count == 1`, and one row.

**AC-G5 (pill reads pending rows only).** Given a batch with `applied_at` null whose rows are
all `superseded`, then `GET /api/v1/scm/sales-orders` returns `planning_change_batch_id` null
for that order; given the same batch with one `pending` row, it returns the batch id.

**AC-G6 (backfill).** After migration `513_planning_change_gate_backfill` on the 10 Sep live
copy, every pending row with no held decision and no inquiry row is `superseded` with a
reason, every batch left without a pending row has `applied_at` set, and SO389799's held row
stays `pending` with its batch still open. No row or batch is deleted.

**AC-G7 (browser).** On the lane after the migration, SCM Sales Orders search `SO403765` shows
no `Changed` pill; `SO389799` shows it, and the board it opens marks one cell Was / Now.
