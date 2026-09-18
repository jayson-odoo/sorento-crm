# Acceptance criteria: order inquiry sheet - correct a settled row's Was date too

Companion to `PLAN-oi-sheet-date-settled-rows.md`. Every criterion is verified by a pytest
on Postgres (`tests/_pg_fixture.py`, via `world()`), seeding its own chain. Follow-up to
`PLAN-oi-sheet-date-follow-sheet.md` (#1004, merged).

The rule for the owner: **a migrated row a planning change already restated keeps its Now
date; its Was date is corrected when it still carries the line's date and the sheet row
matches the Was quantity.**

* **AC-19** Given a migrated row restated IN PLACE (the SRTWCX8605-S-RL-PJ / CB2806A-DIY /
  SRTWB245 shape: `qty` 280, `delivery_date` 2027-03-01 (the line's `required_date`, its
  Now), `previous_qty` 182, `previous_delivery_date` 2027-03-01 (the Was, 7.4's mistake),
  note carrying `"...; Linked to 202603-S0109 (...), expected 2026-06-01; auto: autocount
  linkage; Was 182 on 2027-03-01"`), and the sheet says 182 @ 1.6.2026, when `preview` is
  called, then it forecasts `rows_delivery_date_updated == 1`; when `apply` is then called
  on the same file, then: `previous_delivery_date` moves to 2026-06-01; `delivery_date`,
  `qty` and `previous_qty` are all untouched; the note's `"AutoCount ...; Linked to ...,
  expected ..."` prose survives verbatim and only the `"Was 182 on ..."` fragment moves to
  `"Was 182 on 2026-06-01"`; the outcome reports `DELIVERY_DATE_UPDATED`.
* **AC-20** Given a settled row whose `previous_delivery_date` already differs from the
  line's `required_date` (already corrected, or never carried 7.4's mistake), when the
  sheet is uploaded naming its line, then it is skipped `ALREADY_RAISED`,
  `rows_delivery_date_updated == 0`, and the row is untouched.
* **AC-21** Given a settled row whose `previous_qty` does not match the sheet row's
  quantity (a different instruction), when the sheet is uploaded, then it is skipped
  `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and the row is untouched.
* **AC-22** Given AC-19's upload run twice, when the second run applies, then it reports
  `rows_delivery_date_updated == 0` - once repaired, the row's `previous_delivery_date` no
  longer equals the line's `required_date`, so the second run finds no candidate.
* **AC-23** Given one line carrying BOTH an untouched migrated row (shape A, same quantity
  as a settled row's `previous_qty`) and a settled row (shape B), with only ONE sheet row
  of that quantity, when the sheet is uploaded, then shape A is resolved (the untouched
  row's `delivery_date` moves), the settled row's `previous_delivery_date` is untouched,
  and `rows_delivery_date_updated == 1` - one sheet row claims one row only, deterministically
  (exact match first, then shape A, then shape B).

Never touched by any of the above: `qty`, `state`, `changed_at`, `ack_state`, links - shape
B's own row's `delivery_date` included, since only its Was side ever moves.
