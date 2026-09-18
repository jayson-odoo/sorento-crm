# Acceptance criteria: order inquiry sheet - adopt the sheet row as a superseded row's replacement's Was

Companion to `PLAN-oi-sheet-date-adopt-was.md`. Every criterion is verified by a pytest on
Postgres (`tests/_pg_fixture.py`, via `world()`), seeding its own chain. Follow-up to
`PLAN-oi-sheet-date-settled-rows.md` (#1011, merged). Revised (round 7) after a prod
`SELECT` showed the original shape (one stamped row, `changed_at` set, no Was) never
occurs - the real shape is a CANCELLED, superseded migrated row plus a fresh LIVE row that
replaced it, on the same mirror.

The rule for the owner: **a live row that replaced a superseded migrated row adopts the
sheet row as its Was; its Now stays the book's.**

* **AC-25** Given the REAL SO314593 pair - a CANCELLED migrated row (`qty` 220,
  `previous_qty` 182, `previous_delivery_date` the line's `required_date`, note
  `"Superseded by revision 2"`) and a LIVE row that replaced it (`qty` 220, `delivery_date`
  the line's `required_date`, no Was, no stamp) - and the sheet says 182 @ 1.6.2026, when
  `preview` is called, then it forecasts `rows_delivery_date_updated == 1`; when `apply` is
  then called on the same file, then: the LIVE row's `previous_qty` becomes 182,
  `previous_delivery_date` becomes 2026-06-01, `delivery_date` and `qty` are both
  untouched, its note gains `"Was 182 on 2026-06-01"`; the CANCELLED row is untouched; the
  outcome reports `DELIVERY_DATE_UPDATED`; `preview`'s forecast equals what `apply` wrote.
* **AC-26** Given a live row with shape C's own shape (no Was, on the line's own date) but
  NO cancelled sibling anywhere on the mirror - a plain board row - when the sheet is
  uploaded, then it is skipped `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and the
  row is untouched.
* **AC-27** Given a cancelled migrated sibling whose OWN `qty` AND `previous_qty` both
  differ from the sheet's quantity, when the sheet is uploaded, then the live row is
  skipped `ALREADY_RAISED`, `rows_delivery_date_updated == 0`, and untouched.
* **AC-28** Given AC-25's upload run twice, when the second run applies, then it reports
  `rows_delivery_date_updated == 0` - once adopted, the live row's `previous_qty` is no
  longer `NULL`, so the second run finds no candidate.
* **AC-29** Given one mirror carrying a shape A row, a shape B row, AND a shape C pair (a
  live row + its cancelled sibling), with THREE sheet rows each matching exactly one, when
  the sheet is uploaded, then all three resolve (`rows_delivery_date_updated == 3`) - each
  claimed exactly once, deterministically, in priority order (exact match, shape A, shape
  B, shape C).

Three more from the round 7 review, each its own red:

* **Sibling identity, not position.** Two live rows and two cancelled siblings of the SAME
  item on one mirror, with the sheet's own two rows (100 and 182) in the REVERSE order of
  the siblings' own creation (182 created first, 100 second) - both sheet rows still
  resolve, paired through whichever sibling's own quantity actually matches, never by file
  or creation position.
* **Anchored note edit.** A live row whose note already carries a `"Was ... on ..."`
  fragment (an unusual prior state) has that fragment REPLACED by the adoption, never a
  second one appended.
* **Idempotent even when the adopted date equals the line's own date.** When the sheet's
  own date happens to equal the line's `required_date`, a second run is still a no-op - the
  adopted live row is never a stamped (migrated) row, so it never re-enters shape A's or
  shape B's own pool on a later run either, on top of shape C's own precondition no longer
  holding.

Never touched by any of the above: the CANCELLED sibling (read-only, always), the live
row's `qty`/`delivery_date`/`ack_state`, links.
