# PLAN: order inquiry sheet - follow the sheet's own delivery date

Status: Track: small fix - building. Reverses section 7.4 of
`PLAN-scm-oi-sheet-pairing-repair.md`. Lane worktree `sorento_crm-oi-sheet-date`, branch
`fix/oi-sheet-date-follow-sheet`, DB `sorento_oibf_ci`. Backend only.

UAC: `oi-sheet-date-follow-sheet-acceptance-criteria.md`.

## What was measured

Owner ruling, 18 Sep 2026: "we should have followed the sheet's date." Facts measured on a
prod copy: SO314593's open AutoCount lines are 220 @ 2027-03-01, and the operator's sheet
said 182 @ 1.9.2026 for the same instruction.

Section 7.4 of `PLAN-scm-oi-sheet-pairing-repair.md` made the raised row's `delivery_date`
read the SALES ORDER LINE's `required_date` over the sheet's own, falling back to the
sheet's only when the line carried none:

```python
delivery_date = match.core_line.required_date or row.delivery_date
```

That is why the worklist read 01/03/2027 for a delivery purchasing had actually agreed to
move to 1.9.2026 in the sheet, and why the Was/Now `(i)` on the fresh 220 row (backfilled
from the migrated 182 row by a one-off script, PR #1003) printed the same wrong date
twice - the backfill copied the migrated row's own stale date, and nothing had ever
written the sheet's.

A second problem, orthogonal to the rule itself: a re-upload of the corrected sheet did
nothing. `_already_raised` (`app/services/project_order_inquiry_import_service.py`) skips
any line whose mirror already carries a non-cancelled row - correctly, the sheet is a
migration and must not raise the same instruction twice (D2) - but skip and "leave the
existing row untouched forever" had always been the same code path, so a migrated row's
date, once wrong, stayed wrong no matter how many times the sheet was fixed and
re-uploaded.

## The two changes

1. **The row's delivery date is the sheet's own** (`raise_row`,
   `project_order_inquiry_import_service.py`): `delivery_date = row.delivery_date or
   match.core_line.required_date`. An ORDER BACK row's date cell carries words, never a
   date, so `row.delivery_date` is `None` and the line's own date stands, unaffected by
   this reversal - `verb` is what already says the quantity is owed against something
   already ordered. The sheet's date still decides which line a row matches and whether two
   rows restate one instruction (the restatement key and the "date equals the sheet's"
   rank term are both untouched); only what the raised row REPORTS changes.

2. **A re-upload repairs a migrated row's stale date.** In the apply loop, when a line is
   already raised, `_repair_migrated_date` looks for the MIGRATED row on that mirror line
   (`note` starts with the migration stamp), matching item code and quantity. If its date
   differs from the sheet's, the migrated row's `delivery_date` moves to the sheet's, and
   any sibling row whose `previous_qty` / `previous_delivery_date` mirror the migrated
   row's OLD figures (the Was/Now pair a backfill or a later planning change's
   `_settle_row_in_place` stamped from them) is corrected too, so the `(i)` stops printing
   the wrong date. Reported with its own outcome code, `DELIVERY_DATE_UPDATED`, and a new
   `rows_delivery_date_updated` counter beside `rows_already_raised` in the result. Links,
   quantities, state and ack fields are never touched. Idempotent: a second run of the same
   file, once the migrated row is already on the sheet's date, changes nothing and reports
   `ALREADY_RAISED` again.

No new table, no new endpoint, no migration, no frontend change. The result contract grows
one key (`rows_delivery_date_updated`); the shared `RESULT_KEYS` contract test
(`tests/test_project_order_inquiry_import_migration.py`, AC-S1-22) is updated in the same
change.

## Files touched

* `app/services/project_order_inquiry_import_service.py` - the delivery-date assignment,
  `_mirror_of` + `_repair_migrated_date` helpers, the apply-loop branch, the `_result` /
  `validate` summary line.
* `app/services/import_outcome_codes.py` - `DELIVERY_DATE_UPDATED` code + label.
* `tests/test_oi_sheet_date_follow_sheet.py` (new) - AC-1 to AC-7.
* `tests/test_oi_sheet_pairing_repair.py` - `test_ac_r_37_...` rewritten for the reversed
  rule.
* `tests/test_project_order_inquiry_import_migration.py` - `RESULT_KEYS` gains
  `rows_delivery_date_updated`.
