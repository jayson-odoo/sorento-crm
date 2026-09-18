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
migration stamp) and a fresh sibling row a later planning change raised beside it,
carrying the Was/Now pair (`previous_qty` / `previous_delivery_date`) stamped from the
migrated row's old figures.

* **AC-4** Given a migrated row 182 @ 2027-03-01 on a line, a sibling fresh row 220 with
  `previous_qty` 182 and `previous_delivery_date` 2027-03-01, and the sheet, corrected,
  says 182 @ 2026-09-01, when the sheet is re-uploaded, then: the migrated row's
  `delivery_date` becomes 2026-09-01; the sibling's `previous_delivery_date` becomes
  2026-09-01; the sibling's own `qty` and `delivery_date` are untouched; no new row is
  raised (`rows_raised` 0); the outcome code is `DELIVERY_DATE_UPDATED`; and the result
  carries `rows_delivery_date_updated == 1` beside `rows_already_raised == 1`.
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

Never touched by any of the above: links, quantities (except the untouched sibling
assertion above), state, or ack fields.
