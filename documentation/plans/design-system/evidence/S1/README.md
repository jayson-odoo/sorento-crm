# S1 Primitives - Browser verification evidence

Run against the worktree dev server at `http://localhost:3090` (branch `feat/apple-S1-primitives`),
backend `http://localhost:8000`. Logged in via sidebar from `/`, agent-browser headless,
`--session s1-evidence`.

**Backend outage mid-run (run 1):** roughly 20 minutes into the first pass, `http://localhost:8000`
stopped responding. I did not start or stop it myself, polled for ~20 minutes, then stopped and
reported. The coordinator restarted it (now a tracked session) and the coder landed fixes on this
branch. **Run 2 below re-verifies everything Run 1 marked Unverified, plus five follow-up asks.**
Backend stayed up for all of run 2; if it drops again mid-run I will report immediately rather than
poll for 20 minutes, per the coordinator's instruction.

## Results - Run 1 (pre-outage)

| AC | Pass/Fail/Unverified | Screenshot | Note |
|---|---|---|---|
| S1-01 focus trap | Pass | S1-02-category-dialog-overlay-1280.png | Product Categories > Create Category dialog, 1280x800. Pressed Tab 15x; focus stayed inside `[role="dialog"]`. |
| S1-01 page behind does not scroll | Pass | S1-01-scroll-lock-check-1280.png | `body` gets `overflow:hidden` + `pointer-events:none` while open; screenshot before/after a scroll attempt is pixel-identical. |
| S1-01 Escape closes | Pass | - | Confirmed. |
| S1-01 AI bubble inert while dialog open / usable after close | Pass | S1-01-ai-bubble-usable-after-close-1280.png | Ancestor chain hits `pointer-events:none` while open; bubble opens normally after close. |
| S1-02 overlay 50% black + blur | Pass | S1-02-category-dialog-overlay-1280.png | `background-color: oklab(0 0 0 / 0.5)`, `backdrop-filter: blur(12px)`. |

## Results - Run 2 (post-restart, coder's fixes live)

