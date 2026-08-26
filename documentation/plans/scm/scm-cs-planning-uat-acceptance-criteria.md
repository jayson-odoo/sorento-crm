# UAC - CS fulfilment planning: UAT fixes

Plan: `PLAN-scm-cs-planning-uat.md`. Verified in a real browser on :3060 via the sidebar.

## A. Labels
- AC-A1 SRT382-6-DIY on SO415472: suggestion reads "Use shared stock 71 from BRW", never "Use own location".
- AC-A2 CWCY605 on SO324132 rev 1: decided reads "Use own location 454 from DC1-BB, 267 from MWH-BB, 211 from WH3-BB".
- AC-A3 A `group_borrow` source reads "Borrow from another order"; `cross_group_borrow` reads "Borrow other location".
- AC-A4 The stock documents popover has no "On hand - SO + SPO = Available" header line.

## B. Location table
- AC-B1 For a BRW-BB line the table lists BRW-BB, then MWH-BB / DC1-BB / WH3-BB / RSW-BB, then BRW / MWH / DC1 / WH3 / RSW, each with a Where tag and a subtotal per tag with more than one row. **The subtotal half is SUPERSEDED by AC-L12 (26 Aug):** rows are subtotalled by the SET availability is counted over rather than by Where tag (the line's own location subtotals with its group), and a section of ONE row DOES print a subtotal when it states a net, because the net covers locations this table does not list and no single row can say it.
- AC-B2 A row with no stock upload shows 0, not "Not stated".
- AC-B3 The Taken column sums exactly to the quantity needed when the line is fully covered; pools not drawn on show 0.

## C. Cell colour
- AC-C1 A cell whose only suggestion is Buy shows one rose segment; a mixed cell shows segments in proportion.
- AC-C2 Ticking Amend from Buy to Shared flips the bar to sky before confirm; clearing the tick returns it.
- AC-C3 A confirmed cell's bar is solid; an undecided cell's is faded.
- AC-C4 A past-date column tints its header only; cell bodies carry no date tint.
- AC-C5 RETIRED 26 Aug: the decision strip cards carry the labels and colours, so there is no legend row; the board shows no "N of M lines are already past their delivery date" banner (the column headers say it).

## D. Suggested vs decided (board page)
- AC-D1 Confirming writes `proposed_components` per line snapshot; decided `components` unchanged.
- AC-D2 The board page shows a decision strip of six cards (Buy / Use shared stock / Use own location / Borrow from another order / Borrow other location / Incoming supply), each with Suggested and Decided totals for the lines the current view can show; a differing pair is marked; a 0 / 0 card is disabled; clicking a card filters both the grid and the list view.
- AC-D3 The cell popover shows a Decision card beside the Suggestion card once any line is decided.
- AC-D4 List view and SO detail Lines tab show Suggested and Decided columns in section 2's words.

## E. Stock transfers
- AC-E1 Approving "71 from BRW" on a BRW-BB line creates stock transfer TR-nnnnnn: BRW -> BRW-BB, 71, state proposed, linked to the SO line and decision.
- AC-E2 SO324132 rev 1 yields six transfers for CWCX605-RL / CWCY605 (DC1-BB, MWH-BB, WH3-BB -> BRW-BB) with the snapshot quantities.
- AC-E3 Reconfirm cancels open transfers ("Superseded by revision N") and writes fresh ones.
- AC-E4 `committed_v` / `on_order_v` unchanged by transfers (pytest totals before/after).
- AC-E5 Transfers page reachable from the sidebar; Approve asks for confirmation; Mark moved asks for the AutoCount ref; nothing closes automatically.
- AC-E6 SO detail and sales-agent detail show a Transfers tab.

## F. (withdrawn - sets)
- AC-F1 The board popover for SO324132 line 2 reads "Use own location 354 from DC1-BB, 79 from MWH-BB, 499 from WH3-BB" and the Transfers page lists the three moves; the order-inquiry page carries no row for it.

## G. PO occupancy
- AC-G1 PO-2026/07-0029 detail shows, below the lines table: outstanding 500, allocated 500, free 0; three placements (SO416191 6 at BRW, SO416191 7 at BRW, SO324132 487 at BRW-BB), each marked "location differs" against DC1.
- AC-G2 No Split for AutoCount section; Allocated to carries needed-at vs PO location per placement.
- AC-G3 Re-uploading the PO book with that line split into BRW-BB 487 + BRW 13 keeps every placement attached to the line whose warehouse matches; none is orphaned or unplaced.
- AC-G4 PO list shows an Allocated column and filter.
- AC-G5 Nothing in G writes to `purchase_order_lines`.

## H. Order-inquiry page
- AC-H1 The subtitle "Every project and every adopted sales order, by delivery month." is gone.
- AC-H2 Worklist shows Raised by (name) and Raised at (MY time) for OI-000006; the per-SO header shows the same.
- AC-H3 Typing the CS user's name in the search bar returns their inquiries; the Raised by filter lists only users who raised one.
- AC-H4 Reconfirming SO324132 as a different user re-stamps Raised by on the header.

## I. Link PO / Link SPO
- AC-I1 No screen says Place / Auto-place / Unplace; they read Link PO, Auto-link, Unlink; state reads Linked.
- AC-I2 A raised row for SRTWCY7405-PJ at BRW-IB lists SPO-2026/08-0061 allocations before 202604-S0083 lines; within a document BRW-IB ranks before DC1-IB, before BRW, before BRW-BB.
- AC-I3 Auto-link on SO381895's raised rows links the ORDER BACK rows to the documents the 19 Aug form cites, or the fixture sheet records the difference.
- AC-I4 Linking to an SPO line removes the row from confirmed demand exactly as a PO link does (pytest on `committed_v`).
- AC-I6 SO414285 shows one OI row per SO line (nine), never a split row; M310-CR-PJ reads qty 8, Linked 8 of 8 with two links (5 + 3 on 202607-S0105); MSK11C 67 reads two links (10 + 57).
- AC-I7 A row linked 5 of 8 is state partly linked; `committed_v` carries 3 for it.
- AC-I8 Backfill merges every split row pair on the dev copy into one row + links; row count per SO line = 1 afterwards.
- AC-I9 SO detail Lines tab for SO414285 shows Linked to: M310-CR-PJ = 202607-S0105 L3 5 + L7 3; MSK11C = 202608-S0002 10 + 57.
- AC-I10 Candidate list orders by PO issue date, then line expected date, then document number, and shows both dates.
- AC-I5 Worklist Linked to column shows document + PO / SPO badge; filter Linked = po | spo | none works.

## J. UAT fixture
- AC-J1 `scm-cs-planning-uat-fixture.md` lists every row of the three SO381895 forms with expected verb, qty, location and link target, and an empty Actual column.
- AC-J2 SPO-2026/08-0046 and 202606-S0019 are marked "not in system" on the sheet, not silently skipped.

## K. SPO in spo_allocations
- AC-K1 Importing the 2026 PO & SPO book writes one `spo_allocations` row per SPO line and no `purchase_orders` row with an `SPO-` number.
- AC-K2 Existing SPO documents in `purchase_orders` are migrated across and removed; the migration downgrades cleanly.
- AC-K3 `on_order_v` for SRTWCY7405-PJ at BRW-IB includes SPO-2026/08-0061's open quantity.
- AC-K4 A line due after that SPO's arrival date proposes Incoming supply on rung 1.

## Ladder v3
- AC-L1 A line due beyond `as_of + lead time + 14` proposes Buy for the whole quantity and lists no other component.
- AC-L2 Within the window, a BRW-BB line with 40 available at BRW-BB, 30 at DC1-BB and 1000 at pool BRW proposes own 40 + own 30 + shared 30 for a need of 100 (group before pool).
- AC-L3 Group borrow from another sales order is never in the automatic proposal; it remains a manual pick.
- AC-L4 Singleton-pool parity test unchanged byte for byte.
- AC-L5 Amend refuses a composition mixing stock sources and Buy on one line (422 with the reason); the dialog's Buy switch clears the stock rows.
- AC-L6 Amend on SO415472 L1 offers SO394803 L2 (same agent) as a donor regardless of rank, requires an authorisation reason, and on confirm raises an Order back OI row for SO394803 L2 with the donor's date; the donor cell reads "71 lent to SO415472".

## Ladder v4 (group netting, ruled 26 Aug)
- AC-L7 B2155-NL-BLUE on SO381895 (24 Aug, 60): with BRW-IB 5290 / 27804 SO and MWH-IB 7000 / 0 SO, the group net is -15514 and the suggestion is Buy 60; MWH-IB's 7000 is never offered.
- AC-L8 SRTWCY8605-PJ: pools net -102 (BRW -103, DC1 +1) offers nothing from any pool.
- AC-L9 A cross-group donor (MWH-IR, on hand 100) is offered only when the whole -IR group nets positive, capped by that net; confirming the borrow raises an ORDER BACK row against MWH-IR.
- AC-L10 SRTWC7405-SC (31 Aug, 10): SPO 110 at BRW-IB with group net (2 + 330 + 110 - 2335) negative proposes no Incoming; the line buys.
- AC-L11 B2155-NL-BLUE's raised row does not link to 202607-S0067 BRW-IB while the IB group is in deficit; SRTWC8605-SC-RL links to 202607-S0039 BRW 9 (pool) and not to 202603-S0109 BRW-IB 11.
- AC-L12 The popover's Group subtotal, Site pool subtotal and Other group rows read the nets the engine used; Taken is 0 on every row of a non-positive net.
- AC-L13 A pool draw raises no ORDER BACK row.
- AC-L14 The group's offer to a line is `max(group_net + that line's own open quantity, 0)`, because `sum(SO)` already counts the line asking. On a line of 60: group net 0 offers 60 (the line is covered from the group), net -20 offers 40 (and the whole-line rule then buys the 60 anyway, since 40 is not all of it), net -70 offers 0 (the line buys). Every OTHER line's demand stays netted, so a group that is short offers the same nothing to the front of its queue as to the back of it.

## I2. Order inquiries read like the board (ruled 26 Aug)
- AC-I11 The schedule view shows three cards above the matrix: Use SPO, Use PO, Buy, with totals over the current filter; clicking one narrows the matrix; a second click clears.
- AC-I12 A cell whose rows are all unlinked shows one rose segment and reads "Buy N"; a row linked 5 of 8 to a PO shows sky 5 / rose 3 and reads "PO 5 · Buy 3"; a row linked to an SPO shows violet.
- AC-I13 Confirming a plan-generated PO that links a raised row flips its cell from Buy to Use PO without a reload of the filter.
- AC-I14 The list view's Linked to column carries the same bar; there is no legend row on either view.
