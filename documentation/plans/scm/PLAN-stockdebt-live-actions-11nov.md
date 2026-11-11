# PLAN: Stock Debt frozen SO qty, live linkage / reserve; Change PO (STOCKDEBT-LIVE-ACTIONS)

Status: Build (small fix track: no migration, no auth/RBAC change, no new ingest surface; the
one new write route sits behind the existing `projects.stock_debt.link_po` permission and the
"AutoCount links from Stock Debt" switch). Part 1 and Part 2 built on PR #2332.

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
(summed over the request). The new link is sent first (whole row or split, the existing link
write); the old PO line is unlinked only when AutoCount answered the link `done`. Each answer is
returned with `action` = link / unlink. Every call goes through the existing logged,
idempotency-keyed `_send_intent`.

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

## Not changed (named so the trigger is visible)

- The board grid's month cells, Total and totals stay as frozen (`row_data`, header `totals`).
  They are the debt reading at save time; recomputing them live would make the snapshot the
  live board. Trigger: the owner asks for the grid cells to move with cover.