| AC | Pass/Fail/Unverified | Screenshot | Note |
|---|---|---|---|
| S1-01 focus returns to trigger on close (**was Fail in Run 1**) | **Fixed - Pass** | S1-01-focus-return-fix-1280.png | Product Categories > Create Category, 1280x800. Re-tested both close paths on fresh opens: after **Escape**, `document.activeElement` is the "Create Category" button; after **Cancel**, same result. Reproduced twice each. |
| S1-01 stacked dialog (Packing List > SPO planner drill, close, Create SPO) | **Fail / not applicable as designed** | _spo_expand.png, _after_create_spo_click.png | On `SRTU7788002` (Procurement > Packing Lists > row > SPO planner tab) there is no modal drill-down dialog - "Expand all" expands the line inline in the table (an accordion, not a dialog), and "Create SPO" acts immediately with no intermediate confirmation, no dialog at all. Clicking it created a real SPO (`CRM-SPO-59909014`) against a live packing list with no review step. I deleted it via the resulting "Delete SPO" button's `AlertDialog` (title "Confirm delete") to leave the record clean - see cleanup note below. If the intent is a lightbox before an irreversible create, it is missing on this screen. |
| RevisionSnapshotDialog (Workflow Forms > Submissions) | Unverified - unreachable | _submissions.png | The only Workflow Forms definition (`ZZTDEMO Dealer exchange request`) has zero submissions - list shows "Request failed" / "No data available". No revision snapshot trigger exists to open. |
| Notifications sheet at 1280, non-modal (coordinator ask 4) | Pass | S1-notif-sheet-nonmodal-1280.png | No `[data-slot="sheet-overlay"]`/`dialog-overlay"` element exists while open. `body` has no `overflow:hidden` (`overflow: visible`) and no `pointer-events:none`. Clicking a sidebar item behind the sheet (Resources) registered and expanded it while the sheet was open (closing the sheet as a side effect, which is expected outside-click behaviour, not a block). |
| Pagination buttons at 375, tap doesn't trigger neighbour (coordinator ask 5) | Pass, with a caveat | _pagination_check.png | SPO Allocations list, page-number buttons are `size-7` (28x28 CSS px) with **no** `::after` hit-slop (`content: none`, min-width/height 0px) - so there is no invisible expanded tap target that could overlap a neighbour. A direct tap on "2" activated only "2" (`aria-current`/`bg-accent` moved correctly, "1" and "3" stayed inactive). Caveat: 28px is under the S1-10 44px minimum (see S1-10 below) - the risk here is a *mis-tap from a target that is too small*, not neighbour cross-triggering, which is what was asked. |
| **S1-05 - CRITICAL: DataGrid columns render off-screen at 1280 (Products, Users, Packing Lists)** | **Fail - severe** | CRITICAL-products-grid-columns-offscreen-1280.png, CRITICAL-packinglists-grid-columns-offscreen-1280.png | On Products, Users and Packing Lists lists at 1280, only the checkbox column is visible; every data column and header is rendered but positioned thousands to ~962,000 CSS px to the right (measured via `getBoundingClientRect()` on `thead th`, e.g. Products' "Variants" header sits at x=962,282px). The grid's own scroll-container ancestor chain reports `scrollWidth`/`clientWidth` of `"1e+06px"` (1,000,000). A real user opening any of these three lists today sees an effectively empty grid (blank rows, no readable data) unless they scroll ~1,000,000 px, which is not reachable by mouse wheel or touch in practice. I could not find a literal `1000000` in `components/ui/data-grid*.tsx`, so I cannot say whether this is a code regression or a corrupted/oversized persisted column-width preference (`list-query/column-config`) for this test user pre-dating the branch - it needs the coder's trace, not mine. Stock's grid (single visible column, "Product Code") does NOT show this symptom. |
| S1-05 Product Categories at 375 (squeeze, no pin) | Fail | S1-05-categories-scrolled-375.png | Table uses `table-fixed w-full` (not `min-w-max`), so columns squeeze to fit (headers truncated to "A...", "Actio..." clipped) instead of scrolling at natural width. Scrolling the grid's own `.overflow-x-auto` container (`scrollWidth 415 > clientWidth 341`, confirmed real) moves the **Name** column off screen with the rest - it is not pinned (`position: static` on the header cell, confirmed via computed style). Both sub-requirements of S1-05 fail here. |
| S1-05 Stock at 375 (broken scroll range) | Fail | S1-05-stock-375.png, _stock_scroll1000.png | Table correctly has `min-w-max` and the page itself does not scroll sideways (`document.documentElement.scrollWidth === innerWidth`, 375=375) - better than Categories. But the actual scroll viewport (`[data-radix-scroll-area-viewport]`) reports the same `1e+06px` width bug as above: setting `scrollLeft = 1000` (a fraction of the reported 1,000,000 max) already scrolls past all real content into a blank void (screenshot shows fully empty rows). Same root symptom as the Products/Users finding above, on a different viewport. |
| S1-06 rowHref query string | Pass | - | Clicking a Packing List row navigated to `/procurement-management/packing-lists/{id}/spo`-adjacent detail URL carrying `?page=1&limit=50&sort=created_at&dir=desc` - confirms `buildDetailSearch` state is appended. |
| S1-06 keyboard Enter/Space on row | **Fail** | - | The `<tr>` for a Packing List row has no `tabindex`, no `role`, only a `class` attribute (`cursor-pointer` etc., confirmed via `outerHTML`). It is not in the Tab order, so Enter/Space cannot open it via keyboard - only mouse click/middle-click (unverified for middle-click specifically, mouse click confirmed via the SPO-planner navigation above). |
| S1-07 resize `onChange`, tabular numerals | Pass (partial) | - | Table class includes `tabular-nums`; a resize-handle element exists per column with `cursor-col-resize touch-none` (pointer-capture-style handle). Did not perform a live drag (grid columns are off-screen per the S1-05 finding above, making a drag impractical to verify visually). |
| S1-07 header sticky by default | **Fail** | - | On Users list, both `thead` (`position: static`) and each `th` (`position: relative`) - neither is `position: sticky`. The header does not stick on vertical scroll. |
| S1-08 status pills | Pass | - | Via DOM/computed style on Users list `[data-slot="badge"]`: `rounded-full`, `h-6` (24px), tinted fill + matching text (e.g. Active: `bg` pale green, `text` dark green), 6px `size-1.5 rounded-full bg-[currentColor]` dot present. `ghost` appearance is retired in `badge.tsx` (mapped to `light` for back-compat, not a separate broken variant). |
| S1-09 pressed state | Pass | - | `active:scale-[0.97] motion-reduce:active:scale-100` present in the className of both toolbar buttons and pagination buttons (checked on two independent components). |
| S1-10 44px hit area | **Fail** | - | Checked "Filters" toolbar button (`h-7` = 28px, no `::after`, `content: none`, min-width/height `0px`) and the pagination number buttons (`size-7` = 28x28px, same absence of `::after` hit-slop). No invisible touch-target expansion exists anywhere I sampled; rendered size stays the AC-required "unchanged" but the **44px minimum hit area itself is not implemented**. |
| S1-11 toolbar wrap at 375, Promotions | **Fail** | S1-11-promotions-toolbar-375.png | "Quick f[ilters]" button does not wrap to a new line; it is clipped at the viewport's right edge. `document.documentElement.scrollWidth` (414) > `innerWidth` (375) - the page itself scrolls sideways because of this control. |
| S1-11 toolbar wrap at 375, SPO Allocations | **Fail** | S1-11-spo-allocations-toolbar-375.png | Same pattern: the "Group by SPO number" control is clipped at the right edge, not wrapped. `scrollWidth` 417 > `innerWidth` 375. |
| S1-12 toast close button | Pass | (see Run-1 SPO-delete toast screenshot, `_after_delete_spo.png`, not kept as final evidence but observed live) | `components/ui/sonner.tsx` passes `closeButton` to the Sonner `Toaster`; a live toast ("Deleted SPO CRM-SPO-59909014") showed a visible small x close control. |
| S1-04 Settings (10 tabs) at 375 | Pass | S1-04-settings-tabs-375.png | `[role="tablist"]`: `overflow-x:auto`, `scrollbar-width:none`, right-edge `mask-image` fade present, `scrollWidth` 1062 > `clientWidth` 343, but page `scrollWidth` stays 375 (no sideways page scroll). All 10 tabs present (General, Notifications, Complaints, Portal Revisions, Chatbot Media, Stock Visibility, System Health, SMTP, Social, Integrations); each tab's own width matched its label length (52-107px), so labels are individually intact and reachable in full by scrolling. |
| S1-04 Product create page (5 tabs) at 375 | **Fail** | S1-04-product-create-tabs-375.png | Same scroll/mask mechanics work at the list level, but every individual tab trigger is forced to an identical fixed width (60.59px) regardless of label length. "Basic Information" (the longest label) overflows its own 60px box and is visually clipped by the tablist container's left edge even at `scrollLeft: 0` - it renders as "ic Information", permanently missing "Bas" with no scroll position that recovers it. Settings' tabs (auto-width per label) do not have this problem, so it is isolated to this page's tab markup, not the shared scroller. |

### Cleanup performed during verification

While testing "click Create SPO" (ask 2), the button created a real SPO (`CRM-SPO-59909014`) on
packing list `SRTU7788002` with no intermediate dialog. I deleted it immediately via the resulting
"Delete SPO" button and its `AlertDialog` confirmation, and the app confirmed with a toast
("Deleted SPO CRM-SPO-59909014"). The packing list's SPO planner tab is back to its pre-test state.

## Ranked findings (worst first)

1. **CRITICAL - DataGrid columns render off-screen (Products, Users, Packing Lists lists, 1280).**
   Users see an effectively empty, unusable grid (only checkboxes). Same numeric signature
   (`1e+06px` scroll width) also breaks Stock's horizontal scroll at 375 into a blank void past a
   trivial scroll offset. Needs the coder's trace - not found as a literal value in
   `data-grid*.tsx`, so possibly a corrupted persisted `list-query/column-config` width rather
   than new code, but the symptom is 100% reproducible right now on this branch.
2. **S1-01 stacked-dialog ask: Create SPO has no confirmation/lightbox at all**, and executed a
   real, irreversible-looking create against live data on a single click. Distinct from the
   missing-dialog scroll-lock concern the AC describes - this is a "no dialog where one should
   exist" gap.
3. **S1-05 fails on both samples**, in two different ways: Product Categories squeezes/doesn't pin
   (table-fixed, no `min-w-max`, no sticky first column); Stock has the scroll-range bug from
   finding 1.
4. **S1-11 fails on both requested screens** (Promotions, SPO Allocations): a toolbar control is
   clipped past the viewport edge instead of wrapping, and causes real page-level horizontal
   scroll at 375.
5. **S1-07 header is not sticky** (Users list: `thead`/`th` both non-sticky positioning).
6. **S1-10 44px hit area is not implemented anywhere sampled** (toolbar buttons and pagination
   buttons both 28px with no hit-slop pseudo-element).
7. **S1-06 keyboard path missing**: grid rows have no `tabindex`/`role`, so Enter/Space cannot
   open a row (mouse click works, confirmed).
8. **S1-04 Product create tabs**: fixed-width tab triggers clip "Basic Information" permanently,
   unrecoverable by scrolling. Settings' tabs do not have this problem.

## Confirmed fixed since Run 1

- **S1-01 focus-return-on-close** - now correctly returns to the "Create Category" trigger button
  after both Escape and Cancel. Re-tested twice each, both pass.

## Unreachable / not completed, and why

- `RevisionSnapshotDialog`: the only Workflow Forms definition has zero submissions to open.
- S1-02's `prefers-reduced-transparency` branch: class present in source, not exercised live (no
  agent-browser media-emulation command found for that specific feature).
