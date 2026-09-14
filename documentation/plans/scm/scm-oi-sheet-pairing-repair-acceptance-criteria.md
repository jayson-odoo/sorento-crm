# Acceptance criteria: order inquiry sheet pairing repair

Companion to `PLAN-scm-oi-sheet-pairing-repair.md`. Every criterion is verified by a
pytest on Postgres (`tests/_pg_fixture.py`, `blank_session`), seeding its own chain.

## Journey

Same operator, same button as `scm-oi-sheet-migration-acceptance-criteria.md`. The one
thing that changes for them: the row the sheet raises lands on the sales order line the
cited purchase order actually names, and is linked to the purchase order or shipping order
AutoCount's own line reference states, whether or not any claim row was ever written for
it. A roll-up tab that repeats a month tab's row with a different remark raises nothing
extra.

Fixture vocabulary: "ref" = `sales_order_lines.source_ref` (e.g.
`AED_SORENTO:41576559:41604391`); a PO line or SPO allocation "names" a line when its
`from_so_line_ref` equals that ref.

## Slice S1, the importer [BE]

Pairing on the ref (R1)

* AC-R-1 Given a sheet row that matches a line, and a purchase order line for the same
  product that names that line, and NO `order_link_claim` row anywhere, when applied, then
  the raised row is linked to that PO line for `min(qty, PO line qty_ordered)`, the link is
  `auto` with trigger "autocount linkage", and the result counts it under
  `links_from_autocount`.
* AC-R-2 Given AC-R-1 plus an SPO allocation for the product with `from_po_number` = that
  PO's number, when applied, then the link lands on the SPO allocation first and the PO line
  takes only the remainder (D10 kept, reached through the ref).
* AC-R-3 Given an SPO allocation that names the line directly (`from_so_line_ref` on the
  allocation) AND a PO line that names it, when applied, then the SPO allocation is linked
  before the PO line.
* AC-R-4 Given the line has ONLY a `po_history` claim (no ref anywhere, no other claim),
  when applied, then the row is raised UNLINKED (`links_written` 0), and if the sheet cites
  a document that document is still tried as source 3.
* AC-R-5 Given the line has an `autocount` claim resolved to it (number-level, no ref on
  the purchase side), when applied, then that claim's target is linked (source 2 still
  works when AutoCount stated only the number).
* AC-R-6 Given a PO line A names the line and an `autocount` claim on the line points at PO
  line B, both with capacity for the whole need, when applied, then all of it lands on A
  and nothing on B.
* AC-R-7 Given a PO line that names the line but is already fully occupied by existing
  links (capacity 0), when applied, then it is skipped and the need falls through to the
  next source, exactly as the capacity rule already does.

Line pick (R2)

* AC-R-8 Given a sales order with two lines of the same item, both fitting the row's qty,
  line 1 with the earlier required date, and the sheet citing a PO whose line names line 2,
  when applied, then the row is raised against line 2 and linked to that PO line.
* AC-R-9 Given AC-R-8 but the cited document is an SPO whose allocation carries
  `from_po_number` = a PO whose line names line 2, when applied, then the row lands on
  line 2 (the chain read backwards).
* AC-R-10 Given two fitting lines, one `cancelled` and created earlier with the same
  required date, one `closed`, and no citation, when applied, then the row lands on the
  closed line. Given ONLY the cancelled line fits, it still matches (D1 kept).

Restatement (R3)

* AC-R-11 Given two sheet rows identical on SO, item, qty, delivery date and location but
  with different remarks (one cites a PO, the other blank; or two different remarks), when
  applied, then ONE row is raised, the second is reported `restates_an_instalment`, and the
  line's quantity is charged once. Replaces the parent's AC-S1-38 reading of the remark.
* AC-R-12 Given the FIRST of two restating rows has a blank remark and the SECOND cites a PO
  line that has room (and nothing names the line), when applied, then the one raised row is
  linked to that cited PO line (the citation is merged onto the first match).

Parent tests that change: in `tests/test_project_order_inquiry_import_migration.py`, the
test for AC-S1-38 (restatement) is rewritten so its "differs only by remark" case now
expects a restatement, and any test that seeds a `po_history` claim and expects a link
from it is rewritten to seed the ref (or an `autocount` claim) instead. Everything else in
that file stays green unchanged.

## Slice S2, rollback script [BE]

* AC-R-13 Given rows raised by `apply(..., file_name="a.xlsx")` with links, and rows raised
  by a second `apply(..., file_name="b.xlsx")`, when
  `scripts/rollback_oi_sheet_upload.py --file-name a.xlsx --apply` runs, then a.xlsx's rows,
  their links and the links' `order_inquiry` claims are gone, and b.xlsx's rows and links
  are untouched.
* AC-R-14 Given the same, when run WITHOUT `--apply`, then nothing is deleted and the
  printed counts equal what `--apply` would delete.
* AC-R-15 Given an inquiry header left with zero rows by the rollback, when `--apply` runs,
  then that header is deleted; a header that still has rows from another file stays.
* AC-R-16 Given the rollback ran, when the same sheet is applied again, then the rows are
  raised again (D2's "already raised" no longer blocks them).
