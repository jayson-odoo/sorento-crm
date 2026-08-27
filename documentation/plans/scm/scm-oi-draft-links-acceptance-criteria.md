# UAC - Order Inquiries: draft links up front, one Confirm, Outstanding PO/SPO

Plan: `PLAN-scm-oi-draft-links.md`. Verified by browser evidence (sidebar navigation from `/`, 1280 and 375), pytest and vitest.

## A. Links found up front
- AC-D1 Confirming SO404352 on the fulfilment board raises its rows To confirm, and each row a PO or SPO can cover already shows the document under Outstanding PO/SPO with the draft icon, without anyone pressing anything on the Order Inquiries page.
- AC-D2 A row nothing can cover reads "Not found (new order)".
- AC-D2b An ORDER row (not only ORDER BACK) with an open SPO for its product drafts onto the SPO before any PO; only an SPO line at a pool warehouse (BRW, MWH, DC1, WH3, RSW) is drafted, a line at any other code is shown in the lightbox and never taken.
- AC-D3 A draft link occupies the PO's remaining quantity: a second row of the same product is offered the rest, never the same units; the PO page's Allocated to panel lists the row as Proposed.
- AC-D4 The reorder plan's project demand ignores drafts on To confirm rows exactly as it ignored awaiting rows before; the plan chip reads "N to confirm".

## B. Confirm and reject
- AC-D5 Ticking three To confirm rows and choosing Start > Confirm selected (3) stamps them Confirmed <name> <time>; their draft icons flip to confirmed without a reload and no link changes document; an unlinked remainder is linked in the same press.
- AC-D6 Actions > Reject selected (N) asks one reason for the batch; an empty reason is refused; each row reads Rejected: <reason>, its links are gone, the PO's remaining quantity is back, and the board line shows the Rejected badge.
- AC-D7 A CS user who amends a confirmed row on the board sees it come back as Changed with the Was / Now table; its links stay and read as draft; Confirm returns it to Confirmed.
- AC-D8 A CS user sees no Start menu and no Reject / Confirm items; the endpoints answer 403.

## C. Re-deal
- AC-D9 Actions > Auto link all opens a dialog carrying Purchase order cut off <date> (defaulting to the plan's horizon, cleared = "No link horizon"); after an upload that adds a nearer PO for the product, the press moves the draft from the old document to the new one; a confirmed row's link is never moved.
- AC-D10 Start > Upload purchase orders with a book carrying SPO rows: Test reports the SPO documents and lines and any unknown locations; Confirm upload writes them as open SPO allocations with their warehouse; Link now drafts rows of those products onto them, SPO before any PO; a second book without those SPO lines closes them.
- AC-D11 Confirming a plan-generated PO drafts To confirm rows and links Confirmed rows, and the page reads both correctly.

## D. Reading the page
- AC-D12 The list opens on Confirmed = To confirm with the active-filter chip shown; clearing the chip shows every row; the three cards, the schedule and the export follow the filter.
- AC-D13 The toolbar is one row at 1280: search, Filters, Columns, refresh on the left; Actions and Start on the right; no Link up to box, no Acknowledge, no left Link / Unlink buttons, no row Actions column; the selection strip shows "N selected" and Clear only. At 375 nothing clips and the page does not scroll sideways.
- AC-D14 Actions holds Auto link all, Link selected (1) (enabled only with exactly one row ticked, opens the manual dialog), Unlink selected (N), Reject selected (N), Unlink all, Export Excel; Start holds Upload purchase orders and Confirm selected (N); counts disable at 0.
- AC-D15 The State column and its filter are gone; the Linked filter reads Found / Not found; the column headers read Outstanding PO/SPO, Taken by PO/SPO, Confirmed.
- AC-D16 An SPO link reads its pool warehouse code and quantity (`BRW 1`), never `L14 1`; the line label sits in the title; a document with no location in the book reads "no location".
- AC-D17 A late document reads "late N d" where N = days between the row's delivery date and the document's expected date, with the full dates in the title.

## E. Lightbox
- AC-D18 Pressing a PO number opens a dialog (not a popover): number, supplier, status, expected, "Open purchase order" link, the lines table and the Allocated to rows marked Proposed / Confirmed; it scrolls inside itself and closes on Escape; usable at 375.
- AC-D19 Pressing an SPO number opens the same dialog shape with the allocation lines (SKU, allocated, received, remaining, location) and the shipment / container when one exists.
- AC-D20 The old PO popover component no longer exists in the tree.

## F. Wire and tests
- AC-D21 `late_days`, the SPO `location` fallback, `to_confirm` and the PO detail's `allocations` are on the wire from the list, the summary, the export and the SO detail (asserted in tests).
- AC-D22 Tests per plan section 7 in the same PR; browser evidence for AC-D1, D2, D5, D6, D9, D12, D13, D16, D18, D19 on SO404352; no dashes in the diff.
