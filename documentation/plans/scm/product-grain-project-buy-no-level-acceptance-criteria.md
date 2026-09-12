# UAC: product-grain plan buys confirmed project demand without a reorder level (#794)

- AC-1 A product on the reorder_level basis with NO level (no buyer override, master 0) and
  N units of confirmed unplaced Order Inquiry Buy suggests N (MOQ/multiple applied), reason
  "project buy: N confirmed unplaced Buy", on a `buy` row; the order sheet row shows
  Suggested qty N, Project N.
- AC-2 The same product still shows the level as unset (panel "none set today", "Set
  AutoCount level to X" offered); no `needs_level` row is emitted beside the buy.
- AC-3 A no-level product with retail-only demand still emits `needs_level` and no buy.
- AC-4 A no-level product with confirmed Buy and no linked supplier emits `exception`
  carrying the project need; the summary row still states suggested = project need.
- AC-5 Products WITH a level plan byte-identical to before (existing per-product tests green).
- AC-6 No data change on prod is required; CSK2800-QT reads Suggested 914 on the next plan
  after deploy.

## Slice 2: order sheet suggestion columns + every planned product (owner, 10 Sep)

- AC-7 The order sheet Excel and PDF carry `Suggested qty` and `Suggestion` immediately left
  of `Order qty`, in that order; the other columns keep their order.
- AC-8 `Suggested qty` prints the engine figure (0 printed as 0); `Suggestion` prints the
  engine's one-line reason (buy reason, "covers" for covered, "no reorder level set ..." for
  needs_level, "no linked supplier" for exception). `Order qty` stays the pen column: blank
  until chosen.
- AC-9 Every product the run planned (buy, covered, needs_level, exception) is on the book
  and on the sheet; a covered or needs-level product prints with Suggested qty 0. No row is
  dropped for suggested 0.
- AC-10 A buyer can choose an order quantity on a row whose suggestion is 0 and confirm it.
- AC-11 DROPPED (review, 10 Sep): the on-screen order summary grid was retired in S10; the
  Suggestion column lives on the PDF and Excel only. The FE change is the row type + mock.
- AC-12 Export still refuses above 2000 rows with "Narrow the plan first" (unchanged).

## Slice 3: document numbers under the two supply cells (owner, 10 Sep)

- AC-13 The `BRW PO qty` cell shows the total on the first line and one `PO number - qty`
  line per open PO below it; `BRW incoming qty` does the same with `SPO number - qty`. PDF
  and Excel alike.
- AC-14 A product with nothing open prints a bare 0 in those cells, as today.
- AC-15 Only site-pool, still-open lines and allocations are listed (the same scope as the
  totals), so the listed quantities sum to the total on the first line. An over-received
  still-open line (negative remainder) counts as 0 in both the total and the list.
- AC-16 A buyer's chosen quantity on a suggested-0 row survives Confirm: location split
  persisted, draft PO line raised, worklist row names the location.
- AC-17 The widened book admission (covered / needs_level rows) applies on the product grain
  only; a location-grain run keeps the old rule.
