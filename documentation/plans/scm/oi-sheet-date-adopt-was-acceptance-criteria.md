# Acceptance criteria: order inquiry sheet - adopt the sheet row as a restated row's Was

Companion to `PLAN-oi-sheet-date-adopt-was.md`. Every criterion is verified by a pytest on
Postgres (`tests/_pg_fixture.py`, via `world()`), seeding its own chain. Follow-up to
`PLAN-oi-sheet-date-settled-rows.md` (#1011, merged).

The rule for the owner: **a migrated row the board restated before a Was was recorded
adopts the sheet row as its Was; its Now stays the book's.**

* **AC-25** Given a migrated row a board Confirm restated IN PLACE (the CB2806A-DIY (220) /
  SRTWB245 (280) shape: `qty` 220, `delivery_date` the line's `required_date`, `changed_at`
  set, `previous_qty`/`previous_delivery_date` both `NULL`), and the sheet says 182 @
  1.6.2026, when `preview` is called, then it forecasts `rows_delivery_date_updated == 1`;
  when `apply` is then called on the same file, then: `previous_qty` becomes 182,
  `previous_delivery_date` becomes 2026-06-01; `delivery_date` and `qty` are both
  untouched; the note gains `"; Was 182 on 2026-06-01"`; the outcome reports
  `DELIVERY_DATE_UPDATED`.
* **AC-26** Given a migrated row with `changed_at IS NULL` (never restated - shape A's own
  territory) whose quantity does not match the sheet's, when the sheet is uploaded, then it
  is skipped `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and the row is untouched.
* **AC-27** Given a restated row whose `delivery_date` already differs from the line's
  `required_date`, when the sheet is uploaded, then it is skipped `ALREADY_RAISED`,
  `rows_delivery_date_updated == 0`, and the row is untouched.
* **AC-28** Given AC-25's upload run twice, when the second run applies, then it reports
  `rows_delivery_date_updated == 0` - once adopted, the row's `previous_qty` is no longer
  `NULL`, so the second run finds no candidate.
* **AC-29** Given one mirror carrying a shape A row, a shape B row AND a shape C row, with
  THREE sheet rows each matching exactly one, when the sheet is uploaded, then all three
  are resolved (`rows_delivery_date_updated == 3`) - each claimed exactly once,
  deterministically, in priority order (exact match, then shape A, then shape B, then
  shape C).

Never touched by any of the above: `qty`, `delivery_date` (shape C's own row), `state`,
`ack_state`, links.
