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

## Slice E. One signal

**AC-E1.** Given a confirmed decision and any qualifying change, then no decision is set to
`challenged`; the sheet never shows "Needs CS review" for drift; the change batch is the only
signal.

**AC-E2.** `challenge_if_drifted` has no caller on the sheet read, confirm and reconcile
paths; the borrow-hold release it performed happens on apply of the batch instead.

## Cross-cutting

**AC-X1.** Purchasing is notified once per applied order, after the order's savepoint commits
(already shipped) and to every purchasing role (issue #854).

**AC-X2.** Every AC above has a pytest; C and D also have a vitest for the board words; each
slice ends with a browser run on the lane of its scenarios seeded on SO419772.
