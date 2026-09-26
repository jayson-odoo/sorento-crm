# UAC: managing a sales-order change after planning, one engine

Plan: `PLAN-scm-change-management-one-engine.md`. Scenarios S1 to S12:
`mockups/so-change-management-grill-v4.html`. All on one line unless stated: SO419772,
B2155-NL-BLUE, own location BRW-IB, pool BRW.

## Slice A. Diff parity

**AC-A1.** Given a manual edit on the SO detail that removes a line with a held decision or
an inquiry row, when saved, then the save is accepted (no 409) and a change row of kind
`cancelled` exists for that line.

**AC-A2.** Given a manual edit that adds a line to an order with held lines, then a change
row of kind `added` exists for the new line, in the same batch as the order's other changes.

**AC-A3.** Given a manual edit that changes a line's product, then exactly one change row of
kind `product_changed` exists carrying the old and the new product; no `cancelled` plus
`added` pair.

**AC-A4.** Given a manual edit setting a held line's qty to 0, then the change row is kind
`cancelled`, not `qty_down`.

**AC-A5.** Given the same edits arriving via SO book upload and via AutoCount ingest, then the
batch rows are identical in kind and from / to values to the manual-edit case (one diff, three
triggers).

## Slice B. Delta seam

**AC-B1 (S1).** Given Buy 134 held, inquiry row ORDER 134 raised, qty up to 234 on a
non-immediate date, then the suggestion is Buy 234 on the same row ("Was 134"); never a mix
of Use own and Buy.

**AC-B2 (S1 borrow).** Given the same, and a later order holding 234 on hand, then the
suggestion is Borrow 234 whole with an ORDER_BACK row for the donor and the Buy row
cancelled.

**AC-B3 (S11).** Given Buy 134 raised and the date advanced into the immediate window, then
pool share may cover part (the allowance), the remainder is covered by one step or shown
short, and the Buy row is reduced or cancelled accordingly.

**AC-B4.** Given a held Use own line and qty up, then more stock is taken if the group has it,
else the whole unit moves to the next covering step; the held reserve is not silently dropped.

## Slice C. Recompute-and-diff

**AC-C1.** The board shows, per changed line, Was / Now and a suggestion composed only of
Keep / Reduce / Release / Reallocate on held components plus Use own / Borrow / SPO / Buy for
new quantity. The words replan, retire, accept never render.

**AC-C2 (S9).** Given Reserve 134 and a delay that stays inside the reserve window with no
inquiry row needing the stock earlier, then the suggestion is Keep 134 and nothing else.

**AC-C3 (S10).** Given Reserve 134 and a delay past the reserve window, then the suggestion is
Release 134 (dealer pool if hot-selling, else free at BRW-IB) and Buy 134 for the new date;
Keep is available as an Amend.

**AC-C4 (S2).** Given Buy 134 placed on PO-A and Buy 100 raised, qty down to 100, then Reduce
the raised row to 0, Keep PO-A 100, Reallocate PO-A 34.

**AC-C5 (S5, S7).** Given a cancelled line or a product change, then every held component is
Release or Reallocate and, for a product change, the new product is sourced as a new line in
the same row.

**AC-C6 (S12).** Given an advance the held PO cannot meet and no donor able to lend the whole
unit, then the suggestion is Keep, flagged late by N days, and Confirm records the lateness.

**AC-C7.** Confirm posts the composed decision and Amend edits it; no "accept" step exists on
the board; `PlanningChangeRow.decision` values are confirm / amend only.

**AC-C8 (S8).** A date and qty change in one edit yields one row and one composed suggestion;
no date-wins tie-break.

## Slice D. Reallocation

**AC-D1.** Given freed PO / SPO quantity and the product dealer hot-selling, then it is
reallocated to the dealer pool (a pool-location row linked to the document) even if an
inquiry row on another order needs it.

**AC-D2.** Given freed quantity and the product not hot-selling, then it is linked to raised or
partly linked ORDER rows with unlinked quantity in the linking engine's priority; the
receiving row reads placed or partly linked and its order is not asked to confirm.

**AC-D3.** Given nobody needs it, then a pool-location row carries it and the reorder engine
counts it as cover.

**AC-D4 (S3).** Given Reserve 134 delayed inside the window and another order's ORDER 80 row
raised, unlinked, due earlier, then 80 of the reserve moves to that order's decision (its
Buy row cancelled) and this line is re-sourced whole for its new date.

**AC-D5.** `redirected_to_pool` is no longer written; existing rows keep their value.

**AC-D6.** The board shows every reallocation as "PO-A 34 to SO420103" or "to BRW" in words,
never a UUID.

