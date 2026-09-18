# PLAN: order inquiry sheet - adopt the sheet row as a superseded row's replacement's Was

Status: Track: small fix - ready for PR review. Follow-up to `PLAN-oi-sheet-date-settled-
rows.md` (#1011, MERGED). Lane worktree `sorento_crm-oi-sheet-date`, branch
`fix/oi-sheet-date-adopt-was`. DB `sorento_oisd_ci`. Backend only.

UAC: `oi-sheet-date-adopt-was-acceptance-criteria.md`.

## Review round 2 (19 Sep 2026, Opus reviewer, head d5187594a)

Four findings against round 7's own shape C, closed in this same lane, no re-scope of the
rule itself:

* **BLOCKER, anchored note edit actually drops the tail.** The `apply()` write used
  `existing_note.find("Was ")` plus `existing_note[:was_at].rstrip("; ")` to rebuild the
  prefix - which discards EVERYTHING after the old fragment. A live row whose note also
  carried a linkage probe's own tail (`"; Linked to 202603-S0109 (...); auto: autocount
  linkage"`) lost it. Fixed with `re.search(r"Was \S+ on \d{4}-\d{2}-\d{2}", note)` and an
  in-place splice (`note[:start] + fragment + note[end:]`) - append only when no fragment
  exists at all.
  `test_shape_c_note_edit_is_anchored_replacing_not_appending` now puts prose on BOTH sides
  of the fragment and pins the tail byte for byte.
* **S1, sibling identity was note/quantity alone.** Any CANCELLED row on the mirror whose
  `qty` or `previous_qty` happened to equal the sheet's quantity counted as the migrated
  sibling, so a cancelled BOARD row (never raised by an upload) could false-positive. Fixed
  by narrowing the sibling pool to rows `import_job_rows` itself records as CREATED by this
  feature (`entity_type = 'order_inquiry_row' AND outcome = 'created' AND entity_id =
  str(row.id)`) - the durable record `ImportOutcome.success(...)` already writes for every
  row it raises, and the ONLY identity a superseded row's overwritten note can no longer
  provide. One extra query per upload over the cancelled candidate ids on the SAME round
  trip (never per-row), skipped when there are no cancelled candidates at all. **No index
  exists on `import_job_rows (entity_type, entity_id)`** - confirmed against the schema
  (`ix_import_job_rows_import_job_id`, `_job_code`, `_job_outcome`, `_job_row`,
  `_created_at`, none of them cover `entity_type`/`entity_id`). Not added in this lane
  (small fix track, no migrations); a follow-up if a full-book re-upload's cancelled-row
  count makes this scan measurably slow. AC-26 rewritten (`_cancelled_board_row`, a
  look-alike cancelled row never registered in `import_job_rows`) so it tests the identity
  gate itself rather than a quantity mismatch (AC-27's own case).
* **S2, live-row pairing was a coin flip.** `_resolve_shape_c_repairs` picked the live row
  by `unclaimed_live` LIST POSITION (`next(c for c in unclaimed_live if item matches)`), and
  `created_at` ties inside one transaction left the `id` tiebreak effectively random.
  Fixed: paired by the MATCHED sibling's own `qty` first (prod's own shape - sibling `qty`
  220, live `qty` 220), falling back to item-only only when nothing carries that quantity.
  `test_shape_c_pairs_by_sibling_identity_not_file_position` rewritten to assert WHICH live
  row gets WHICH Was (not merely that both resolve), run 10/10 locally.
* **S3, claim-once had three surviving mutants.** All three were already correct in code
  (the `already_claimed` skip and both pool `.remove()` calls), but nothing pinned them.
  Five new regression tests close the gap: `test_shape_c_claims_each_pool_at_most_once` (two
  sheet rows, one sibling, one live row - only the first adopts),
  `test_shape_c_never_reclaims_a_row_shape_a_already_repaired` (a sheet row shape A already
  repaired is never also handed to shape C),
  `test_shape_c_claims_the_live_pool_at_most_once` and
  `test_shape_c_claims_the_sibling_pool_at_most_once` (each isolates ONE of the two
  `.remove()` calls - a single "two rows, one sibling, one live row" test cannot catch both
  independently, since the sibling lookup gates the live lookup and masks a dropped
  `unclaimed_live.remove`).
* **NIT.** `test_shape_c_adopts_even_when_the_lives_own_qty_equals_the_sheet_qty` states the
  existing (correct) rule explicitly: a live row whose OWN `qty` happens to equal the
  sheet's quantity still adopts the Was when the date differs.

## What was measured (round 7, revised after a prod `SELECT`)

The first cut of this plan (round 6) guessed the shape from the symptom alone: a migrated
row `changed_at IS NOT NULL` but with no Was recorded. That guess was WRONG - a prod
`SELECT` for SO314593 showed the shape does not occur. What is actually there:

```
CB2806A-DIY 220 cancelled acknowledged changed_at 2026-09-17 02:11 previous_qty 182
  previous_delivery_date 2027-03-01 created 2026-09-15 16:29 note "Superseded by revision 2"
CB2806A-DIY 220 raised awaiting changed_at 2026-09-17 03:25 previous NULL created
  2026-09-17 03:25 note empty
SRTWB245: identical pair (280, 182 @ 2027-03-01 on the cancelled migrated row).
```

The first row is the MIGRATED row: settled in place once (its own Was, `previous_qty` 182 /
`previous_delivery_date` 2027-03-01 - 7.4's date, the line's `required_date`), then a
SECOND reconfirm (revision 2) CANCELLED it and raised the SECOND row - a fresh LIVE row,
board-raised, no migration stamp, no Was of its own at all. `_settle_row_in_place`'s cancel
path REPLACES the note with `"Superseded by revision N"` rather than appending to it (`row.
note = f"Superseded by revision {decision.revision_no}"`), so the CANCELLED row can never be
found by the migration stamp again - only by its own quantity.

The sheet's 182 @ 1.6.2026 describes the Was the CANCELLED row already had, but the LIVE
row that replaced it never got one - it is a fresh row, not a migrated one, so nothing
about the original migration mistake ever touched it. Both re-uploads (#1004's and #1011's)
skipped the live row as `already_raised` (correctly - shapes A and B both require the
migration stamp) and never touched the cancelled row (correctly - both require the row to
be live).

## The rule, for the owner

**A live row that replaced a superseded migrated row adopts the sheet row as its Was; its
Now stays the book's.**

## The change

A third repair shape, resolved in the SAME pure step (`_resolve_delivery_date_repairs`,
inside `_plan`) and written in `apply`, alongside the existing two:

* **Shape A / Shape B (existing, unchanged)** - both still require the migration stamp and
  `changed_at IS NULL` (shape A) exactly as #1004 shipped; restored explicitly in this
  round after the (deleted) round-6 shape briefly loosened shape A's own check.
* **Shape C (rewritten).** A sheet row landing on an already-raised line whose LIVE row
  (state not cancelled, ANY origin, no migration stamp required) has `previous_qty IS NULL
  AND previous_delivery_date IS NULL` and `delivery_date == line required_date`, where the
  SAME MIRROR also carries a CANCELLED row whose own `qty` (never settled before being
  superseded) OR `previous_qty` (settled once, then superseded) equals the sheet's
  quantity -> the LIVE row adopts `previous_qty = sheet qty`, `previous_delivery_date =
  sheet date`, and the note gains (or, if it already carries a `"Was ... on ..."`
  fragment, has REPLACED) `"Was {qty_str(sheet qty)} on {sheet date}"`. The live row's
  `delivery_date`, `qty` and `ack_state` are untouched; the cancelled row is read, never
  written.

  The cancelled sibling can NEVER be identified by the migration stamp (the cancel path
  overwrites the note), so it is identified by QUANTITY alone, and the pairing between a
  sheet row and a live row is made through that sibling's own identity - never by file or
  creation position (round 7 review: two live rows and two cancelled siblings of the same
  item, with the sheet's own rows in the REVERSE order of the siblings' own creation, must
  still each resolve through the sibling whose own quantity actually matches).

**Resolution order per mirror: shape A, then B, then C, claim-once across all three** - a
sheet row claims at most one live row, a live row is claimed by at most one sheet row, ONE
live row per cancelled sibling (the sibling is claimed too, so a second sibling with the
SAME quantity is what a second live row needs), `created_at, id` order throughout. Shape
A's and shape C's live-row candidate pools are built to be MUTUALLY EXCLUSIVE (a row
genuinely eligible for shape A is never also offered to shape C), closing a flaky
double-claim this round's own review caught before it shipped: a row shape A had already
committed to repairing for one sheet row could otherwise still appear in shape C's pool and
be handed to a different sheet row, with `id`-ordering deciding which run it happened on.

Shape C has no pass-1 no-op of its own: a row whose `previous_qty` is already non-`NULL`
falls out of the eligibility precondition itself before any matching runs, so idempotency
is structural, not a check - `test_ac_28...` (a re-upload of the SAME file, once adopted)
and `test_shape_c_adoption_at_the_required_date_is_still_idempotent` (a HARDER case: the
sheet's own date happens to equal the line's `required_date`, so a naive reading might
expect shape B to see it on the second run - it does not, because the live row was never
stamped, so it never enters shape B's own pool either) both pin this.

**Outcome.** Reuses `DELIVERY_DATE_UPDATED` with message "Was adopted from the sheet
(migrated row superseded)" (the same reasoning as shape B's own message: `ImportOutcome`
labels its aggregate breakdown off the code alone, never the per-row message, so the tile
and the `validate()` warning count all three shapes under one code). `rows_delivery_date_
updated` already sums every match with a `repair_row_id` set, so shape C is counted
automatically and forecast by `preview` the same way shapes A and B are.

**Query cost.** One extra column-set on the SAME round trip, not a second query: the
existing per-mirror query now also fetches CANCELLED rows (needed for shape C's sibling
lookup, since their note can never be trusted) and the `state`/`note` columns needed to
classify everything in Python, in place of the SQL-side `state != CANCELLED` / `note LIKE
stamp%` filters the earlier rounds used - both of those filters would have wrongly excluded
rows shape C now legitimately needs. **Review round 2 (S1) added a genuine second query**:
one `import_job_rows` lookup over the cancelled candidate ids collected in the first query,
run once per upload (not per mirror, not per row), skipped entirely when a run raises no
cancelled candidates at all. No index covers `import_job_rows (entity_type, entity_id)` -
noted as a follow-up, not built here (small fix track, no migrations in this lane).

**No frontend change.**

## Files touched

* `app/services/project_order_inquiry_import_service.py` - `_resolve_shape_c_repairs`
  rewritten entirely (live row + cancelled sibling, not a single stamped row);
  `_resolve_delivery_date_repairs`'s query widened to also fetch cancelled rows and the
  `state`/`note` columns, classification rewritten so shape A's and shape C's live pools
  are mutually exclusive and shape A's `changed_at IS NULL` guard is explicit again;
  `apply()`'s already-raised branch's shape-C write path rewritten (anchored note
  replace-or-append, new message). Review round 2: `_resolve_delivery_date_repairs` narrows
  the cancelled candidate pool to rows `import_job_rows` records as CREATED (S1);
  `_resolve_shape_c_repairs` pairs the live row by the matched sibling's own `qty` first
  (S2); the note splice in `apply()` uses a regex anchor and preserves the tail (BLOCKER).
* `tests/test_oi_sheet_date_follow_sheet.py` - review round 2: `_register_migrated` +
  `_cancelled_board_row` helpers; `_cancelled_sibling` now registers itself in
  `import_job_rows`; AC-26 rewritten around a look-alike unregistered cancelled row;
  `test_shape_c_pairs_by_sibling_identity_not_file_position` asserts which live row got
  which Was; `test_shape_c_note_edit_is_anchored_replacing_not_appending` extended with
  prose on both sides of the fragment; five new tests
  (`test_shape_c_claims_each_pool_at_most_once`,
  `test_shape_c_never_reclaims_a_row_shape_a_already_repaired`,
  `test_shape_c_claims_the_live_pool_at_most_once`,
  `test_shape_c_claims_the_sibling_pool_at_most_once`,
  `test_shape_c_adopts_even_when_the_lives_own_qty_equals_the_sheet_qty`).
* `tests/test_oi_sheet_date_follow_sheet.py` - the round-6 `_restated_row` helper and its
  AC-25 to AC-29 deleted entirely (the shape never occurs); `_cancelled_sibling` +
  `_live_row` helpers (new); AC-25 to AC-29 rewritten for the real shape; three more reds
  from review (sibling-identity-not-position, anchored note replace, idempotent at the
  required date); `test_ac_11`'s own fixture adjusted (its live row's date no longer
  coincides with the line's `required_date`) so it stays an isolated test of "a cancelled
  row is never repaired" rather than accidentally also exercising shape C.
* `documentation/user-guides/supply-chain/upload-plan-data.md` - one clause on the
  re-upload sentence.
