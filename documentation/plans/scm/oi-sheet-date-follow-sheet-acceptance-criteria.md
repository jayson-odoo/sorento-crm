# Acceptance criteria: order inquiry sheet - follow the sheet's own delivery date

Companion to `PLAN-oi-sheet-date-follow-sheet.md`. Every criterion is verified by a pytest
on Postgres (`tests/_pg_fixture.py`, via `world()`), seeding its own chain. Reverses
section 7.4 of `PLAN-scm-oi-sheet-pairing-repair.md`.

## AC-1 to AC-3: which date the raised row reports

* **AC-1** Given a sheet row dated 2026-09-01 against a line required 2027-03-01, when
  raised, then the row's `delivery_date` is 2026-09-01 (the sheet's own).
* **AC-2** Given a sheet row that states no date, against a line required 2027-03-01, when
  raised, then the row's `delivery_date` is 2027-03-01 (the line's, the only fallback).
* **AC-3** Given an ORDER BACK row (the date cell carries words, never a date) against a
  line required 2027-03-01, when raised, then the row's `delivery_date` is 2027-03-01 -
  unaffected by this reversal, since the sheet states no date either way.

## AC-4 to AC-7: a re-upload repairs a migrated row's date

The SO314593 shape: a MIGRATED row (raised by an earlier upload, note carrying the
migration stamp, `redirected_to_pool` once released) and a fresh sibling row a later
planning change raised beside it, carrying the Was/Now pair (`previous_qty` /
`previous_delivery_date`) stamped from the migrated row's old figures.

* **AC-4** Given a migrated, released row 182 @ 2027-03-01 on a line, a sibling fresh row
  220 with `previous_qty` 182 and `previous_delivery_date` 2027-03-01, and a LATER,
  differently named sheet, corrected, says 182 @ 2026-09-01, when it is uploaded, then: the
  migrated row's `delivery_date` becomes 2026-09-01; the sibling's `previous_delivery_date`
  becomes 2026-09-01 (its note prose corrected to match); the sibling's own `qty` and
  `delivery_date` are untouched; no new row is raised (`rows_raised` 0); the outcome code is
  `DELIVERY_DATE_UPDATED`; and the result carries `rows_delivery_date_updated == 1` beside
  `rows_already_raised == 1`.
* **AC-5** Given AC-4's upload run twice, when the second run applies, then it reports
  `ALREADY_RAISED` (`rows_delivery_date_updated == 0`, `rows_already_raised == 1`) and
  every value is identical to after the first run - the migrated row is already on the
  sheet's date.
* **AC-6** Given the only row on the line carries no migration stamp (raised by the
  board), when the sheet is re-uploaded naming that line, then it is skipped
  `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and nothing is written.
* **AC-7** Given a migrated row on the line whose quantity does not match the sheet row's
  (the sheet is restating a DIFFERENT instruction), when the sheet is re-uploaded, then it
  is skipped `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and the migrated row's
  date is untouched.

## AC-8 to AC-13: fix round 1 (19 Sep 2026, Opus review)

* **AC-8 (B1)** Given one line raised with two equal-quantity, differently dated rows (100
  @ 2026-09-01 + 100 @ 2026-10-01), when the SAME sheet is re-uploaded unchanged, then
  `rows_delivery_date_updated == 0` and both rows' dates are untouched; when a sheet that
  moves ONLY the October row to 2026-11-01 is uploaded, then `rows_delivery_date_updated
  == 1`, the September row's date is untouched, and the October row's own date moves to
  November; re-uploading that same moved sheet again writes nothing further (deterministic).
* **AC-9 (B2)** Given a migrated row a planning change has since restated
  (`previous_qty`/`previous_delivery_date`/`changed_at` all set, state PLACED, its own date
  moved away from the sheet's), when the ORIGINAL migration sheet is re-uploaded, then it is
  skipped `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and the row's own date,
  state and Was/Now are all untouched - a row purchasing has since worked on is never
  reverted by this repair.
* **AC-10 (S2)** Given a migrated row, when an ORDER BACK re-upload (states no date at
  all) names its line, then it is skipped `ALREADY_RAISED`, `rows_delivery_date_updated ==
  0`, and the migrated row's date is untouched (never written to `NULL`).
* **AC-11 (S2)** Given a CANCELLED migrated row that is the only quantity match on a line
  whose LIVE row carries a different quantity, when the sheet is re-uploaded, then it is
  skipped `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and the cancelled row's date
  is untouched.
* **AC-12 (S1)** Given AC-4's shape, when `preview` is called before Confirm, then it
  reports `rows_delivery_date_updated == 1`; when `apply` is then called on the same file,
  then it reports the SAME count `preview` forecast.
* **AC-13 (S5)** Given two migrated rows released to the pool (100 + 82, both 2027-03-01)
  and a sibling whose Was/Now was stamped from them (`previous_qty` 182,
  `previous_delivery_date` 2027-03-01, note "Was 182 on 2027-03-01"), when a sheet corrects
  the two released rows to DIFFERENT dates (2026-09-01 and 2026-10-01), then
  `rows_delivery_date_updated == 2`, the sibling's `previous_delivery_date` recomputes to
  the EARLIEST of the two (2026-09-01), `previous_qty` is untouched, and the note prose is
  corrected to match.

Never touched by any of the above: links, quantities (except the untouched sibling
assertion above), state, or ack fields - except AC-9's settled row, which keeps exactly
what the planning change itself wrote.
