# Acceptance criteria: order inquiry PO/SPO reserving, feedback 8 Sep 2026

Companion to `PLAN-scm-oi-reserving-feedback-8sep.md`. Every criterion is
verified in a real browser (agent-browser, via the sidebar) as well as by test.

## Slice A, the row is one line

* AC-A1 A worklist row whose Outstanding PO/SPO cell backs three documents
  occupies the SAME row height as a row backing one. Measured at 1280 and at
  375.
* AC-A2 No `supply-bar` element renders inside the `po_number` column. The
  schedule view's bar is untouched.
* AC-A3 No `link-late-<document>` element renders anywhere on the worklist,
  and no cell title contains the words "lands" or "arrives late".
* AC-A4 The cell prints EXACTLY three things: the draft or confirmed mark, the
  coverage headline (`115 of 493`), and the info icon. No document number, no
  document count, no location, no quantity per document.
* AC-A5 The info icon opens a lightbox naming every backing document with
  kind, number, location, quantity, expected date and standing, and nothing
  else. It does NOT explain why a document was chosen. Closing it returns to
  the same scroll position.
* AC-A6 A row backing exactly ONE document still prints no document number in
  the cell. The number lives only in the lightbox.
* AC-A7 A row nothing covers still reads "Not found (new order)" and shows no
  icon.

Owner feedback, 9 Sep 2026, against the running lane: the Qty column carried
the same defect - a rejected row's reason or a changed row's Was/Now table
rendered as a second line, so those rows read two lines tall while every
other row read one. "These can be informational icon also."

* AC-A8 The Qty cell is ONE LINE: the quantity, and an info icon ONLY when
  the row carries a rejection note, a change stamp, or both. A plain
  acknowledged row shows the number alone and no icon.
* AC-A9 A rejected row's icon is visually distinguishable from a changed
  row's at a glance, without adding words to the cell - the rejected icon
  reads as a warning, the changed icon reads as muted. Clicking it opens a
  dialog naming the item and stating who rejected it and their reason.
* AC-A10 A changed row's icon opens a dialog naming the item and stating that
  it changed, when, and the Was/Now detail the badge used to carry.
* AC-A11 A row both rejected and once changed shows both facts in the
  dialog, and the icon reads as the warning colour (rejection is the more
  urgent of the two).
* AC-A12 `RejectedNote` and `ChangedBadge` are gone from the cell path -
  nothing else in the tree renders them, so they move into the dialog
  wholesale rather than leaving a dead export behind.

## Slice B, the document lightbox

* AC-B1 Opening a PO lightbox on a document with 89 lines renders a DataGrid,
  not a bare table, with `tableLayout.width = 'fixed'` and resizable columns.
* AC-B2 Typing a product code into the lightbox search narrows the lines to
  that product. Typing `BRW-IB` narrows them to that location. One input does
  both.
* AC-B3 Searching `SRTWCX8605-S-RL-PJ` on `202405-S0045` and then `BRW-IB`
  surfaces the two open lines (52 and 2) without paging.
* AC-B4 The lightbox paginates at 10 rows by default and states the total.
* AC-B5 "Open document" opens `/scm/purchase-orders/{id}` in a NEW tab; the
  lightbox and the list behind it are still there on return.
* AC-B6 The SPO lightbox gets the same grid, search and pagination.
* AC-B7 Usable and non-clipped at 375 and at 1280.

## Slice C, SPO names its PO (gated)

* AC-C1 An SPO lightbox line that AutoCount says came from a purchase order
  prints that PO number.
* AC-C2 The PO number there opens the PO lightbox.
* AC-C3 A line with no source PO prints nothing rather than a guess.

## Slice D, all or nothing cover

* AC-D1 A row needing 493 whose cascadable candidates total 115 receives NO
  links from the automatic pass, stays `raised`, and its whole 493 counts to
  Buy.
* AC-D2 A row needing 493 whose cascadable candidates total 493 or more is
  linked in full exactly as today.
* AC-D3 The Buy tile above the list rises by the full row quantity, not by
  the balance, for a row AC-D1 covers.
* AC-D4 The Link dialog still offers a partial take by hand, and taking one
  still writes a link and leaves the row `partly_linked`.
