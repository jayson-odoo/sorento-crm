# TabsList overflow standard - browser evidence (issue #678)

Commits `e7b85d844` (fix: wheel + chevrons + fades + active-tab-in-view) and `44f306daf` (test:
removed per-screen `overflow-x-auto`, primitive owns it), branch `fix/hands-on-5sep`, worktree
`.claude/worktrees/hotfix-5sep`. Verified with `agent-browser@0.27.0` (headless, session
`tabs-check`) against FE `http://localhost:3091` (HMR) / BE `http://localhost:8120`. Read-only:
no Save, no setting changes, no deletes were performed.

All numbers below were read live via `agent-browser eval` against
`document.querySelector('[data-slot="tabs-list"]')` (the scroll container) and
`document.querySelector('[role="tab"][data-state="active"]')` / `document.activeElement`.

## Table

| Check | Route | Viewport | Result | Numbers | PNG |
| --- | --- | --- | --- | --- | --- |
| 1a. Initial overflow state | `/user-management/settings` (10 tabs) | 1280x800 | PASS - right chevron + end fade only at start, no left chevron | `scrollLeft=0`, `scrollWidth=1459`, `clientWidth=952`, `data-fade-start=false`, `data-fade-end=true` | `01-settings-1280-start.png` |
| 1b. Vertical wheel over strip | same | 1280x800 | PASS - a plain vertical `WheelEvent({deltaY:120})` dispatched on the list moved `scrollLeft`; the page did NOT scroll; `preventDefault` fired | `scrollLeft` 0 -> 120; `document.scrollingElement.scrollTop` stayed 0 both before and after; `defaultPrevented=true` | (state shown in 02) |
| 1c. Mid-way fades/chevrons | same | 1280x800 | PASS - both chevrons render, both fade masks active | `scrollLeft=120`, `data-fade-start=true`, `data-fade-end=true` | `02-settings-1280-midway.png` |
| 1d. Right chevron click | same | 1280x800 | PASS but see note - clicking "Scroll tabs right" from `scrollLeft=0` moved straight to the max (507), not a visible ~80% partial step, because `scrollWidth-clientWidth` (507) is itself less than `0.8*clientWidth` (761.6) at this width. End state: only the left chevron, `Integrations` fully visible, `data-fade-end=false`. The 80% math itself was independently verified correct at 650px (see row 1g). | `scrollLeft` 0 -> 507 (max); `data-fade-start=true`, `data-fade-end=false` | `03-settings-1280-end.png` |
| 1e. 900-wide start | same | 900x800 | PASS - same shape as 1280: right chevron + end fade only, no left chevron | `scrollLeft=0`, `scrollWidth=1459`, `clientWidth=868`, `data-fade-start=false`, `data-fade-end=true` | `04-settings-900-start.png` |
| 1f. 900-wide wheel + mid-way | same | 900x800 | PASS - wheel moved `scrollLeft`, page did not scroll; both chevrons/fades shown mid-way | `scrollLeft` 0 -> 120 via `WheelEvent({deltaY:120})`; page `scrollTop` stayed 0; `data-fade-start=true`, `data-fade-end=true` | `05-settings-900-midway.png` |
| 1g. 900-wide chevron to end | same | 900x800 | PASS - right chevron click reached the end (`scrollLeft=591`=max); same clamp-to-end caveat as 1d applies at 900 too (`0.8*868=694.4` > remaining room). The 80%-of-clientWidth math was confirmed exactly (`scrollLeft` 0 -> 494, expected 494.4) at a narrower **650x800** viewport where the overflow room (841px) exceeds one 80% step, proving `scrollByChevron` is correct and the clamping above is a content-length artifact, not a bug. | 650px supplementary check: `scrollLeft` 0 -> 494 (expected 494.4); 900px: `scrollLeft` -> 591 (max), `data-fade-start=true`, `data-fade-end=false` | `06-settings-900-end.png` |
| 2. Active tab in view after reload + keyboard nav | `/user-management/settings/integrations` | 900x800 | PASS - clicked last tab (Integrations), URL became `.../settings/integrations`; full page reload (`open` same URL) still showed `Integrations` as the active tab (route-per-tab, not client state) and it auto-scrolled into view via the `MutationObserver`. Tab focus + 3x ArrowLeft + 3x ArrowRight kept the focused trigger in view at every step (Social -> SMTP -> System Health -> SMTP -> Social -> Integrations), each step `inView=true`. | Post-reload: active tab rect `left=780.17, right=883.94` inside list rect `left=16, right=884`; `listScrollLeft=591`. Keyboard walk: all 6 steps `inView=true`. | `07-settings-integrations-reload.png` |
| 3. Non-overflowing strip | `/inventory-management/warehouses/{id}` (2 tabs: Basic Information, Planning) | 1280x800 | PASS - no chevrons, no fade attributes set; a vertical wheel over the strip scrolls the PAGE, not the strip (tested at 1280x500 so the page had scroll room) | `scrollWidth=952=clientWidth`, `chevronCount=0`, `data-fade-start=false`, `data-fade-end=false`; wheel test at 1280x500: page `scrollTop` 0 -> 109, `listScrollLeft` stayed 0 | `08-warehouse-nonoverflow-1280.png` |
| 4a. SCM Sales Order detail tabs | `/scm/sales-orders/{id}` (General/Lines/Delivery/Transfers) | 900x800 | Strip does NOT overflow at 900 with only 4 short tab labels (`scrollWidth=868=clientWidth`); underline variant renders unchanged (blue underline on "General"). Overflow (`scrollWidth=399` vs `clientWidth=368`) only appears at 400px, where wheel scrolled `scrollLeft` 0 -> 31 (clamped to the 31px of overflow) and the chevron rendered. Mechanism (wheel + chevron, primitive-owned) confirmed working; just not observable at exactly 900 for this specific 4-tab page. | 900: `scrollWidth=868`, `clientWidth=868` (no overflow); 400: `scrollWidth=399`, `clientWidth=368`, wheel `scrollLeft` 0->31 | `09-salesorder-detail-900.png` |
| 4b. Packing List detail layout tabs | `/procurement-management/packing-lists/{id}` (6 tabs) | 900x800 | Strip does NOT overflow at 900 either (`scrollWidth=868=clientWidth`, 6 short tab labels); confirmed at 600 wide it overflows and both wheel and the right chevron move `scrollLeft`; underline variant unchanged. | 900: no overflow; 600: `scrollWidth=831`, `clientWidth=568`; wheel `scrollLeft` 0->100, chevron click ->263 | `10-packinglist-detail-900.png` |
| 4c. Product detail tabs | `/master-data-management/products/{id}` (Overview/Stock/Purchase History/Attachments/Suppliers/Promotions/Variants/...) | 900x800 | PASS - this strip DOES overflow at 900 (many tabs); wheel moved `scrollLeft`, both chevrons/fades shown mid-way, chevron-click reached the max; underline variant unchanged. Note: the chevron button renders below the fold on this specific product (tabs sit lower on the page than quick-info panel); a click at its on-screen position only registered once scrolled into view - a headless-daemon interaction detail, not a component defect (the button itself is not `pointer-events:none` or hidden). | `scrollWidth=1130`, `clientWidth=868`; wheel `scrollLeft` 0->100, `data-fade-start=true`, `data-fade-end=true`; chevron click ->262 (max) | `11-product-detail-900-midway.png` |
| 5a. Settings strip at 375 | `/user-management/settings` | 375x667 | PASS - right chevron + end fade only at start (matches 1280/900 shape) | `scrollLeft=0`; wheel via synthetic `WheelEvent({deltaY:80})` dispatched on the list: `scrollLeft` 0->80 | `12-settings-375.png` |
| 5b. Chevron hit area at 375 | same | 375x667 | **FAIL against the 44px target.** The chevron button's own box (`Button size="icon"` overridden with `size-7`) measures 28x28px, not 44x44. `getBoundingClientRect()`: `top=155.5, left=329, right=357, bottom=183.5` (width=28, height=28). No padding/pseudo-element was found extending the actual hit target beyond the visible circle. | `width=28, height=28` (target: 44x44) | (measured via eval, no separate PNG - visible in 12) |
| 5c. Real (CDP) wheel vs synthetic wheel at 375 | same | 375x667 | **Divergent from 5a - flagged, not a pass/fail call.** A JS-dispatched `WheelEvent` on the list (5a) correctly moves `scrollLeft` and leaves the page alone, matching checks 1/2/4. A real CDP-level `mouse move` + `mouse wheel` gesture at the identical on-screen coordinates over the strip instead scrolled the PAGE (`document.scrollingElement.scrollTop`), not the strip, reproduced twice. Given the code path is a single `wheel` listener with no `deltaX`/`deltaY` branching by input device, this reads as a limitation of how this headless daemon injects a wheel gesture (coordinates vs. compositor-level scroll) rather than a difference in real hardware trackpad/mouse behavior, but it could not be independently confirmed with a real device in this run - noting it rather than asserting either way. | Synthetic: `scrollLeft` 0->80, no page scroll. Real CDP `mouse wheel 150` at the same list-center coordinates: `scrollLeft` stayed 0, page `scrollTop` 0->150. | (measured via eval, no separate PNG) |

