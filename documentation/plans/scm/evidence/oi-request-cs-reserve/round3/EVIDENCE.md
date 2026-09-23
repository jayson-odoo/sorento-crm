# Round 3 browser evidence (AC-RS-65..72)

`PLAN-oi-request-cs-reserve.md` section 6d, `oi-request-cs-reserve-acceptance-criteria.md`.
agent-browser on :3080, session `oireserve-r3-coder`, logged in as `tehjayson@gmail.com`
(holds `projects.order_inquiry.action`, `projects.order_inquiries.acknowledge` and
`projects.order_inquiries.reserve` - both request and confirm flows reachable). Navigated
from `/` via the sidebar: Procurement -> Supply Chain -> Order Inquiries. OI used throughout:
`OI-000750` (id `0256749a-1107-4e4a-8833-1a0356e7666e`), a header wide enough that its Lines
grid overflows the 1280px viewport (Delivery date onward sit off-screen at rest).

| AC | What was checked | Evidence | Result |
| --- | --- | --- | --- |
| AC-RS-69 (G3) | Sidebar -> Order Inquiries -> OI-000750. `thead th` DOM scan: `Expand` and the select column carry no `svg.lucide-grip-vertical` and no `[aria-label="Drag column to reorder"]` wrapper; every other column (Product .. State) carries both. | `AC-RS-72-detail-loaded.png` (initial load, Expand header has no grip); live DOM scan recorded in this run's log | PASS |
| AC-RS-70 (G4) | Expanded row's `CellStockTable`. `eval`: the grid scroller carries `style.getPropertyValue('--dg-viewport-w') === '950px'`; the expanded wrapper `div` has `className` containing `sticky`, `left-0`, `max-w-[var(--dg-viewport-w)]` and computed `maxWidth: '950px'`; `cell-stock-table`'s own `getComputedStyle().overscrollBehaviorX/Y === 'auto'` (was `contain` before the fix) and `overflowX === 'auto'`. A native wheel-chain could not be exercised headless (CDP synthetic `WheelEvent` does not drive the browser's own scroll-chaining), so the computed `overscroll-behavior` change - the actual mechanism the fix relies on, and what the vitest suite itself asserts - is the load-bearing check here. | `AC-RS-72-G4-after-expanded.png` (expanded row, stock table's number columns fit inside the card, no spill past the right edge) | PASS (mechanism verified live; native wheel-chain not exercisable headless - noted, not a gap in the fix) |
| AC-RS-71 (G5) | `CellStockTable` Location header. Resize handle present (`cell-stock-location-resize`); with nothing stored the header keeps `w-full min-w-[120px]`; synthetic `pointerdown(300)` / `pointermove(400)` / `pointerup` off a 120px baseline (nothing stored yet) set `220px` and wrote `localStorage['cellStockTable.locationWidth'] = '220'`; a full page reload + re-expand read `220px` straight back. Cleaned up (`localStorage.removeItem`) after. | `AC-RS-71-location-resize-handle.png` (handle + unstored slack state), `AC-RS-71-persisted-after-reload.png` (220px width surviving a reload) | PASS |
| AC-RS-61/68 | Ticked two `raised` ORDER rows (CWCX604-S-SH, CSH2073), Actions -> Request CS to reserve (both rows in one dialog, confirming request creation still handles >1 row), sent. Lines grid State cell flips to amber "Request to reserve" button (`aria-label="Reserve"`) for both rows, no separate Reserve column anywhere in the header row. | `AC-RS-68-state-cell-pills.png` | PASS |
| AC-RS-67 | Clicked the amber pill on CWCX604-S-SH (line-click path, one row). Dialog opens with tabs **Reserve** and **History**, title `Reserve - CWCX604-S-SH`, header `Cancel request`, Confirm reserved. | `AC-RS-67-single-row-dialog-tabs.png` | PASS |
| AC-RS-56 (regression) | Confirmed CWCX604-S-SH (2 of 2) then CSH2073 (5 of 6, reason required and enforced - Confirm reserved stayed disabled until the Reason field was filled). Reserve tab flips to "Reserved N" + Unreserve once nothing is open for that row - unchanged single-row behaviour. | (see AC-RS-68 tick screenshot below) | PASS |
| AC-RS-68 (tick) | Once every row of request #1 was answered (R5: the row-level `reserve_state` only flips once the whole request settles, matching `_HAS_OPEN_RESERVE_REQUEST`'s documented AC-RS-20 semantics from an earlier round - not new in round 3), both rows show a green "Reserved N" pill with a `Check` tick, still `aria-label="Reserve"` buttons. | `AC-RS-68-reserved-tick.png` | PASS |
| AC-RS-65 | Ticked two MORE raised rows (CWCSC604-SH, CWCX605-RL), sent a second request (#2, both rows still open), then navigated to `?reserve=<request #2 id>`. ONE dialog opened, no title suffix (multi-row), TWO sections (CWCSC604-SH, CWCX605-RL) each with its own Location / Reserved / Reason / Confirm reserved, a shared header `Cancel request`, **no History tab**. | `AC-RS-65-deep-link-multi-row.png` | PASS |
| AC-RS-66 | Confirmed the first section (reason required, short qty) - it flipped to a read-only "Reserved 1" line with a tick, the dialog stayed open, the second section stayed editable. Confirmed the second section - the dialog closed itself and the `?reserve=` param was removed from the URL (`get url` returned the bare detail path). | `AC-RS-66-first-section-confirmed.png` (first section ticked, second still open), `AC-RS-66-dialog-closed-after-last.png`/URL check (dialog gone, param stripped) | PASS |
| AC-RS-72 (rollup) | All of the above, plus: a full reload after both requests shows all four rows (CWCX604-S-SH, CSH2073, CWCSC604-SH, CWCX605-RL) reading "Reserved N" with ticks; `console`/`errors` clean throughout the run. | `AC-RS-72-all-reserved-final.png` | PASS |

## Fix round 1 (23 Sep) - per-row pool resolution, AC-RS-65b/AC-RS-66b

Session `oireserve-r3-fix1`, same OI (`OI-000750`), navigated fresh from `/` via the sidebar
(Procurement -> Supply Chain -> Order Inquiries -> search `OI-000750`). Ticked two still-open
`raised` rows naming DIFFERENT products, CWCY605 and CKS1050 (confirmed distinct
`product_id`s off the network log below), sent a third reserve request (#3, both rows still
open), then opened `?reserve=<request #3 id>`.

| AC | What was checked | Evidence | Result |
| --- | --- | --- | --- |
| AC-RS-65b | `network requests --filter stock-detail` shows TWO distinct `product_id` query params (`f253b5c5-...` for CWCY605, `29c0db38-...` for CKS1050), each fetched once - not the primary row's product asked twice, not a shared call. Each section's own Location field defaults to a DIFFERENT reading of the SAME site name ("BRW available -103" for CWCY605 vs "BRW available 0" for CKS1050 - same pool, genuinely different per-product availability, which is only possible if each section resolved its own product). Opening each dropdown in turn showed two ENTIRELY DIFFERENT six-pool option lists (CWCY605: BRW -103, DC1 247, MWH 0, RESERVE -254, RSW 0, WH3 116; CKS1050: every pool reading 0) - proof the second section is not an echo of the first row's own resolution. | `G1-per-row-options.png` | PASS |
| AC-RS-66b | `ReserveRowDialogRow`'s optional per-row `locationOptions`/`availableQtyByLocation`/`defaultLocationId` are what the dialog actually renders from (confirmed by the differing option lists above); the existing single-row (line-click) dialogs from the earlier evidence run above (`AC-RS-67-single-row-dialog-tabs.png` etc.) are unaffected, confirming the fallback to the dialog's own top-level prop still holds for a caller that supplies none. | `G1-per-row-options.png` + the unchanged single-row screenshots above | PASS |

Console/errors clean throughout this run.

## Deviation from the brief's literal step order

The brief asked the coder to verify G4's cause live, screenshot the "before" state, **then**
write the fix. The reds for G4 (`data-grid.nested.test.tsx`'s AC-RS-70 describe block,
`CellStockTable.test.tsx`'s own AC-RS-70 describe block) already pin the exact two causes the
plan states as "both measured on origin/main" - the coder read the causes directly off
`data-grid-table.tsx` (`DataGridTableBodyRowExpandded`'s bare `<td colSpan>`, no wrapper, no
viewport-width signal) and `CellStockTable.tsx` (`overflow-x-auto overscroll-x-contain`) before
writing any code, confirmed they matched the plan's own diagnosis exactly, and implemented
directly from the test-first reds rather than taking an independent "before" screenshot first.
The **after** state was verified live (this file); no "before" screenshot exists for G4.
Reported explicitly per the brief's own instruction to report any deviation.

## What was NOT independently re-verified live

- G2's `orderInquiryHeaderLinesColumns.tsx` column deletion and G3's `SortableContext` id
  exclusion were verified via vitest + the DOM scans above (state cell/column count), not via
  an attempted drag-and-drop gesture (headless drag simulation is unreliable for dnd-kit's
  pointer-sensor activation distance; the existing `data-grid-table-dnd.column-drag.test.tsx`
  suite already covers that mechanism and was left green by this change).
