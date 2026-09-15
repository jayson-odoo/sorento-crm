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
* AC-R-17 Given a link whose `claim_id` names a claim this upload did NOT open - either
  another feed's (`claim_placed_on_po` resolves onto the existing row at that identity and
  keeps its source) or one another file's link still points at - when `--apply` runs, then
  that claim SURVIVES with its source unchanged and is not counted under `claims`. Only a
  claim of source `order_inquiry` that no surviving link names is deleted.
* AC-R-18 Given a blank or whitespace-only `--file-name`, when run, then it is REFUSED with
  a `ValueError` and nothing is deleted - the bare stamp is the prefix of every migrated row
  ever raised, including the rows an upload with no file name stamped.
* AC-R-19 Given rows raised under `JAN - DEC 2026 ORDER.xlsx` and under `JAN.xlsx`, when
  the rollback runs for `JAN`, then NOTHING is deleted (the match is on the whole file name,
  not a prefix of it); when it runs for `JAN.xlsx`, then only that file's rows go - including
  a row whose note carries the operator's own remark and its links' stamps after the file
  name.
* AC-R-20 Given rows raised under ONE file name in TWO companies, when the rollback runs,
  then it is REFUSED with a `ValueError` naming the companies and nothing is deleted; with
  `--all-companies` it removes both companies' rows. A run whose rows are all in one company
  needs no flag. (The script runs under the system scope - `None`, all companies - which is
  what lets one stamp be found at all, and equally what would let one company's operator take
  another company's rows out unnoticed.)

## Slice S3, PO and SPO columns on the worklist [FE]

* AC-R-26 Given a row linked to one PO line and nothing else, when the worklist renders,
  then the PO cell shows that PO number as a clickable link and no pill, the SPO cell
  shows a muted dash, and neither cell prints the coverage headline or an info icon.
* AC-R-27 Given a row linked to two allocations of the SAME SPO number and one PO line,
  then the SPO cell shows that number once with no pill (distinct numbers, not links) and
  the PO cell shows the PO number.
* AC-R-28 Given a row linked to three distinct SPO numbers, then the SPO cell shows the
  first (in link order) and a `+2` pill; clicking the number or the pill opens the
  Backing documents lightbox listing all three (the existing dialog, AC-A5 unchanged).
* AC-R-29 Given a row with no links, then the PO cell reads `Not found (new order)` and
  the SPO cell a muted dash; nothing is clickable.
* AC-R-30 Given a fully bundled row, then the PO cell reads exactly what it reads today
  (`Included with ...`, bundled trigger) and the SPO cell a muted dash.
* AC-R-31 Both columns carry explicit `size`, the number is `truncate` + `title`, the
  column ids are `po_number` and `spo_number`, and the header titles are `PO` and `SPO`.

## Reviewer round, 15 Sep 2026 (S1 importer)

* AC-R-21 Given a cited or referenced purchase order with TWO lines of the same product,
  and a shipping order carrying one allocation per purchase order LINE
  (`spo_allocations.from_po_line_ref` quoting that line's `source_ref`), when the row's
  sales order line is named by the SECOND purchase order line, then the link lands on THAT
  line's allocation - not on the first allocation of the document. (Prod: SPO-2026/01-0140
  carries five CB2154-DIY allocations from 202511-S0097, one per sales order line.)
* AC-R-22 Given a `from_so_line_ref` whose value names MORE THAN ONE sales order line - the
  August extract wrote bare ordinals, and `'1'` sits on 3,364 lines - when the sheet cites
  that document, then the ambiguous ref does not make any line "named" for the line pick:
  the row still lands on the real line rather than on a cancelled ghost that happens to
  carry the ordinal, and no link is written from the reference (source 1). The citation is
  still tried as source 3.
* AC-R-23 Given the FIRST of two restating rows has a blank remark and the SECOND cites a
  purchase order whose line names a DIFFERENT sales order line from the one the first row
  would otherwise match, when applied, then the one raised row is on the line the citation
  names - the lent citation reaches the line pick, not only the pairing.
* AC-R-24 Given two sales orders each holding a line with the same ambiguous `source_ref`,
  and a purchase order line naming that ref, when applied with no citation, then the row is
  raised and NOTHING is linked.
* AC-R-25 Given one purchase order with several lines of the same item,
  `order_link_service._purchase_side` answers with the OLDEST of them for both `by_key` and
  `by_number`, whatever order the database returns the rows in - an unordered read made the
  same file pair differently on its preview and on its apply.

## Follow-up, 14 Sep evening: bought line first (plan section 7)

* AC-R-32 Given a sales order with two open lines of the same item both fitting the row's
  qty, line 1 with the earlier required date, a PO line naming line 2, and a sheet row with
  NO remark, when applied, then the row is raised against line 2 and linked to that PO line.
* AC-R-33 Given the same but line 2 is `closed` and line 1 is `open`, when applied, then
  the row still lands on line 2 (bought beats open); and given line 2 is `cancelled`, the
  row lands on line 1 (cancelled-last still comes before bought).
* AC-R-34 [BE] Given a PO line of 62 naming the row's line and an SPO allocation of 62 with
  `from_po_line_ref` = that PO line's `source_ref`, and a row of 364, when applied, then the
  row gets ONE link, to the SPO allocation for 62, and no link to the PO line; given the
  allocation is 40, the PO line is linked for 22 and no more.
* AC-R-35 [FE] Given a row whose only link is an SPO allocation with `source_po_number`
  `202510-S0078`, when the worklist renders, then the PO cell shows `202510-S0078` and the
  SPO cell the SPO number; a row with a `po` link to `A` and an `spo` link from `A` shows
  `A` once in the PO cell (no pill).
* AC-R-36 [BE] Given a row of 364 on a core line with 364 ordered and 352 delivered and
  links of 62, when the worklist summary and the `kind=buy` filter run, then Buy for that
  row is 0 (`min(364, 12) - 62` floored) and the row is not in the `buy` set; given 300
  delivered, Buy is 2.
* AC-R-37 [BE] Given a sheet row dated 2026-01-05 matching a line whose required date is
  2030-01-01, when applied, then the raised row's `delivery_date` is 2030-01-01; given the
  line has no required date, the row carries the sheet's date.

## Reviewer round on #904, 15 Sep

* AC-R-34, second case [BE] Given ONE purchase order carrying line A (100, shipped in full
  on an allocation somebody else already holds) and line B (50, the line that names this
  row's sales order line), when applied, then the row is linked to B for 50: the deduction
  a line takes for its own shipments is per LINE, and a sibling's containers are not
  evidence that this line's units have sailed.
* AC-R-37, third case [BE] Given an ORDER BACK sheet row on a line whose required date is
  2030-01-01, when applied, then the raised row's `delivery_date` is 2030-01-01 too - the
  words in the date cell are still never a date, and `verb` is what says the quantity is
  owed against something already ordered.
* AC-R-38 [BE] The Buy cap (7.3) is the FIGURE, not one card's arithmetic. Given a row of
  364 on a core line ordered 364 / delivered 352 with links of 62, then the worklist's
  Remaining column (`_quantity_flow_by_so_line`), `scm.committed_v`'s project leg and
  `demand.horizon_committed_select_sql` - what a reorder run buys from - each read 0; given
  300 delivered, each reads 2. A row that says "nothing left to buy" on the card and 302 to
  the engine is worse than one that says 302 in both, because only one of the two is on a
  screen anybody checks.

## Follow-up, 15 Sep: remark out, exact date wins, cancelled lines never a target (plan section 8, issue #915)

Every criterion below is a pytest in `tests/test_oi_sheet_pairing_repair.py` over the
`blank_session` world, unless it names another file. Postgres only.

- **AC-R-39 The remark does not pick the line.** Two open lines of one item on one order,
  A dated the sheet's date and named by no document, B dated a month later and named by PO
  P (`from_so_line_ref` = B's ref). A sheet row for the item, dated A's date, whose remark
  cites P. The row lands on A. (Under #904 it landed on B by term 1.)
- **AC-R-40 The remark does not link.** One open line named by no document; PO P has a
  free line of the item with capacity; the sheet row cites P. The row is raised with NO
  link, `links_written` 0, `documents_not_linkable` empty, and the note still ends with the
  operator's remark text (AC-S1-28 kept).
- **AC-R-41 The exact date beats a bought line.** Two lines, A closed and fully delivered
  dated the sheet's date with no document naming it, B closed dated later and named by PO P
  which SPO S shipped in full. Row dated A's date, no remark. Lands on A, unlinked, and the
  raised row's `delivery_date` is A's date (7.4). B is not touched.
- **AC-R-42 Bought still decides when no line carries the sheet's date.** Same two lines,
  the sheet row dated a third date. Lands on B and links to S (section 7 preserved, AC-R-32's
  premise restated against the new order).
- **AC-R-43 No cascade.** Three dated lines L1 < L2 < L3 of equal quantity, L1 named by
  nothing, L2 and L3 each named by a PO line shipped on one SPO; an open balance line L4
  dated 2030-01-01 of a larger quantity. Three sheet rows dated L1, L2, L3 in that order.
  Each row lands on its own dated line; L2 and L3 rows link to the SPO; L1's row is
  unlinked; nothing lands on L4 and no raised row carries 2030-01-01.
- **AC-R-44 A cancelled purchase order line is never a target, from any source.** (a) PO
  line X cancelled with `from_so_line_ref` = the row's line: no link from the ref source and
  the line does NOT rank as "bought" because of X. (b) An `order_link_claim` naming
  cancelled line X: no link from the claim source. (c) A non-cancelled sibling line of the
  same PO with capacity IS still linked in the same run, so the exclusion is per line, not
  per document.
- **AC-R-45 The result contract is whole.** `preview` over the AC-R-43 world returns every
  key it returned before (`ok problems orders_adopted orders_stamped rows rows_raised
  rows_already_raised rows_line_not_found line_not_found sales_orders_not_found
  orders_not_plannable links_written links_partial links_from_autocount
  documents_not_linkable sheets_read sheets_skipped`) and `links_from_autocount ==
  links_written`.
- **Flipped tests** (plan 8.3): AC-R-8, AC-R-9, AC-R-12, AC-R-23 and the six `test_cited_*`
  / `test_*citation*` / `test_autocount_wins_over_remark` tests in
  `tests/test_project_order_inquiry_import_migration.py` are rewritten to the new rulings or
  deleted with the reason in the PR body; AC-R-32, AC-R-33, AC-R-11 stay as they are.
- **AC-R-46 An undated row does not prefer an undated line** (reviewer finding 1, 15 Sep).
  Two lines: L1 with no required date, named by nothing; L2 dated, named by a PO line that an
  SPO shipped. One ORDER BACK sheet row (no delivery date). The row lands on L2 and links to
  the SPO; the raised row's `delivery_date` is L2's date, not NULL. (Under the first cut of
  section 8 the date term read `None == None` as a match and put the row on L1, unlinked.)