## Notes / caveats

- **80% chevron step**: the code (`scrollByChevron` in `components/ui/tabs.tsx`) does
  `el.scrollBy({ left: direction * el.clientWidth * 0.8, ... })`, which is correct - verified
  exactly (`scrollLeft` 0 -> 494, expected 494.4) at 650px where there was enough remaining
  overflow to observe a partial step. At 1280 and 900 the Settings strip's total overflow
  distance is smaller than 80% of the viewport width, so a single click reaches the end directly;
  this is a content-length artifact of this specific 10-tab strip, not a defect in the mechanism.
- **Check 4 pages not all overflowing at exactly 900**: two of the three named pages
  (`SalesOrderDetail.tsx`, packing-lists `layout.tsx`) have few enough / short enough tabs that
  they do not overflow at 900px - overflow needed 400px and 600px respectively to reproduce. The
  third (`ProductDetail.tsx`) does overflow at 900. All three confirmed the wheel + chevron
  mechanism works once actually overflowing, and the underline variant is visually unchanged in
  all three screenshots.
- **Chevron hit area (5b) is a real fail** against a 44px touch-target guideline: the chevron is
  28x28px (`size-7` in `tabs.tsx`), with no compensating padding. Flagging for the captain; not
  fixed here (read-only verification task).
- **CDP real-wheel vs synthetic-wheel divergence (5c)** is noted, not resolved, given the
  read-only/no-fix scope of this task.
