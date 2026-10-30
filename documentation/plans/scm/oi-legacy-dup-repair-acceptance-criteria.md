# UAC: OI-LEGACY-DUP-REPAIR

Plan: `PLAN-oi-legacy-dup-repair-30oct.md`.

- **AC-1 detect.** A sheet-import row that duplicates another row of the same job and tab, sits on
  a line whose qty and date both differ from the sheet, and whose line's own later sheet row was
  skipped `already_raised` is reported as a squatter, with both sheet rows and the skipped row.
- **AC-2 no false positive: per-line repeat.** Two identical sheet rows on one tab, each on its own
  line whose qty equals the sheet qty (only the date differs), are NOT reported.
- **AC-3 no false positive: no skipped row.** A duplicate on a mismatched line with no skipped
  `already_raised` row for that line is NOT reported.
- **AC-4 no false positive: skipped row names another qty.** A skipped row whose qty is not the
  line's qty does not count as evidence.
- **AC-5 restate.** `--apply` sets a restate-eligible squatter's qty and date to the skipped row's,
  writes `previous_qty` / `previous_delivery_date`, appends a note, and flips `acknowledged` to
  `changed` with `changed_at` set; an `awaiting` row stays `awaiting`. The sibling row is untouched.
- **AC-6 hold.** A cancelled, linked, actioned, edited-since-import, reserve-requested or bundled
  squatter, and one sharing its line with another live row (two copies on one line, or a real
  instruction beside it), is reported with its reason and never written.
- **AC-7 dry run writes nothing.** Without `--apply` no row changes.
- **AC-8 count guard.** `--apply` with an `--expect` that differs from the restate count found
  refuses and writes nothing.
- **AC-9 idempotent.** A second `--apply` restates nothing.
- **AC-10 audit.** Each restated row gets one audit EVENT with old and new qty / date.