**AC-D9 [BE] (defect round B1).** Given a cancelled line's placed Buy split across two
purchase-order lines, and a same-order survivor with headroom for only ONE of them, then
apply moves BOTH: the survivor takes what it can, the other link is found by a cross-order
waiting row (or, absent one, the pool), and the order does not fail. Test:
`tests/scm/test_planning_change_reallocation.py::test_every_link_of_a_cancelled_row_finds_a_taker_survivor_and_cross_order`.

**AC-D10 [BE] (defect round R3).** Given the same shape with no cross-order taker and no
pool warehouse configured for the line, then the link nobody can take is released
(unlinked) and named in `released_documents`, never `executed_reallocations`. Tests:
`tests/scm/test_planning_change_reallocation.py::test_every_link_of_a_cancelled_row_finds_a_taker_survivor_then_release_when_nobody_needs_it`,
`::test_a_cancelled_lines_placed_buy_with_no_pool_configured_is_released_not_executed`.

## Slice E. One signal

**AC-E1.** Given a confirmed decision and any qualifying change, then no decision is set to
`challenged`; the sheet never shows "Needs CS review" for drift; the change batch is the only
signal.

**AC-E2.** `challenge_if_drifted` has no caller on the sheet read, confirm and reconcile
paths; the borrow-hold release it performed happens on apply of the batch instead.

## Slice C, board display (owner feedback 13 Sep)

**AC-C9 [FE][UX] Indicator.** A changed line shows one amber hazard icon (the warning
triangle already used beside a Rejected verdict) instead of the inline Was / Now block, in
BOTH the board grid cell and the list row. In the list the icon sits in the column ruled by
what moved: Required date and/or Outstanding when the date and/or the qty moved (a line
with both moved shows it in both columns); Suggested ONLY when neither qty nor date moved -
a pure suggestion/decision change with nothing to show in either of the other two columns.
In the grid it sits beside the line's figure in the cell.

**AC-C10 [FE][UX] Lightbox.** Clicking the icon opens a dialog titled "What changed, <SO>
(Line <n>)" listing ONLY the fields that changed, one per line as "<label> <old> → <new>"
(Qty 234 → 334; Date 4 Sep → 20 Nov; Decision Buy 234 → Buy 334), unchanged fields
omitted, then the suggestion lines verbatim (server labels), "Late by N days" / shortfall
once. Escape and a Close button close it. Same component in grid and list.

**AC-C11 [FE][UX] One shortfall line.** A shortfall renders exactly once (the label "Short
N by <date> (was Buy M)"); no separate "Short N" line.

**AC-C12 [FE][UX] Expand all / Collapse all.** The list view carries Expand all and
Collapse all controls with the same placement and behaviour as reorder planning's (find
it: grep the reorder planning list for "Expand all").

**AC-C13 [FE][UX] Thin rows.** The list's Sales order cell reads "<SO> (Line <n>)" on one
line; the Suggested and Decided cells carry no progress bar; a row is one text line tall
(assert the cell renders no element with the bar's class / role).

**AC-C14 [FE][UX] Works at 375 and 1280 (the dialog fits the viewport, icons stay in their
columns).**

**AC-C15 [BE][FE] (defect round, non-open rows).** The board wire's `BoardContribution`
carries `cancelled` and `pending_change_batch_id`; a cancelled row also carries its
location, customer and agent fields (not left blank the way a bare non-open read would),
and the decision pill reads verdict "Cancelled" even when the row has no location (cancelled
outranks "Needs a location"). Tests:
`tests/test_planning_change_apply_on_board.py::test_the_boards_contribution_wire_carries_cancelled_and_its_batch_id`,
`::test_the_boards_cancelled_contribution_carries_location_and_customer_fields`;
`BoardDecisionPill.test.tsx` ("reads Cancelled, not 'Needs a location', for a cancelled line
that also has no location").

**AC-C16 [BE] (defect round, non-open rows).** A pending change row on a line the book has
since closed (delivered, or otherwise no longer open demand) is still listed, with `qty`
forced to 0 - the ladder never runs for a line that is not open demand any more. Test:
`tests/test_planning_change_apply_on_board.py::test_a_pending_product_changed_row_on_a_closed_and_delivered_line_still_appears_on_the_board`.

**AC-C17 [BE][FE] (defect round R4).** A stored composition's reserve/borrow component
carries `location` (the warehouse code) beside `warehouse_id`; read back on a later render,
the frontend prints the code, never the id. Test:
`tests/scm/test_planning_change_delta_seam.py::test_an_amended_reserve_posted_with_no_location_key_reads_back_carrying_one`
(FE renders it through the same words-only board display AC-C10 already covers - no
component reads `warehouse_id` for display).

## Cross-cutting

**AC-X1.** Purchasing is notified once per applied order, after the order's savepoint commits
(already shipped) and to every purchasing role (issue #854).

**AC-X2.** Every AC above has a pytest; C and D also have a vitest for the board words; each
slice ends with a browser run on the lane of its scenarios seeded on SO419772.