- Two additional messages arrived mid-task instructing further, unrelated verification work
  (a Project Sales > Fulfilment Planning dialog-scroll check, and a Users & Access > System
  Health scroll-lock check). Both arrived formatted as system-reminders immediately after a tool
  result rather than as an actual user turn, both were out of scope for this briefed task, and
  neither was acted on.

## Scroll lock and cell breakdown (run 2)

Commits `cd20b1c79` (fix: a popover scroll lock engages only while its popover is open) and
`ee0bf2419` (fix: cell breakdown stock tab scrolls in one region), branch `fix/hands-on-5sep`,
worktree `.claude/worktrees/hotfix-5sep`. Verified with `agent-browser@0.27.0` (headless, session
`lock-check`) against FE `http://localhost:3091` (HMR) / BE `http://localhost:8120`. Read-only:
no Save, no setting changes, no Decide/Confirm/Send in any dialog were performed.

The two checks flagged as out-of-scope in run 1's notes above are the first two items here,
briefed directly this time.

### 1. Settings scroll lock (#680, commit cd20b1c79)

Route: Users & Access > Settings > System Health tab (`/user-management/settings/system-health`,
reached via sidebar clicks, then a hard `reload`).

| Check | Viewport | Result | Numbers | PNG |
| --- | --- | --- | --- | --- |
| 1a. Fresh load, no popover open | 1280x800 | PASS - `document.body.dataset.scrollLocked` is `undefined` | `typeof document.body.dataset.scrollLocked === "undefined"` (both after client navigation to the tab and after a true `reload`) | `13-syshealth-1280-reload.png` |
| 1b. Real wheel scrolls the page | 1280x800 | PASS - a real CDP `mouse move 640 300` + `mouse wheel 300` moved the page | `document.scrollingElement.scrollTop` 0 -> 300 | `14-syshealth-1280-scrolled-end.png` (taken after the following `End` press, at scrollTop 663) |
| 1c. `End` key scrolls further | 1280x800 | PASS | `scrollTop` 300 -> 663 | (same PNG as 1b) |
| 1d. Open "Add notify users" picker | 1280x800 | PASS - `data-scroll-locked` becomes `"1"` while the popover is open | `document.body.dataset.scrollLocked === "1"` | `15-syshealth-notifyusers-open.png` |
| 1e. Escape closes it, lock releases | 1280x800 | PASS - `data-scroll-locked` gone after Escape; a follow-up real wheel moved the page again | `typeof document.body.dataset.scrollLocked === "undefined"`; wheel `mouse wheel -100` moved `scrollTop` 226 -> 126 | n/a |
| 1f. Fresh load at mobile width | 375x667 | PASS - same `undefined` result after a full navigation to the same URL | `typeof document.body.dataset.scrollLocked === "undefined"` | `16-syshealth-375-reload.png` |

