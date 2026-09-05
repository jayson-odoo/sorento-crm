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