* AC-D5 `default_take` in the dialog reads zero for every candidate of a row
  the cascade will not deal, so preview and pass agree.
* AC-D6 A row already `partly_linked` before the change keeps its links after
  a deploy. No migration and no script touches it.
* AC-D7 A row whose candidates are entirely non-cascadable (sibling group,
  another site) behaves as it does today: nothing linked, all Buy.
* AC-D8 Regression: the existing partial-cover tests are rewritten to the new
  rule rather than deleted, and each one names which rule it asserts.

## Slice H, the pass takes from the pool and nowhere else

* AC-H1 A row at BRW-IB, and a PO line at BRW-IB with enough remaining that NO
  claim of this row's own sales order names, get no automatic link. The row
  stays raised and its quantity goes to Buy.
* AC-H2 The same row WITH a BRW pool line covering it in full is linked to the
  pool line.
* AC-H3 A row at BRW-IB and a line at DC1-IB (same ownership group, another
  site) get no automatic link.
* AC-H4 A row at BRW-IB and a line at BRW-BB get no automatic link, as today.
* AC-H5 Two pool lines, the row's own site pool and another, are still tried
  in that order.
* AC-H6 A row naming NO location is dealt pool lines only, and never a
  project-location line.
* AC-H7 The Link dialog still LISTS every tier, labelled with its tier, and a
  buyer taking a project-location line by hand still writes a link.
* AC-H8 `default_take` reads zero for a project-location candidate, because
  the pass will not take it.
* AC-H9 Existing links standing on project-location lines are NOT removed by
  this change. No migration, no script.
* AC-H10 `_groups_in_deficit` and `_exempt_groups_for_row` still run for the
  Link dialog and manual placement, and their tests still pass.
* AC-H11 The owner's exception: a project-bin line that THIS row's own sales
  order claims IS taken automatically, wherever it stands. A purchase order
  this codebase raised off the plan claims the rows that sized it
  (`scm/supply_claim.py`), and those rows link on the next pass exactly as they
  did before slice H.
* AC-H12 A project-bin line claimed by ANOTHER sales order, or claimed by
  nobody, is still refused (G12 unchanged), and is still listed in the Link
  dialog for a manual take.
* AC-H13 The cascade never writes or infers a claim for itself. A project-bin
  line is attributed by the supply writer, by the book's `FromSODocList`, or by
  a person - never by the pass that wants to consume it.
* AC-H14 Ranking: with an own-claimed project-bin line and a pool line both
  available and both able to cover, the claimed line wins on the sort key.

## Slice E, SO-tied line wins (gated)

* AC-E1 Given a PO line at BRW-BB tied to SO419595 and a pool line at BRW with
  more remaining, a row of SO419595 links to the BRW-BB line.
* AC-E2 The SO-tied line is a RANK: where it holds 2 of a needed 10, and the
  pool covers the rest, the row still fails the all-or-nothing test only if
  the two together fall short.
* AC-E3 A row of a DIFFERENT sales order never prefers that line, and reaches
  it only at its ordinary location tier.
* AC-E4 The Link dialog labels the SO-tied candidate so a buyer can see why it
  ranked first.
* AC-E5 After a book re-upload that moves the quantity to a new SO-tied line,
  `relink_to_matching_lines` re-points the placement onto it.

## Slice F, extract carries linkage (gated)

* AC-F1 A PO line arriving from the live AutoCount feed with a source SO
  writes an `OrderLinkClaim` with `source = 'autocount'` and the item code
  stated.
* AC-F2 The claim resolves to a `po_line_id` and an `so_line_id` once both
  documents are held, whichever arrived first.
* AC-F3 Re-syncing the same document writes no second claim.
* AC-F4 A claim naming a sales order we do not hold stays unresolved and is
  counted, never dropped.

## Slice G, PODTL rows that cannot be true (gated)

* AC-G1 The PO detail page never labels a line with nothing ordered and
  nothing outstanding as "Outstanding".
* AC-G2 The document footer totals reconcile: received never exceeds ordered
  on a document where AutoCount says it does not.
* AC-G3 Whatever rule is chosen is stated in the plan with the shared
  service's answer quoted, before any code is written.