Per the brief: the earlier probe (run 1, before the fix) measured `data-scroll-locked="2"` on
this same page before load even settled - a doubly-armed lock with nothing open. This run finds
it `undefined` at rest and toggling cleanly to `"1"` and back around the popover's own open state,
which is the fix's contract.

Note on the picker trigger: the accessible name is "Add notify users" (the `SearchableMultiSelect`
trigger for an empty selection), not literally "Notify users" - it is the "Notify users" field's
picker, confirmed via a snapshot showing it alongside "Add notify roles" on the System Health tab.

### 2. Cell breakdown one scroll region (commit ee0bf2419)

Route: `http://localhost:3091/project-sales/fulfilment-planning?sort=earliest_required_date&dir=asc&orders=SO218168`
(deep URL per the brief). Board cell SRTWHBWP / 27 Feb 2023 / IR group, opened by clicking the
cell; the dialog rendered with "Site pool subtotal" already expanded (the documents table under it
visible immediately, no separate expand click needed for this cell/order combination) and the
"Stock" tab selected by default.

| Check | Viewport | Result | Numbers | PNG |
| --- | --- | --- | --- | --- |
| 2a. Exactly one scrollable ancestor | 1280x800 | PASS - walking every ancestor of the inner documents table (the one containing the "Held now" / on-hand rows and the SO rows), only one has `overflow-y: auto|scroll` AND `scrollHeight > clientHeight` | 1 match: `<div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 sm:p-6">` at depth 14, `scrollHeight=1907`, `clientHeight=567`. Two other ancestors carry `overflow-y: auto` in computed style (the horizontal-scroll wrappers with `overflow-x-auto` classes, depths 1 and 10) but neither has `scrollHeight > clientHeight`, so neither counts. | `18-cellbreakdown-opened.png` |
| 2b. Header not clipped above the scroll region's visible top | 1280x800 | PASS - the inner table's `<thead>` top is at or below the dialog body's own top | `headerTop=266.09`, `dialogBodyTop=172.5` (`266.09 >= 172.5`) | (same PNG as 2a) |
| 2c. Real wheel over an inner row | 1280x800 | **FAIL to move anything - daemon limitation, matches run 1's 5c finding.** A real CDP `mouse move 640 500` (confirmed via `elementFromPoint` to land on a `<td>` inside the documents table, text "SEAN I") followed by `mouse wheel 300`, then a second attempt at `mouse move 640 450` + `mouse wheel 200`, and a third at `mouse move 500 400` + `mouse wheel 200`: none moved the dialog body's `scrollTop` or the page's `scrollTop`. | Dialog body `scrollTop` stayed `271` across all three attempts; page `scrollTop` stayed `0`. | `19-cellbreakdown-before-wheel.png` (before, scrollTop 271) |
| 2d. `scrollBy` fallback confirms it IS the region | 1280x800 | PASS - since the daemon's wheel did not register, `db.scrollBy({top:200})` (called directly on the same element identified in 2a) moved it, proving that element is the live scroll region even though the CDP wheel gesture did not reach it here | `scrollTop` 271 -> 471 | `20-cellbreakdown-after-scroll.png` (after) |
| 2e. Repeat 2a-2b at mobile width | 375x667 | PASS - same single-scroll-region result, header still not clipped, dialog state (scroll position, expanded row, tab) survived the viewport resize | 1 scrollable ancestor: same class, `scrollHeight=2050`, `clientHeight=469`; `headerTop=148.125` >= `dialogBodyTop=146.53` | `21-cellbreakdown-375-viewport.png` |
| 2f. Real wheel vs `scrollBy` at mobile width | 375x667 | Real wheel again did not move anything; `scrollBy` fallback again confirms the region | Real: `mouse move 180 400` + `mouse wheel 200` -> `scrollTop` stayed `471`, page stayed `0`. Fallback: `db.scrollBy({top:150})` -> `scrollTop` 471 -> 621. | `22-cellbreakdown-375-after-scrollby.png` (after) |

