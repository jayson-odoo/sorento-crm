# PLAN: Stock Debt frozen SO qty, live linkage / reserve; Change PO (STOCKDEBT-LIVE-ACTIONS)

Status: Review (normal track: the diff is over the ~300-line small-fix limit; no migration, no
auth/RBAC change, no new ingest surface, and the one new write route sits behind the existing
`projects.stock_debt.link_po` permission and the "AutoCount links from Stock Debt" switch).
Part 1 and Part 2 on PR #2332; review round 1 fixed.

## Owner rulings

- 11 Nov 2026 ~15:05 MYT: "in stock debt, what should be frozen is the things like quantity,
  orders, at the moment, the linkage, request to reserve all those should be updated".
- 30 Oct 2026: "we snapshot the sales order but not the OI".
- 11 Nov 2026 ~15:15 MYT, Change PO card: 1(a) a 4th Decide item "Change PO..." under "Link to
  PO...", greyed with the reason unless every ticked line is covered by exactly one PO line;
  2(a) the old PO line is unlinked and stays open as free supply, qty untouched, the new PO line
  is linked for the same qty; 3(a) refuse with "PO Y has only N free" and change nothing.

## What the owner hit

Decide > Link to PO answered "Linked", but after Done and after a reload the drill still showed
the frozen Covered by / Assigned / Status. Cause: the drill served every demand-row field as
stored at save (`StockDebtSnapshotService.create`, `_demand_row` per line); only `now.po_links`
was read live. On a covered line Link is greyed ("Already covered by PO X"), with no way to
swap the PO.

## Part 1: frozen vs live in the snapshot drill

`StockDebtSnapshotService.lines()` now calls `_live_cover()`: one `StockDebtService._assignments`
walk (`view=True`, the board's own call) for the row's single product under the snapshot's
stored filters, overlaying the cover fields on every frozen line still in today's walk. A line
gone from today's walk (cancelled, delivered, out of the filters) keeps its frozen cover and the
Now pill says why. The front end already re-reads the drill after every Decide action
(`usePoLinkMutations.refresh`, `onRequested`), so the new state shows without a reload.

Short mixes both: frozen outstanding less what covers the line in time today
(`live open - live short`), clamped to [0, frozen outstanding].

See the PR body for the full column table with sources.

## Part 2: Change PO...

`POST .../po-link/change {changes: [{sales_order_line_id, po_line_id}]}`. Refused (422, nothing
sent) unless the SO line is covered by exactly one open PO line, the new PO line is a different,
unlinked, open AutoCount line of the product in the same book, and it has the linked qty free
(summed over the request), the old PO line passes the same open-AutoCount-line check, and each
SO line is named once. The old PO line is unlinked FIRST, then the new link is sent (whole row or
split, the existing link write): while the old row covers the SO row, AutoCount refuses any new
link as QTY_ABOVE_OUTSTANDING (AC-E2E-DB3 on db3, 11 Nov; the card's "link first" order was
wrong). A refused unlink sends no link and changes nothing. A link that fails after the unlink
returns `unlinked_po`, and the popup says the line is now uncovered. Each answer is returned with
`action` = unlink / link. Every call goes through the existing logged, idempotency-keyed
`_send_intent`; an unlink's key also carries the link it removes, so unlinking the same row again
after it moved is a new intent, not a replay.

Not built: AC-E2E-DB3's option (b), one PUT for old and new rows on the same PO document (old row
"D" plus a new DtlKey 0 row). Trigger: the Shared Service exposes that call.

## Tests

- `sorento_crm_backend/tests/scm/test_stock_debt_snapshot_live_cover.py`: link / unlink / move
  after the snapshot show in the drill (red without the service change: 3 fail), frozen qty with
  live cover Short, a line gone keeps its frozen cover, and the Change PO route (order of writes,
  free refusal, exactly-one rule, refused link leaves the old link, switch off).
- `tests/scm/test_stock_debt_snapshots.py` AC-11 (`test_a_snapshot_keeps_its_orders_and_quantities_frozen`):
  was "never recomputed"; now the header, rows and every line's SO fields are unchanged and the
  cover moves.
- Vitest: `PoLinkDialog.test.tsx` (Change PO popup), `poLinkWording.test.ts` (menu state),
  `SnapshotClient.drill.test.tsx` (menu order).

## Open owner questions (from review round 1)

- The drill's Total and the board's month cells stay frozen while Short is now live, so after a
  link the drill can read Short 0 beside a frozen Total.
- Which qty Change PO moves: built as `qty_ordered - qty_cancelled` (what Now shows); the other
  reading is the open balance `qty_ordered - qty_received`.

## Not changed (named so the trigger is visible)

- The board grid's month cells, Total and totals stay as frozen (`row_data`, header `totals`).
  They are the debt reading at save time; recomputing them live would make the snapshot the
  live board. Trigger: the owner asks for the grid cells to move with cover.
- A line no longer in today's walk (cancelled, delivered, out of the filters) keeps its frozen
  cover and Short; the Now pill says why.

## Assistant coverage (DoD lines 6 to 8)

- Line 6: n/a, no new list screen.
- Line 7: no `ActionDef` for Change PO, on purpose: it is an AutoCount write behind the admin
  switch (OFF by default) and the human Decide flow, the same as Link / Unlink / Move, which have
  none. Trigger to revisit: the owner wants the assistant to write to AutoCount.
- Line 8: n/a for the same reason; the drill's figures are not a new assistant answer.
