# PLAN: order inquiry sheet - follow the sheet's own delivery date

Status: Track: small fix - in review. Reverses section 7.4 of
`PLAN-scm-oi-sheet-pairing-repair.md`. Lane worktree `sorento_crm-oi-sheet-date`, branch
`fix/oi-sheet-date-follow-sheet`, PR #1004. DB `sorento_oisd_ci` (its own; `sorento_oibf_ci`
belongs to the #1003 lane and was not touched again after the first round's mistake).
Backend + a one-line frontend type/tile addition (S4, fix round 1).

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
   already raised, the resolution decided in `_plan` (see "Fix round 1" below) either names
   a MIGRATED row to repair or names none. Repairing moves that row's `delivery_date` to the
   sheet's own and, where it is `redirected_to_pool`, recomputes any sibling's Was/Now.
   Reported with its own outcome code, `DELIVERY_DATE_UPDATED`, and a new
   `rows_delivery_date_updated` counter beside `rows_already_raised` in the result. Links,
   quantities, state and ack fields are never touched. Idempotent: a second run of the same
   file, once the migrated row is already on the sheet's date, changes nothing and reports
   `ALREADY_RAISED` again.

No new table, no new endpoint, no migration. The result contract grows one key
(`rows_delivery_date_updated`); the shared `RESULT_KEYS` contract test
(`tests/test_project_order_inquiry_import_migration.py`, AC-S1-22) is updated in the same
change. A frontend tile for it was added in fix round 1 (S4).

## Fix round 1, 19 Sep 2026 (Opus review, NOT READY on the first round)

Two blockers and five shoulds. The rule sentences, as the reviewer asked to have them
stated here:

**B1 - repair candidates are resolved per LINE, not per row.** A migrated row's own item
code and quantity is not a unique key: a sheet that splits one line's quantity across
several dated rows (100 @ 2026-09-01 + 100 @ 2026-10-01, one line) leaves several migrated
rows sharing both - 116 `(mirror, item, qty)` groups / 233 migrated rows on the 15 Sep prod
copy alone - and resolving row-by-row with no ordering let an unchanged re-upload overwrite
September's row with October's date and flip the pair back on every further run, converging
on nothing. The fix: for each already-raised core line, collect the sheet rows of THIS file
landing on it (in file order) and the non-cancelled, unrestated migrated rows on its mirror
(ordered by `created_at`, `id`). Pass 1 lets a sheet row claim a migrated row with the same
item, quantity AND date as a no-op (both already agree). Pass 2 lets each sheet row pass 1
left unclaimed claim the first STILL-unclaimed migrated row with the same item and quantity
(whatever its date) and repairs it. A migrated row is claimed at most once per run, by at
most one sheet row, so two same-qty rows can never both point at a row the other pass
already gave away. Implemented in `_resolve_line_repairs` (pure, deterministic, no database
access) plus `_resolve_delivery_date_repairs` (gathers its inputs, one query per upload for
every already-raised line's siblings).

**B2 - the repair touches only a migrated row that no planning change has restated since
migration: `previous_qty IS NULL`, `previous_delivery_date IS NULL`, `changed_at IS NULL`.
A row a change settled keeps the change's date.** 5,793 of 11,810 migrated rows on the 15
Sep prod copy already carry a link, and SO314593's own rows are linked, received, some
redirected to the pool - "already raised" cannot mean "untouched by purchasing". No
handshake stamp is written by the repair (no `changed_at`, no `ack_state` flip): this is a
data repair of the MIGRATION's own mistake, not a second opinion about a decision
purchasing has since made, and purchasing already works to the sheet's date either way.
Implemented as the eligibility filter inside `_resolve_delivery_date_repairs`'s own query.

**S1 - `preview` forecasts the repair.** `_resolve_delivery_date_repairs` runs as a PURE,
read-only step inside `_plan` (never inside `apply`), storing the candidate migrated row id
on `_Match.repair_row_id`. `rows_delivery_date_updated` in `_result` is read off
`plan.matches` (`sum(1 for m in plan.matches if m.repair_row_id)`) rather than a
caller-supplied count, so `preview` and `apply` cannot report different numbers for the
same file, and `validate`'s "left alone" warning line now excludes the rows that will be
repaired rather than double-counting them.

**S3 - one query, not one per row.** `_already_raised` now also returns the core-line ->
mirror-id map it already builds internally, stashed on `_Plan.mirror_by_core_line`, so
`_resolve_delivery_date_repairs` never re-queries it, and every already-raised line's
migrated siblings are loaded in ONE query (grouped by mirror) rather than one per row. The
first round's `_mirror_of` (a per-row `SELECT`) is gone.

**S5 - a sibling's Was/Now recomputes from the mirror's `redirected_to_pool` migrated rows,
not from a qty/date match against the one row just repaired.** `ProjectOrderInquiryService`'s
own writer (~1093-1098, AC-OH-40..42) stamps a fresh row's `previous_qty` as the SUM of the
rows a redirect released and `previous_delivery_date` as the EARLIEST of their dates. A
repair never changes what a row replaced - `previous_qty` is left alone - it only
recomputes the EARLIEST date over the mirror's currently-`redirected_to_pool` migrated rows,
using their (possibly just-repaired) dates, and writes it onto every non-cancelled sibling
that already carries a `previous_delivery_date`, correcting the note's own "on <date>"
prose to match. Implemented in `_resync_sibling_was_now`, called once per mirror a repair
touched, after the apply loop's main pass (never inline, since a line's second dated row can
still repair a sibling migrated row on the SAME mirror later in the same loop).

