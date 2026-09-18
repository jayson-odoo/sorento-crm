# PLAN: order inquiry sheet - adopt the sheet row as a restated row's Was

Status: Track: small fix - ready for PR review. Follow-up to `PLAN-oi-sheet-date-settled-
rows.md` (#1011, MERGED). Lane worktree `sorento_crm-oi-sheet-date`, branch
`fix/oi-sheet-date-adopt-was`. DB `sorento_oisd_ci`. Backend only.

UAC: `oi-sheet-date-adopt-was-acceptance-criteria.md`.

## What was measured

Prod evidence, SO314593, measured after two re-uploads of the real book: `CB2806A-DIY`
(220) and `SRTWB245` (280) are migrated rows (note starts with the migration stamp) that a
BOARD CONFIRM restated in place BEFORE #992 deployed - 17 Sep 2026, 10:11 and 11:25 MYT
("Eling") - when nothing wrote `previous_qty` / `previous_delivery_date` for a restated
row yet. So both carry NO Was at all, `qty` 220/280 != the sheet's 182, `delivery_date`
== the line's `required_date`, and both re-uploads (#1004's and #1011's) skipped them as
`already_raised`.

## The mandatory verification

Whether `changed_at IS NOT NULL` is a trustworthy "the board restated this row" marker -
as opposed to "somebody just edited the sheet's quantity" - is what makes this rule safe
rather than a guess, so it was verified against git history before writing any code:

```
$ git log -S "changed_at" --oneline -- app/services/project_order_inquiry_service.py
624dc9797 feat(scm): order inquiries - confirm per SO (handshake back on)... (#991)
dfd2cda70 feat(oi): S1 auto-acknowledge - rows born acknowledged, reject only manual gate (#471)
78192f053 feat(scm): CS planning UAT build - board ladder v5, order-inquiry handshake... (#345)
```

`ProjectOrderInquiryService._settle_row_in_place` is the ONLY writer of `changed_at`
anywhere in that service (confirmed by `grep -n "changed_at\s*="`). Its shape at
`a3d215ab9` (the direct parent of `e91ec3614`/#992) and its CURRENT shape both write
`changed_at` in the exact same conditional block as `previous_qty` / `previous_delivery_
date` - the write has always been:

```python
if changed:
    row.note = f"{row.note}; {moved}" if row.note else moved
    row.previous_qty = previous_qty
    row.previous_delivery_date = previous_date
    if row.ack_state in (ACK_ACKNOWLEDGED, ACK_CHANGED):
        row.changed_at = datetime.utcnow()
        # ack_state target differs pre-/post-#991; the pairing with previous_qty/
        # previous_delivery_date does not.
```

So `changed_at` was, and still is, ALWAYS stamped together with `previous_qty` /
`previous_delivery_date` by this function - the pre-#992 settle DID stamp `changed_at` on
an acknowledged row, satisfying the check the owner asked for. What the prod rows show
(`changed_at` set, `previous_qty`/`previous_delivery_date` still `NULL`) is therefore a
state `_settle_row_in_place` does not produce directly by itself, in either version
inspected - something else (a rollback + re-raise, a different code path, or a manual
step) must have left `previous_qty`/`previous_delivery_date` unset while `changed_at`
survived. This plan does not attempt to reverse-engineer which: `changed_at` remaining
the ONLY writer in the service is what makes it safe to trust as "a planning change
restated this row" wherever it is found, regardless of the exact path that produced the
combination, and the owner's own ruling is to treat this combination as the fingerprint.
Not widened beyond what was asked.

## The rule, for the owner

**A migrated row the board restated before a Was was recorded adopts the sheet row as its
Was; its Now stays the book's.**

## The change

A third repair shape, resolved in the SAME pure step (`_resolve_delivery_date_repairs`,
inside `_plan`) and written in `apply`, alongside the existing two:

* **Shape A / Shape B (existing, unchanged).**
* **Shape C (new).** A migrated row (note carries the migration stamp) with `previous_qty
  IS NULL AND previous_delivery_date IS NULL`, `delivery_date == line's required_date`,
  `changed_at IS NOT NULL` (the restated-since-acknowledged marker), and the row's own
  `qty` differs from the sheet row's -> `previous_qty := sheet qty`,
  `previous_delivery_date := sheet date`; the note gains `"; Was {qty_str(sheet qty)} on
  {sheet date}"`, using the SAME fragment format `_settle_row_in_place`'s own writer uses,
  so the Was/Now table and the note agree. `delivery_date`, `qty`, `state` and `ack_state`
  are all untouched; no sibling resync (there was no Was pair for any sibling to have
  derived a resync from).

**Resolution order per mirror: shape A, then B, then C, claim-once across all three** - a
sheet row claims at most one row, a row is claimed by at most one sheet row, the same
`created_at, id` order shapes A and B already use. Shape C has no pass-1 no-op of its own:
a row whose `(previous_qty, previous_delivery_date)` already equal the sheet's is
impossible by the `NULL` precondition - once adopted, the row no longer carries
`previous_qty IS NULL` and drops out of the candidate pool on the next run entirely, which
is where idempotency comes from instead.

**Outcome.** Reuses `DELIVERY_DATE_UPDATED` with message "Was adopted from the sheet" (the
same reasoning as shape B's own message: `ImportOutcome` labels its aggregate breakdown
off the code alone, never the per-row message, so the tile and the `validate()` warning
count all three shapes under one code). `rows_delivery_date_updated` already sums every
match with a `repair_row_id` set, so shape C is counted automatically and forecast by
`preview` the same way shapes A and B are.

**No frontend change.**

## Files touched

* `app/services/project_order_inquiry_import_service.py` - `_Match.repair_shape` docstring
  widened for `"C"`; `_resolve_shape_c_repairs` (new); `_resolve_delivery_date_repairs`'s
  query gains `changed_at` to the projection and classifies shape A vs shape C by it;
  `apply()`'s already-raised branch gains the shape-C write path.
* `tests/test_oi_sheet_date_follow_sheet.py` - `_restated_row` helper (new); AC-25 to
  AC-29.
* `documentation/user-guides/supply-chain/upload-plan-data.md` - one clause on the
  re-upload sentence.