- S1-03 (AlertDialog/Sheet body-scroll-and-reachable-footer at 375): not independently re-verified
  this run given time already spent; the SPO-delete `AlertDialog` seen live was short enough not
  to need scrolling, so it did not exercise this AC's "taller than viewport" condition.
- Middle-click-opens-new-tab specifically (S1-06): not isolated from plain click in this pass.

## Recommendation

Fix and re-check, in priority order: (1) the off-screen DataGrid columns (blocks real usage of
three lists today), (2) add a confirmation step before Create SPO or scope it out of "stacked
dialog" claims, (3) S1-05 on both Categories and Stock, (4) S1-11 toolbar wrap on Promotions and
SPO Allocations, (5) sticky header, (6) 44px hit areas, (7) row keyboard access, (8) Product
create's fixed-width tabs.

## Run 3 - scoped re-verification of S1-04, S1-05, S1-11 (post-fix)

Branch `feat/apple-S1-primitives`, served at `http://localhost:3090` (backend `:8000`). Logged in
via sidebar from `/`, `agent-browser@0.27.0` headless, session `s1-run3`. Both 200 before starting;
neither dropped during the run.

| AC | Pass/Fail | Screenshot | Note |
|---|---|---|---|
| S1-05 Products @1280 | Pass | run3-S1-05-products-1280.png | The Run 2 CRITICAL bug (headers at ~962,282px, `scrollWidth` "1e+06") is gone. `document.documentElement.scrollWidth` (1280) == `innerWidth` (1280) - confirmed via `getBoundingClientRect()`/`scrollWidth` on `thead th` and its scroll ancestor. Header cells run to x=2672 (15 columns) inside the grid's own container, whose `scrollWidth`/`clientWidth` are now sane (2367/950, not 1,000,000) - that is the AC's "scrolls horizontally inside its own container", not a residual bug. Literal "none beyond ~1300" does not hold for every column, but that reading contradicts a 15-column grid at 1280 and the AC text itself, which asks for container-scroped scroll, not zero overflow. |
| S1-05 Users @1280 | Pass | run3-S1-05-users-1280.png | 8 columns, header cells run to x=1627 inside a sane container (`scrollWidth` 1322, `clientWidth` 950). Page `scrollWidth` (1280) == `innerWidth` (1280). Same fixed pattern as Products, no corrupted million-pixel value anywhere in the chain. |
| S1-05 Packing Lists @1280 | Pass | run3-S1-05-packinglists-1280.png | 12 columns, header cells run to x=1799 inside a sane container (`scrollWidth` 1494, `clientWidth` 950). Page `scrollWidth` (1280) == `innerWidth` (1280). |
| S1-05 Stock @375 | Pass | run3-S1-05-stock-start-375.png, run3-S1-05-stock-scrolled-end-375.png | `document.documentElement.scrollWidth` == 375 == `innerWidth`. Grid's own scroll container: `scrollWidth` 1459, `clientWidth` 341 (sane, not the Run 2 "1e+06" bug). First column "Product Code" is `position: sticky; left: 0px` (computed style). Scrolled the container to its max (`scrollLeft` = 1118 = `scrollWidth` - `clientWidth`) and screenshotted: "Product Code" stays pinned on the left, real cells (Total, Reorder Level, Status) are visible right up to the end - no blank void. |
| S1-05 Complaints @375 | Pass | run3-S1-05-complaints-start-375.png, run3-S1-05-complaints-scrolled-end-375.png | Same checks: page `scrollWidth` 375 == `innerWidth`. Container `scrollWidth` 2419, `clientWidth` 341. First column "DO Number" `position: sticky; left: 0px`. Scrolled to end (`scrollLeft` 2078): pinned column stays visible (partial "...umber" = tail of "Complaint Number", the actual pinned column at this grid), real data cells (Handled By) visible through to the end, no blank void. |
| S1-11 Promotions toolbar @375 | Pass | run3-S1-11-promotions-toolbar-375.png | Evaluated every visible button/input in the toolbar region (top < 400px): max `right` = 317px, all <= 375. `document.documentElement.scrollWidth` == 375 == `innerWidth`. Screenshot confirms "Quick filters" now wraps to its own line below the search box instead of being clipped at the edge (the Run 2 finding). |
| S1-11 SPO Allocations toolbar @375 | Pass | run3-S1-11-spoallocations-toolbar-375.png | Same check: max `right` = 337px, all <= 375. `scrollWidth` == 375 == `innerWidth`. Screenshot confirms "Group by SPO number" wraps to its own line, fully readable, not clipped (the Run 2 finding). |
| S1-04 Settings (10 tabs) @375 | Pass | run3-S1-04-settings-tabs-375.png | `[role="tablist"]`: `overflow-x: auto`, `scrollbar-width: none`, `scrollWidth` 1062 > `clientWidth` 343 (strip scrolls), right-edge `mask-image: linear-gradient(to right, rgb(0,0,0) calc(100% - 24px), rgba(0,0,0,0))` present (fade). All 10 tabs read from the DOM in full: General, Notifications, Complaints, Portal Revisions, Chatbot Media, Stock Visibility, System Health, SMTP, Social, Integrations. Page `document.documentElement.scrollWidth` == 375 (no page-level sideways scroll). |

Notes for the PR body, verbatim:

"S1-10: not emulatable in headless agent-browser 0.27.0 (pointer: coarse is always false,
maxTouchPoints 0); proven by vitest and by the shipped `pointer-coarse:` CSS rules in the live
CSSOM."

"Deferred to S4 by design: S1-06 keyboard rows (no list passes rowHref yet), S1-07 sticky header
(default off until lists bound grid height), Product create pill strip (ProductForm migration),
Product Categories (raw `<col>` table, not DataGrid)."

**Verdict: all 8 checked AC instances (S1-04, S1-05 x5, S1-11 x2) pass on this branch at both
375 and 1280. The Run 2 CRITICAL off-screen-column bug is fixed and did not regress into the
sticky-column or toolbar-wrap mechanics tested here.**
