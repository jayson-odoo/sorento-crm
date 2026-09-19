# PLAN: order inquiry sheet - follow the sheet's own delivery date

Status: shipped (merged in #1004, 18 Sep 2026)

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

**N4 - the repair is confined to 7.4's own artefacts, from whichever upload wrote them.**
Superseded by S8 below (fix round 2): a later sheet may still correct a row 7.4 wrote under
an EARLIER, differently named upload, but ONLY while that row still carries 7.4's own
fingerprint. AC-4 (below) uploads the migration under one file name and the correction
under a different one, to keep the cross-file point visible rather than assumed.

**Environment note.** Round 1 created and bootstrapped `sorento_oisd_ci` for its own DB
after discovering the `.env`'s original `sorento_oibf_ci` did not exist locally and
building it from `python -m scripts.bootstrap_env` - that database belongs to the #1003
lane (`PLAN-oi-was-now-backfill`, not yet in this checkout under that name) and was
schema-empty before this lane's bootstrap ran against it. Fix round 1 moved this lane onto
its own `sorento_oisd_ci` and left `sorento_oibf_ci` alone from then on; the #1003 lane
should confirm its own database is still what it expects.

## Fix round 2, 19 Sep 2026 (Opus review round 2, NOT READY - one blocker)

**B3 - `_resync_sibling_was_now` matched on the mirror alone, so it rewrote EVERY
non-cancelled sibling whose `previous_delivery_date` differed from the newly-computed
earliest, including a sibling whose Was/Now came from an UNRELATED event on the same
mirror, and its note edit was an unanchored `note.replace("on <old>", ...)` that also
falsified an `"AutoCount moved <doc> to <SO> on <date>"` provenance line
`orderInquiryAck.ts` reads by prefix.** Fixed by capturing `old_earliest` and
`old_total_qty` - the mirror's `redirected_to_pool` migrated rows' earliest date and total
quantity - BEFORE the run writes any repair to that mirror (`apply`'s `before_repair`
dict, one snapshot per mirror, taken at the FIRST repair touching it). After the repair,
only a sibling whose OWN `(previous_delivery_date, previous_qty)` is EXACTLY
`(old_earliest, old_total_qty)` - the precise pairing
`ProjectOrderInquiryService`'s writer (~1093-1098) produced - is touched, and the note
edit is anchored to the fragment `f"Was {qty} on {old_earliest}"` -> `f"Was {qty} on
{new_earliest}"`, replaced once, never a bare date substring.

**S7 - the three B2 markers are each tested alone.** `test_ac_9b_each_b2_marker_alone_blocks_the_repair`
parametrizes over `previous_qty` / `previous_delivery_date` / `changed_at`, setting exactly
ONE per case (the migrated row's own `delivery_date` is left AT the line's `required_date`,
so S8's own gate cannot be why the repair is blocked) - catching a mutant that keeps two of
the three filter conditions and drops one.

**S8 - the repair is confined to 7.4's own artefacts.** *Eligible only when the migrated
row's `delivery_date` still equals its core sales order line's `required_date` - that is
exactly what section 7.4 wrote, and nothing else does. A row that already carries a date
the line does not (a sheet date raised under this fix, or one a person edited) is never
rewritten by a later sheet: the sheet is a migration, not a second opinion.* One `OR`-of-
per-line-equality clause in `_resolve_delivery_date_repairs`'s own query (S10), not a Python
filter. `test_ac_15_a_row_not_on_the_lines_required_date_is_never_repaired` is the red: a
migrated row raised under THIS fix's own rule (so its date already differs from the line's
required date) is never touched by any later sheet, however it moves the date.

**S9 - `_resolve_line_repairs`'s own pure-function contract is pinned DB-free**, and the
resolver's own `ORDER BY` is pinned separately with a DB red. `_resolve_line_repairs` takes
no database and does not re-derive `created_at`/`id` - it trusts the sequence it is handed,
proven by feeding it the SAME two candidates in opposite order and getting opposite
resolutions (`test_resolve_line_repairs_trusts_the_callers_own_order`), and that pass 1
settles exact matches before pass 2 ever runs regardless of that order
(`test_resolve_line_repairs_pass_one_settles_exact_matches_first`). Separately,
`test_ac_16_the_eligible_query_orders_by_created_at_then_id` inserts two migrated rows
with their `created_at` deliberately set OPPOSITE to insertion order and asserts the
resolution still repairs the one with the EARLIER `created_at` - pinning
`_resolve_delivery_date_repairs`'s own `ORDER BY created_at, id`, which `_resolve_line_repairs`
itself has no opinion about.

**S10 - pushed into SQL.** `_resolve_delivery_date_repairs`'s query now carries the S8
equality clause (one `and_(so_line_id ==, delivery_date ==)` per already-raised line,
`OR`'d together), the migration-stamp filter (`note.like(f"{_MIGRATION_STAMP}%")`) and all
three B2 `IS NULL` markers in ONE `WHERE`, and selects only the five columns the resolver
reads (`with_entities`) instead of hydrating full ORM rows - a book re-upload can touch all
of `scm.order_inquiry_row`'s roughly 11.8k migrated rows.

**N6 - no frontend change this round** (the 8-tile grid from fix round 1 stands).

## Fix round 3, 19 Sep 2026 (Opus review round 3, READY - last small round)

**S13 - the S8 clause moved out of SQL.** The `OR`-of-per-line-equality clause from S10
built one `and_(so_line_id ==, delivery_date ==)` per already-raised MIRROR; at prod scale
(11,500 already-raised mirrors on a full book re-upload) that is a roughly 1.1 MB SQL
statement, and `delivery_date` carries no index, so Postgres fell back to a Seq Scan
(measured 753 ms) instead of the index scan `so_line_id.in_(mirror_ids)` alone gets. Fixed:
the WHERE keeps only `so_line_id.in_(mirror_ids)` (indexed) plus the B2/stamp filters; the
S8 equality against `required_date_by_mirror` moved to a plain Python comparison over the
already-projected `delivery_date` column (already in the `with_entities` list, and the map
was already built) while grouping the rows into `migrated_by_mirror`. One query, same
result, the index intact. `test_ac_15_...` still red under "drop the equality" - it is now
a Python `if`, not a SQL clause, but the same behaviour it guards.

**S12 - three fixture-guard mutants closed.** `test_ac_14a_...` now seeds FOUR siblings
on one mirror instead of one: the MATCHED sibling's own note carries an "AutoCount moved
... on <old_earliest>" provenance line at the SAME date the repair moves, so the anchored
edit's own precision is asserted (the provenance line survives verbatim; only the "Was ...
on" fragment moves) rather than merely assumed; a sibling sharing the matched sibling's
`previous_qty` but a DIFFERENT `previous_delivery_date` is asserted untouched; a sibling
sharing the matched sibling's `previous_delivery_date` but a DIFFERENT `previous_qty` is
asserted untouched too - closing three mutants that survived the round 2 test as written
(each near-miss on only one of the two fields, rather than both).

**N7 - a comment, not a mechanism.** The `_qty_str` import in `_resync_sibling_was_now`
now says why the private name is deliberate: the note prose has to match the writer's own
formatting byte for byte, so reusing it is what keeps the two paths from drifting.

**N8 - one query, not one `db.get` per repaired row.** `apply()` now gathers every
`match.repair_row_id` before the loop and loads them in a single
`filter(OrderInquiryRow.id.in_(...))`, keyed by id in a dict the loop reads from - five
lines, replacing the per-row `db.get` the loop used to make.

## Round 4: text dates in the book (19 Sep 2026, found running the real book through the
lane stack)

`JAN - DEC 2026 ORDERabc.xlsx` run end to end: SO314593's rows were skipped as
`ALREADY_RAISED`, not repaired. Root cause is UPSTREAM of every change above, in
`app/services/project_order_inquiry_reader.py`'s `_as_date` (line ~104 before this round):
it answers `None` for anything that is not already a Python `datetime`/`date` object, and
the real book stores some `DELIVERY DATE` cells as literal TEXT rather than an Excel date.
SO314593's own JUNE rows write the cell as the string `1.6.2026`, so `row.delivery_date`
was already `None` at the ORIGINAL migration (the line's date fallback fired regardless of
7.4 - this plan's own reversal never touched that path) and is still `None` today - an
undated row correctly claims nothing (AC-10), so the repair correctly declined it, on a
row that was never given a date to compare against in the first place.

Measured over all 38 tabs of the real file's `DELIVERY DATE` column: 15,833 real Excel
dates; text shapes `1.3.2026` (67 cells, d.m.yyyy), `1.12.2026` (14, d.mm.yyyy),
`30-04-2026` (11, dd-mm-yyyy), and one `27/10//2026` typo (a doubled slash); non-dates that
must stay `None`: the existing `ORDER BACK ...` variants, `MARCH - APRIL 2026` (31, a
range, not a date), `ASAP` (5), `WAREHOUSE MISSING`, `STOCK TAKE ADJUST`.

**Change (reader only):** `_as_date` now also parses a TEXT cell as a DAY-FIRST date when
it matches `^\s*(\d{1,2})[./-](\d{1,2})[./-]+(\d{4})\s*$` - the trailing `+` tolerates the
`//` typo. Day-first because every one of the measured cells reads that way (`1.3.2026` is
1 March, never 3 January), and a two-digit year is not matched since none appears in the
book. An impossible date (e.g. month 13) still answers `None` rather than raising. The
same helper serves `so_date`, so a text SO DATE cell parses the same way. Nothing in the
importer (`project_order_inquiry_import_service.py`) changes - a text-dated row now simply
carries a real `delivery_date`, so this plan's own matcher and repair rules apply to it
exactly as they do to an Excel-dated row: `_line_sort_key`'s "line whose `required_date`
equals the sheet's" term and `_restates` both now see it. The whole importer family (200
tests: everything this plan's fix rounds 1-3 touch, plus the reader's own suite) was
re-run to confirm nothing pairs differently.

## Files touched

* `app/services/project_order_inquiry_reader.py` - `_as_date` parses a day-first text date
  (round 4).
* `app/services/project_order_inquiry_import_service.py` - the delivery-date assignment;
  `_already_raised` (now also returns the mirror map), `_resolve_line_repairs`,
  `_resolve_delivery_date_repairs` (S8 as a Python comparison per S13, S10's other three
  filters + column projection still in SQL), `_redirected_earliest_and_qty`,
  `_resync_sibling_was_now` (B3 rewrite, N7 comment); the apply-loop branch (`before_repair`
  snapshot, N8's bulk preload); the `_result` / `validate` summary line. `_mirror_of` and
  the first round's `_repair_migrated_date` are gone, superseded by the above.
* `app/services/import_outcome_codes.py` - `DELIVERY_DATE_UPDATED` code + label.
* `tests/test_project_order_inquiry_import_reader.py` - `_as_date` text-date parametrize
  (AC-17, round 4).
* `tests/test_oi_sheet_date_follow_sheet.py` (new, round 1; extended rounds 2, 3 and 4) -
  AC-1 to AC-18, plus two DB-free unit tests for `_resolve_line_repairs`.
* `tests/test_oi_sheet_pairing_repair.py` - `test_ac_r_37_...` rewritten for the reversed
  rule.
* `tests/test_project_order_inquiry_import_migration.py` - `RESULT_KEYS` gains
  `rows_delivery_date_updated`.
* `sorento_crm_frontend/app/(protected)/scm/reorder/services/orderInquiryService.ts` -
  `OrderInquiryPreview.rows_delivery_date_updated` (fix round 1).
* `sorento_crm_frontend/app/(protected)/scm/reorder/components/OrderInquiryUploadDialog.tsx`
  - the "Dates corrected" tile (fix round 1, untouched since per N6).
* `sorento_crm_frontend/app/(protected)/scm/reorder/components/OrderInquiryUploadDialog.test.tsx`
  - fixture + tile-count assertions updated for the eighth tile (fix round 1).
* `documentation/user-guides/supply-chain/upload-plan-data.md` - the DELIVERY DATE bullet
  gained the text-date clause (round 4).
