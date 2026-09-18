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

* **AC-8 (B1)** Given one line carrying TWO migrated rows, both dated the line's OWN
  `required_date` (7.4's exact fingerprint: 100 + 100, same item, no per-row identity to
  tell them apart), when a sheet stating 100 @ 2026-09-01 and 100 @ 2026-10-01 is uploaded,
  then `rows_delivery_date_updated == 2` and the two migrated rows end up split across the
  two dates, one each; re-uploading that SAME corrected sheet again writes nothing further
  (pass 1 now finds an exact match for each, deterministically).
* **AC-9 (B2)** Given a migrated row a planning change has since restated
  (`previous_qty`/`previous_delivery_date`/`changed_at` all set, state PLACED, its own date
  moved away from the sheet's), when the ORIGINAL migration sheet is re-uploaded, then it is
  skipped `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and the row's own date,
  state and Was/Now are all untouched - a row purchasing has since worked on is never
  reverted by this repair. Also (S7, fix round 2): each of the three markers
  (`previous_qty` / `previous_delivery_date` / `changed_at`) blocks the repair ALONE, with
  the migrated row's own date left at the line's `required_date` so AC-15's own gate is not
  what is blocking it.
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

## AC-14 to AC-16: fix round 2 (19 Sep 2026, Opus review round 2)

* **AC-14a (B3)** Given AC-4's shape PLUS an UNRELATED, already-PLACED sibling on the
  SAME mirror carrying its OWN Was/Now (`previous_qty` 25, `previous_delivery_date`
  2026-05-01) and its own `"AutoCount moved PO-1 to SO-9 on 2026-05-01; Was 25 on
  2026-05-01"` note, when the repair runs, then the unrelated sibling's
  `previous_delivery_date` and `note` are BYTE FOR BYTE untouched - a repair matches a
  sibling only on the EXACT `(previous_delivery_date, previous_qty)` pairing the redirected
  rows produced, never "any sibling on this mirror".
* **AC-14b (B3)** Given AC-4's shape PLUS a second, NON-redirected migrated row on the same
  mirror dated EARLIER than the redirected row's own date, when the repair runs, then the
  sibling's `previous_delivery_date` recomputes from the redirected row alone - the earlier,
  non-redirected row is never counted into the earliest-date computation.
* **AC-15 (S8)** Given a migrated row raised under THIS fix's own rule (so its
  `delivery_date` already differs from its core line's `required_date` - not 7.4's own
  mistake), when any later sheet, however dated, is re-uploaded naming its line, then it is
  skipped `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and the row's date is
  untouched.
* **AC-16 (S9, DB)** Given two migrated rows on one line, same item and quantity, whose
  `created_at` is set OPPOSITE to their insertion order, when a sheet row whose date
  matches neither is uploaded, then the row with the EARLIER `created_at` is the one
  repaired, and the later-`created_at` row is untouched - `_resolve_delivery_date_repairs`'s
  own `ORDER BY created_at, id` decides the order, not insertion sequence.

Two DB-free unit tests pin `_resolve_line_repairs`'s own pure-function contract directly
(S9): it trusts the ORDER it is handed rather than re-deriving `created_at`/`id` itself, and
pass 1 settles exact item/quantity/date matches before pass 2 ever runs, regardless of that
order.

Never touched by any of the above: links, quantities (except the untouched sibling
assertion above), state, or ack fields - except AC-9's settled row, which keeps exactly
what the planning change itself wrote, and AC-14a's unrelated sibling, which keeps exactly
what it already carried.
