# PLAN: order inquiry sheet - correct a settled row's Was date too

Status: Track: small fix - ready for PR review. Follow-up to `PLAN-oi-sheet-date-follow-
sheet.md` (#1004, MERGED and deployed as `92c9b27d2`). Lane worktree
`sorento_crm-oi-sheet-date`, branch `fix/oi-sheet-date-settled-rows`. DB `sorento_oisd_ci`.
Backend only.

UAC: `oi-sheet-date-settled-rows-acceptance-criteria.md`.

## What was measured

The owner ran the real book (`JAN - DEC 2026 ORDERabc.xlsx`) on prod after #1004 deployed.
Six of SO314593's used rows were corrected to 2026-06-01, as designed. Three rows were
skipped as `ALREADY_RAISED` and the owner asked why: `SRTWCX8605-S-RL-PJ` 280,
`CB2806A-DIY` 220, `SRTWB245` 280.

Their shape: the MIGRATED row itself was restated IN PLACE by a planning change (there is
no fresh sibling raised beside it) - `qty` 280, `delivery_date` 2027-03-01 (the book's own
date, correct, this is what the planning change most recently settled it to), `previous_qty`
182, `previous_delivery_date` 2027-03-01 (7.4's mistake, still sitting on the Was side),
note `"Migrated from order inquiry sheet JAN - DEC 2026 ORDERabc.xlsx; Linked to
202603-S0109 (...), expected 2026-06-01; auto: autocount linkage; Was 182 on 2027-03-01"`.
The sheet row says 182 @ 1.6.2026.

`PLAN-oi-sheet-date-follow-sheet.md`'s own B2 rule (`previous_qty`/`previous_delivery_date`
/`changed_at` all `NULL`) and the quantity match (280 != 182, since shape A compares the
sheet against the row's CURRENT `qty`) both correctly exclude this row from repair - by
design, purchasing's own settle is never reverted - but that design missed this shape:
**what the sheet describes here is the row's WAS state**, not its Now. The row's Now
(`qty` 280, `delivery_date` 2027-03-01) is the planning change's own correct figure and is
never what a re-upload should touch; its Was (`previous_qty` 182, `previous_delivery_date`
2027-03-01) is still 7.4's own mistake, exactly the same fingerprint shape A looks for -
just carried on the other pair of columns.

## The rule, for the owner

**A migrated row a planning change already restated keeps its Now date; its Was date is
corrected when it still carries the line's date and the sheet row matches the Was
quantity.**

## The change

A second repair shape, resolved in the SAME pure step (`_resolve_delivery_date_repairs`,
inside `_plan`) and written in `apply`, alongside the existing one:

* **Shape A (existing, unchanged).** An untouched migrated row (`previous_qty`/
  `previous_delivery_date`/`changed_at` all `NULL`), `qty == sheet qty`,
  `delivery_date == line's required_date` -> `delivery_date := sheet date` (+ the existing
  sibling Was/Now resync for a `redirected_to_pool` row).
* **Shape B (new).** A migrated row with `previous_qty == sheet qty` AND
  `previous_delivery_date == line's required_date` (7.4's fingerprint, on the Was side) ->
  `previous_delivery_date := sheet date`; `delivery_date`, `qty`, `state`, `changed_at` and
  `ack_state` are all untouched; the note fragment `f"Was {qty} on {old}"` moves to
  `f"Was {qty} on {new}"` (anchored, first occurrence, the same `_qty_str` formatting shape
  A's own sibling resync uses). A row already on the sheet's date on its Was side, or whose
  `previous_qty` differs from the sheet's quantity, is left alone.

**Claim-once, same ordering as shape A extends to:** a sheet row claims at most one row -
exact match first (shape A's own pass 1), then shape A's general repair (pass 2), then
shape B. `_resolve_shape_b_repairs` re-derives shape A's own pass-1 exact-match set (rather
than changing `_resolve_line_repairs`'s return shape, which would break its own DB-free
unit tests from round 2) so a row shape A already claimed - repaired OR settled as a no-op
exact match - is never also handed to shape B.

**Outcome code.** Reuses `DELIVERY_DATE_UPDATED` with a per-row `message` of "Was date
corrected to the sheet's own" (shape A's own call passes no message, so it falls back to
the code's static label). `ImportOutcome`'s aggregate breakdown labels a code ONCE, off
`import_outcome_codes.LABELS`, the first time it is seen (`self._labels.setdefault(code,
label)`) - never off the per-row `message`, which is stored separately, per row, for the
job detail table - so the tile and the `validate()` warning count both shapes under the
SAME code without a second one. `rows_delivery_date_updated` in `_result` already sums
`plan.matches` where `repair_row_id` is set, so shape B is counted automatically.

**No frontend change.** The "Dates corrected" tile and its count already cover
`rows_delivery_date_updated` regardless of shape.

## Files touched

* `app/services/project_order_inquiry_import_service.py` - `_Match.repair_shape` (new
  field, `"A"` or `"B"`); `_resolve_shape_b_repairs` (new); `_resolve_delivery_date_repairs`
  rewritten to query both shapes in one statement and orchestrate them; `apply()`'s
  already-raised branch gains the shape-B write path; `validate()`'s warning text is now
  shape-neutral ("date" rather than "delivery date").
* `tests/test_oi_sheet_date_follow_sheet.py` - `_settled_row` helper (new); AC-19 to AC-23.
* `documentation/user-guides/supply-chain/upload-plan-data.md` - one clause on the
  re-upload sentence.