**S4 - frontend.** `OrderInquiryPreview` (`orderInquiryService.ts`) gained
`rows_delivery_date_updated`; the preview panel already renders `rows_already_raised` as a
`CountTile`, so a matching "Dates corrected" tile was added beside it (eight tiles now, was
seven).

**S2 - two more guards, each with its own red.** An undated sheet row (ORDER BACK, or a
blank cell) is excluded from the resolution entirely before pass 1 ever runs, so it can
neither claim nor blank a migrated row's date. A CANCELLED migrated row is excluded by the
same `state != INQUIRY_CANCELLED` filter `_already_raised` itself already applies, so it is
never a repair candidate even when it is the only quantity match on the line.

**N4 - the repair is not scoped to the uploading file.** Any sheet may correct a row
migrated from an EARLIER, differently named upload - there is nothing in the resolution
that reads `file_name`, only the mirror's current rows. AC-4 (below) uploads the migration
under one file name and the correction under a different one, to keep this visible rather
than assumed.

**Environment note.** Round 1 created and bootstrapped `sorento_oisd_ci` for its own DB
after discovering the `.env`'s original `sorento_oibf_ci` did not exist locally and
building it from `python -m scripts.bootstrap_env` - that database belongs to the #1003
lane (`PLAN-oi-was-now-backfill`, not yet in this checkout under that name) and was
schema-empty before this lane's bootstrap ran against it. Fix round 1 moved this lane onto
its own `sorento_oisd_ci` and left `sorento_oibf_ci` alone from then on; the #1003 lane
should confirm its own database is still what it expects.

## Files touched

* `app/services/project_order_inquiry_import_service.py` - the delivery-date assignment;
  `_already_raised` (now also returns the mirror map), `_resolve_line_repairs`,
  `_resolve_delivery_date_repairs`, `_resync_sibling_was_now`; the apply-loop branch; the
  `_result` / `validate` summary line. `_mirror_of` and the first round's
  `_repair_migrated_date` are gone, superseded by the above.
* `app/services/import_outcome_codes.py` - `DELIVERY_DATE_UPDATED` code + label.
* `tests/test_oi_sheet_date_follow_sheet.py` (new, round 1; extended round 2) - AC-1 to
  AC-13.
* `tests/test_oi_sheet_pairing_repair.py` - `test_ac_r_37_...` rewritten for the reversed
  rule.
* `tests/test_project_order_inquiry_import_migration.py` - `RESULT_KEYS` gains
  `rows_delivery_date_updated`.
* `sorento_crm_frontend/app/(protected)/scm/reorder/services/orderInquiryService.ts` -
  `OrderInquiryPreview.rows_delivery_date_updated`.
* `sorento_crm_frontend/app/(protected)/scm/reorder/components/OrderInquiryUploadDialog.tsx`
  - the "Dates corrected" tile.
* `sorento_crm_frontend/app/(protected)/scm/reorder/components/OrderInquiryUploadDialog.test.tsx`
  - fixture + tile-count assertions updated for the eighth tile.