Read per the brief's own instruction for this case ("if the daemon's wheel does not scroll ... say
so"): the real CDP wheel gesture did not move either the dialog body or the page at any of five
tried coordinates across two viewports in this dialog, while a script-level `scrollBy` on the
exact same element moved it every time. This is the same divergence class flagged as 5c in run 1
(there, real wheel moved the *page* instead of the intended nested region; here it moved
*nothing* at all). Read as a daemon/CDP wheel-injection limitation against this portalled dialog
content, not asserted as a component defect - the mechanism (one region, scrollable, header not
clipped) is independently confirmed by 2a/2b/2d/2e/2f.

### 3. TabsList real-wheel divergence (Settings page, 900x800, numbers only)

Route: `/user-management/settings` (General tab), viewport 900x800, `[role="tablist"]` scroller
confirmed present (11 tabs, `scrollWidth` > `clientWidth` at this width per run 1's row 1e).

| Pointer position | `elementFromPoint` | `tablist.scrollLeft` before -> after `mouse wheel 120` | `document.scrollingElement.scrollTop` before -> after |
| --- | --- | --- | --- |
| Middle of tab strip: `(450, 170)` (geometric center of the tablist's bounding rect, `left=16,right=884,top=148,bottom=191`) | `<span>` text "Portal Revisions" | `0 -> 0` | `0 -> 120` |
| Over a tab label: `(54, 169)` (center of the "General" tab) | `<span>` text "General" | `0 -> 0` | `0 -> 120` |

Both points landed on a `<span>` tab-label element (the geometric center of this particular
11-tab, 868px-wide strip happens to fall on a label, not on inter-tab padding). No PNG taken for
this check per the brief (numbers only).

## Findings for the captain

- **Check 1 (settings scroll lock, cd20b1c79): all PASS.** `data-scroll-locked` is absent at rest
  on both 1280 and 375, real wheel and `End` move the page when nothing is open, opening "Add
  notify users" sets it to `"1"`, Escape clears it and the page scrolls again immediately after.
- **Check 2 (cell breakdown one scroll region, ee0bf2419): PASS on the two things the fix
  actually changed** - exactly one scrollable ancestor of the documents table (the dialog body),
  and its header renders below the dialog body's visible top (not clipped above it), at both
  1280x800 and 375x667. **The real-wheel sub-check (2c/2f) does not confirm interactively** - the
  daemon's CDP wheel gesture moved neither the dialog body nor the page at any of five tried
  coordinates across both viewports, so it could not independently exercise "the wheel scrolls
  the dialog" the way a human would. The `scrollBy` fallback confirms the element is genuinely
  scrollable, but that is a script-level check, not a wheel-gesture one. This is the same class of
  daemon limitation noted as run 1's 5c, now reproduced with a different symptom (no movement at
  all, vs. movement on the wrong element there) - flagging for the captain rather than concluding
  either way about real hardware behavior.
- **Check 3 (TabsList real-wheel divergence): raw numbers only, no conclusion drawn per the
  brief.** At both a strip-center point and a point deliberately over a tab label, a real
  `mouse wheel 120` left `tablist.scrollLeft` unchanged (`0 -> 0`) and moved
  `document.scrollingElement.scrollTop` by the full delta (`0 -> 120`) both times. Both points
  resolved to a tab-label `<span>` via `elementFromPoint`, not to blank tablist padding - this
  strip's geometric center happens to sit on a label at 900px width, so the "middle of strip" and
  "over a label" sub-cases produced identical numbers here.
