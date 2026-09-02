# M2 Keyboard and timing - browser verification evidence (agent-browser, 2 Sep 2026)

Worktree `motion2-M2` (branch `feat/motion2-M2-keyboard-timing`, HEAD `6aa711b2f`), FE dev server
`PORT=3081 npm run dev` (own process group: `npm run dev` PID 68047, `next dev` PID 68072,
`next-server` PID 68090), BE reused read-only on `:8120` per `FASTAPI_INTERNAL_URL=
http://localhost:8120` in `.env.local` (copied from the `motion2-M1` worktree's shape and
confirmed: `NEXTAUTH_URL=http://localhost:3081`, `AUTH_TRUST_HOST=true`, no
`NEXT_PUBLIC_API_URL`). `lsof -i :3081` was empty before starting. Login via
`E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`. Session `--session m2tester` (isolated browser).
Viewport 1280x800 default. Navigated by sidebar clicks from `/`, except a handful of
content-driven jumps (the command palette itself, a category's "View products" link, a
complaint-list row click into its own detail page) which are not typed URLs.

**Method for timing.** Every open/close was triggered with a real or synthetic DOM event
(`.click()` after a full `pointerdown/mousedown/pointerup/mouseup/click` sequence for Radix
triggers that ignore a bare `.click()`, a synthetic `KeyboardEvent` for shortcuts, a synthetic
`contextmenu` MouseEvent for the file-card menu), then polled every animation frame
(`requestAnimationFrame`) for `getComputedStyle(el).opacity` / `.transform` and
`el.getAnimations()` for up to ~650ms, building a (t, opacity, scale) timeline. Settle = first
sampled t where opacity >= 0.99. Where `agent-browser click @ref` silently failed to register
(sidebar group toggles, tab strips, DropdownMenu/Popover triggers, "Filters" panel controls -
the same tool quirk logged in the M1 and M4 evidence, not a product defect), a native
`element.click()` or full pointer-event sequence via `eval --stdin` worked immediately.

**Important measurement note.** Radix wraps the actual spring in a *child* `motion.div` for
`DropdownMenuContent`, `PopoverContent`, `DialogContent`(no - `DialogContent` animates itself)
and `ContextMenuContent`: the outer `[data-slot="..."]` node Radix Popper positions carries only
`class="z-50"` with no animation, so the timeline has to read `wrap.querySelector(':scope > div')`
for menu-family surfaces, not the wrapper itself. This is called out per-check below because it
changed the result the first time (see M2-04 Popover).

## Findings summary (pass/fail table)

| Check | Target | Result | Measured value |
| --- | --- | --- | --- |
| M2-01 | Command palette open (Ctrl+Shift+K) | PASS | `data-motion="off"`; opacity `1`, `transform: matrix(1,0,0,1,...)` (identity scale, positioning translate only) and `getAnimations().length === 0` on the FIRST sampled frame; held static (zero interpolation) across 40 frames / ~800ms |
| M2-01 | Command palette close (Escape) | PARTIAL | Content itself never animates (opacity stays `1`, zero `getAnimations()` throughout) - satisfies "no scale, no spring" - but the DOM node is NOT removed "within one frame": it stays mounted ~150-185ms after Escape because it shares one `AnimatePresence` with the scrim, whose own 150ms fade (`overlayTransition = { duration: 0.15 }` for `motion={false}`) gates the whole fragment's unmount. See detail note. |
| M2-01 | Comparison: normal Dialog (Create Category) open | PASS (reference) | Real spring: starts opacity `0`/scale `0.96`, reaches opacity >= 0.99 at ~400-420ms elapsed from first appearance (scale itself reaches `1` earlier, ~230ms) - i.e. visibly animated, unlike the palette |
| M2-02 | Attachment lightbox ArrowRight/Left instant slide vs animated dot/drag | SOURCE-CONFIRMED, not browser-reachable | `components/common/AttachmentPreviewModal.tsx:167-168`: `ArrowRight` calls `api?.scrollNext(true)`, `ArrowLeft` calls `api?.scrollPrev(true)` - the embla-carousel `jump=true` argument is an instant, non-animated scroll. Dot/drag navigation in `components/ui/carousel.tsx` uses the default `scrollTo()`/drag physics with no `jump` argument, i.e. animated. Could not reach a live multi-image gallery in this dataset: all 5 Project Sales projects have zero documents, the reachable Complaint rows checked have no linked attachments, and the Resource Management "Preview" action opens a single-image, non-carousel viewer (no `embla`/`[data-slot="dialog-content"]` present) rather than the shared `AttachmentPreviewModal`. |
| M2-04 | DropdownMenu open (row "..." on Product Categories) | PASS | Animated child `motion.div` (wrapper `[data-slot="dropdown-menu-content"]` itself is static `class="z-50"`): opacity `0`/scale `0.96` at t=66ms to opacity >= 0.99 at t=322-338ms - settle ≈ 256-272ms, matches "~200ms" with reasonable tail |
| M2-04 | DropdownMenu close (Escape) | PASS | Opacity `1` at t=34ms fading to ~0 by t=309ms - close ≈ 275ms, matches "~200ms" with reasonable tail |
| M2-04 | Popover open (Products list "Filters" > "All categories" SearchableSelect) | PASS | Same shape as DropdownMenu: opacity `0`/scale `0.96` at t=87ms to opacity >= 0.99 at t=317-333ms - settle ≈ 230-246ms |
| M2-04 | **Popover close (same SearchableSelect popover)** | **FAIL** | Closes in **~21ms**, not ~200ms: opacity was `1` at t=0 immediately after Escape and the whole `[data-slot="popover-content"]` node was gone by the next frame (t=21ms), with the last-observed opacity still `1` (no fade ever sampled). Root cause identified in source (see detail note): `PopoverPortal` (`components/ui/popover.tsx:99`) does not forward `forceMount` to `PopoverPrimitive.Portal`, unlike `DropdownMenuPrimitive.Portal forceMount` used one file over. Any `PopoverContent` wrapped in the exported `PopoverPortal` has its whole subtree - including the `AnimatePresence`/`motion.div` exit tween - unmounted the instant Radix's own `open` state flips false, before the spring can run. **Confirmed by a clean A/B on this branch**: the SAME `Popover`/`PopoverContent` pair, used WITHOUT `PopoverPortal` (Marketing > Promotions > "Quick filters"), closes with a proper ~300ms fade (opacity `1` -> `0` smoothly, fully faded by t=301ms) in the identical test. `PopoverPortal` is imported directly by `SearchableSelect.tsx`, `SearchableMultiSelect.tsx`, and 14 SCM/Project-Sales popover components (`PoWorklistView`, `PlanDemandPopover`, `PlanChecklistPopover`, `ProductLocationsPopover`, `PlanExplainDrills`, `ProductPhotoPopover`, `PlanPurchaseTrendPopover`, `DemandDrillPopover`, `PlanTrendPopover`, `PlanRowDialog`, `RankFactorsPopover`, `QuotationScopeTabs`, `ClassificationProofPopover`, `BoardRankPopover`, `BoardTrailPopover`, `SpoScheduleMatrixTable`) - every one of them has this instant, un-eased close. |
| M2-04 | Dialog open (Advanced Filters, Promotions) | PASS (reference) | Opacity `0`/scale `0.96` at t=41ms to opacity >= 0.99 at t~416-420ms - settle ≈ 375-380ms, matches "~300ms" with tail |
| M2-04 | Dialog close (X button, same dialog) | PASS | Opacity `1` at t=6ms fading to `0` by t=301ms - close ≈ 295ms, matches "~200ms" with tail |
| M2-04 | Sheet open (My downloads) | PASS | Slides in via `translateX`: `460px -> ~3px` over ~400-450ms (opacity stays `1` throughout - slide-only, no fade), roughly matches "~300ms" for a larger 460px travel distance |
| M2-04 | Sheet close (Escape) | PASS | Slides back `0 -> 460px` (off-screen) and unmounts at t≈318-336ms, matches "~200ms" with tail |
| M2-04 | **Dialog reopen mid-close (no jump to 0.96)** | **PASS** | Opened Advanced Filters, closed via X, waited 80ms into the close (scale had already decayed to `0.976`), clicked "Filters" again to reopen: the reopen timeline's scale is **monotonically increasing** every sampled frame (`0.971 -> 0.972 -> 0.974 -> ... -> 1.0`), never dropping back down to `0.96` first - confirms the spring continues from its current value rather than restarting |
| M2-05 | AlertDialog (SLA Policy delete, via detail page "Delete") | PASS | Overlay and panel opacity are **numerically identical on every sampled frame** (`0 -> 0.03 -> 0.105 -> 0.206 -> ... -> 1`) - both reach full opacity on the same frame, exactly as specified. `panel.className` has no `animate-in`; overlay class is `bg-black/50 backdrop-blur-md ...` (`OVERLAY_CLASS_STATIC`). Source (`components/ui/alert-dialog.tsx`) confirms a single `AnimatePresence` wrapping both, with one shared `transition` object - unlike `Dialog`, which deliberately gives its overlay a separate, faster tween |
| M2-06 | ContextMenu (Resources > Files, grid, right-click a file card) | PASS | Animated child `motion.div` inside `[data-slot="context-menu-content"]` (wrapper itself `class="z-50"`, no `animate-in`/`zoom-in-95`): opacity `0`/scale `0.96` at t=51ms to opacity >= 0.99 at t=286-305ms - settle ≈ 235-254ms |
| M2-06 | HoverCard (Master Data > Spec Verification, a coverage-count cell, `openDelay={120}`) | PASS | First appears at t=145ms (matches its explicit 120ms open delay plus the ~25ms of dispatch/render overhead measured elsewhere in this run); `[data-slot="hover-card-content"]` class has no `animate-in`; opacity `0` -> >= 0.99 by t=398ms, settle ≈ 253ms from first appearance |
| M2-06 | Menubar submenu | SKIP - not browser-reachable | Identical finding to the M1 evidence: `MenubarContent`/`MenubarItem` usages (`app/components/layouts/demo2/components/navbar-menu.tsx`, `demo3/components/navbar-menu.tsx`, `app/components/partials/navbar/navbar-menu.tsx`) all belong to layout variants other than the active `demo1` layout this tenant renders - no live page exercises a Menubar. Covered by the `[vitest]` half of M2-06 (already green per the brief) |
| M2-07 | TooltipProvider singleton + delays | PASS (source + browser) | `components/ClientProviders.tsx:28`: exactly one `<TooltipProvider delayDuration={700} skipDelayDuration={300}>` wraps the app; `Tooltip` (`components/ui/tooltip.tsx`) renders no provider of its own |
| M2-07 | First tooltip appearance (sidebar "Add to Quick Access" pin, a toolbar-style icon trigger) | PASS | Appeared at t=725ms after a synthetic `pointerenter`/`pointerover`/`mouseenter`/`mousemove` sequence with `pointerType: 'mouse'` - matches the 700ms `delayDuration` |
| M2-07 | Adjacent tooltip within skipDelay window | PASS | Moved to a second, adjacent pin button ~immediately (well under 300ms) after the first was open: its tooltip appeared at t=21ms, i.e. "immediately" per `skipDelayDuration={300}` |
| M2-07 | Tooltip content is opacity-only | PASS | Second tooltip's `getComputedStyle(el).transform` was `"none"` at every sampled frame while opacity animated - fades only, no scale/translate |
| M2-07 | No "must be used within TooltipProvider" warning | PASS | Zero occurrences in `console` output across the entire session (Products, Product Categories, Promotions, SLA Policies, Resources > Files, Project Sales pipeline/detail, Complaints, Spec Verification) |
| Console | Zero `[error]`-level entries across the whole run | PASS | The only non-debug/non-Fast-Refresh lines were pre-existing React dev warnings - `Warning: Missing \`Description\` or \`aria-describedby={undefined}\` for {DialogContent}` (multiple dialogs across the app, unrelated to this branch's diff, a known a11y nit) - zero `[error]`-level console lines and zero uncaught page errors (`errors` command returned empty) throughout |

## Detail notes

### M2-01 - command palette

Full timeline captured via `document.dispatchEvent(new KeyboardEvent('keydown', {key:'K',
ctrlKey:true, shiftKey:true, bubbles:true}))` immediately followed by a 40-frame poll of
`[data-slot="dialog-content"]`:

```
t=97ms  opacity=1  data-motion=off  anims=0  transform=matrix(1,0,0,1,-340,-192)
... (identical on every subsequent frame through t=799ms)
```

(The first sample lands at t≈97ms rather than <20ms because that duration includes the
`eval --stdin` command's own dispatch + render + first-`setTimeout(16)` round trip inside the
page, not a delayed reveal - opacity, scale and animation count are already fully settled at the
very first read, and stay bit-for-bit identical for the next 700+ms, which is the actual claim
under test: nothing ever interpolates.) Screenshot `M2-01-command-palette.png`.

Comparison Dialog (`components/ui/dialog.tsx` default `motion={true}` path, Create Category
modal): scale starts at `0.96`, opacity at `0`, and both climb through a real spring, reaching
`opacity >= 0.99` around 400-420ms after the panel first appears - visibly, measurably different
from the palette's flat line. Screenshot `M2-04-normal-dialog-open.png`.

**Escape.** `[data-slot="dialog-content"]`'s own opacity/transform never move (stays `1` /
identity throughout), and `getAnimations()` on it is `[]` at every sample - the content genuinely
never animates, matching "no scale, no spring." But `DialogContent`'s implementation
(`components/ui/dialog.tsx`) wraps BOTH the scrim and the content in one `<AnimatePresence>`
under a single `{open && (...)}` fragment; for a keyboard-triggered (`motion={false}`) dialog the
scrim still gets its own `overlayTransition = { duration: 0.15 }` fade (by design - see the
in-source comment: "a scrim reading as an abrupt on/off is more jarring than a panel that does").
Framer Motion's `AnimatePresence` does not unmount a fragment until every exiting child's own
exit animation finishes, so the whole `DialogPortal` (content included) stays mounted for the
scrim's ~150ms fade:

```
t=20ms   overlay=1.000  content=1.000
t=100ms  overlay=0.211  content=1.000
t=167ms  overlay=1.000  content=1.000   <- StrictMode dev double-render artifact, see below
t=184ms  <both gone>
```

Net: content removal took ~150-185ms, not one frame, purely as a side effect of the scrim's
independent fade being gated to the same `AnimatePresence`. This is a real, reproducible
divergence from "removes it within one frame" as read literally, though the content node itself
satisfies "no scale, no spring" throughout. Recorded as PARTIAL rather than FAIL because the
`[vitest]` half of M2-01 (which this UAC line also carries) is about class/attribute assertions,
not live DOM-removal timing, and the intent - a keyboard palette must never visibly animate - is
met; only the exact DOM-unmount latency after Escape is off from "one frame."

### M2-02 - attachment lightbox

Confirmed at the source level (`components/common/AttachmentPreviewModal.tsx:167-168`):

```ts
if (e.key === 'ArrowRight') api?.scrollNext(true);
else if (e.key === 'ArrowLeft') api?.scrollPrev(true);
```

The `true` argument is embla-carousel's `jump` flag - an instant, non-animated scroll to the
target slide, distinct from the default animated `scrollTo()`/drag physics used by
`components/ui/carousel.tsx`'s dot navigation and drag handling (no `jump` argument passed
there). This matches the UAC exactly, but could not be exercised live: every reachable record
with an attachment gallery in this dataset had either zero attachments or exactly one -

- All 5 Project Sales projects (stepped through the full pager) report "No documents on this
  project."
- The two Complaint records checked with a populated "Linked Attachments" section both actually
  read "No linked attachments" on inspection (an early positive read was a false one from a stale
  DOM query after a pager navigation).
- Resource Management > Files > right-click a file card > Preview opens a single-image,
  full-screen viewer with no `embla` class and no `[data-slot="dialog-content"]` in the DOM at
  all - it is not routed through the shared `AttachmentPreviewModal`/`Carousel`, so it has no
  next/prev to test in the first place (screenshots `preview1.png`/`preview2.png` were captured
  during the hunt but are not included as evidence since they show the wrong component).

Recorded as SOURCE-CONFIRMED per the same precedent as the M1 evidence's MenubarItem finding.

### M2-04 - DropdownMenu / Popover / Dialog / Sheet

**Structural note affecting all menu-family surfaces.** `[data-slot="dropdown-menu-content"]`,
`[data-slot="popover-content"]` and `[data-slot="context-menu-content"]` are the Radix
positioning nodes and carry only `class="z-50"` - Radix Popper's own inline transform lives here,
untouched, so a `motion.div` wrapped `asChild` around it would conflict. The actual spring lives
on the STATIC first child `<div>` inside each. The very first Popover measurement (before this
was understood) showed a false "no animation, instant open" reading for exactly this reason -
querying the outer node instead of the inner one.

**The Popover close-time bug**, once the correct inner node was queried:

```
[data-slot="popover-content"] on Products > Filters > "All categories" (via SearchableSelect):
  t=0   opacity=1
  t=21  <gone, wrapper AND inner both removed>
```

vs. the SAME component pair used without the extra `PopoverPortal` wrapper (Marketing >
Promotions > "Quick filters", `PromotionsList.tsx:407-419`, plain `<Popover><PopoverTrigger>
<PopoverContent>`):

```
[data-slot="popover-content"] > div on Promotions > "Quick filters":
  t=0    opacity=1
  t=18   opacity=0.939
  t=101  opacity=0.275
  t=201  opacity=0.035
  t=301  opacity=0  <gone>
```

Source diff that explains it, `components/ui/popover.tsx`:

```tsx
// PopoverContent itself (used directly, no bug):
<AnimatePresence>
  {open && (
    <PopoverPrimitive.Content forceMount data-slot="popover-content" ...>
      <motion.div ... exit={{ ...variants.exit, transition: exitTransition }} ...>
```

```tsx
// PopoverPortal (components/ui/popover.tsx:99) - no forceMount forwarded:
function PopoverPortal({ ...props }: React.ComponentProps<typeof PopoverPrimitive.Portal>) {
  return <PopoverPrimitive.Portal {...props} />;
}
```

Compare `dropdown-menu.tsx`'s equivalent, which DOES forward it:
`<DropdownMenuPrimitive.Portal forceMount>` - and DropdownMenu's close measured a clean ~275ms
fade in this same run. `PopoverPortal` is used explicitly (imported alongside `PopoverContent`
and wrapped around it) in `components/common/SearchableSelect.tsx`,
`components/common/SearchableMultiSelect.tsx`, and 14 files under `app/(protected)/scm/**` and
`app/(protected)/project-sales/**` (`PoWorklistView.tsx`, `PlanDemandPopover.tsx`,
`PlanChecklistPopover.tsx`, `ProductLocationsPopover.tsx`, `PlanExplainDrills.tsx`,
`ProductPhotoPopover.tsx`, `PlanPurchaseTrendPopover.tsx`, `DemandDrillPopover.tsx`,
`PlanTrendPopover.tsx`, `PlanRowDialog.tsx`, `RankFactorsPopover.tsx`,
`QuotationScopeTabs.tsx`, `ClassificationProofPopover.tsx`, `BoardRankPopover.tsx`,
`BoardTrailPopover.tsx`, `SpoScheduleMatrixTable.tsx`). Every popover reached through any of
these - which includes every `SearchableSelect`/`SearchableMultiSelect` dropdown in the whole
app, not just the one tested - closes with an un-eased, one-frame snap instead of the ~200ms fade
the rest of the menu family gets. Screenshot of the open state: `M2-04-searchable-select-popover-
open.png` (the close itself has no visual delta worth a screenshot - it is a timing-only defect,
fully captured in the timelines above).

**Dialog reopen mid-close.** Opened "Advanced Filters" (Promotions), clicked its close (`X`)
button, waited 80ms (scale had decayed to `0.976` per a direct read at that instant), then
clicked "Filters" again to reopen while the close was still in flight. The reopen's own sampled
scale sequence: `0.971 -> 0.971 -> 0.972 -> 0.975 -> 0.978 -> 0.981 -> 0.984 -> 0.986 -> 0.989 ->
0.991 -> 0.992 -> 0.994 -> 1.0 -> 1.0 (rest)` - monotonically increasing from where the close left
off, never dropping to `0.96` first. PASS.

### M2-05 - AlertDialog

SLA Policies > a policy detail page > "Delete" (an AlertDialog, not the deferred-action countdown
pattern - this branch's CLAUDE.md notes the countdown pattern replaces confirmation dialogs going
forward, but this one is a pre-existing AlertDialog still in the codebase, matching the brief's
"any remaining destructive AlertDialog"). 15-frame poll of both
`[data-slot="alert-dialog-overlay"]` and `[data-slot="alert-dialog-content"]` from the same
trigger instant shows numerically identical opacity at every single frame:

```
t=26   overlay=0        content=0
t=59   overlay=0.206     content=0.206
t=126  overlay=0.595     content=0.595
t=210  overlay=0.859     content=0.859
(next batch, both already settled)
t=1    overlay=1         content=1
```

`panel.className` (`fixed left-[50%] top-[50%] z-50 grid max-h-[90dvh] w-full max-w-lg gap-4
overflow-y-auto border bg-background p-6 shadow-lg shadow-black/5 sm:rounded-lg`) has no
`animate-in`; `overlay.className` is `fixed inset-0 z-50 bg-black/50 backdrop-blur-md
[@media(prefers-reduced-transparency:reduce)]:backdrop-blur-none [@media(prefers-reduced-
transparency:reduce)]:bg-black/72` - `OVERLAY_CLASS_STATIC`. Screenshot
`M2-05-alertdialog.png`.

### M2-06 - ContextMenu / HoverCard / Menubar

ContextMenu: Resources > Files, grid view, synthetic `contextmenu` MouseEvent on a file card
(same targeting approach as the M1 evidence - the card two levels up from the filename text
node). `[data-slot="context-menu-content"]` wrapper is static `class="z-50"`; its first child
`<div>` animates opacity `0`/scale `0.96` at t=51ms to `>= 0.99` by t=286-305ms. Screenshot
`M2-06-contextmenu.png`.

HoverCard: Master Data Management > Products > Specifications > Spec Verification, a coverage
count cell (`SpecVerificationList.tsx`'s `CoverageCell`, a controlled `HoverCard` with
`openDelay={120}`). Dispatched a full `pointerover/pointerenter/mouseover/mouseenter` sequence on
the trigger button; content first appeared at t=145ms (~120ms delay plus dispatch overhead),
`[data-slot="hover-card-content"]` class `"z-50 outline-hidden"` (no `animate-in`), settling to
`>= 0.99` opacity by t=398ms. Screenshot `M2-06-hovercard.png`.

Menubar: `grep -rl "MenubarContent" app` returns only `app/components/layouts/demo2/components/
navbar-menu.tsx`, `demo3/components/navbar-menu.tsx` and `app/components/partials/navbar/
navbar-menu.tsx` - none of which render under the active `demo1` layout this tenant uses (same
finding as M1's evidence for `MenubarItem`). No page in this tenant renders a Menubar to test
against; the `[vitest]` half of M2-06 already covers the component in isolation per the brief.

### M2-07 - Tooltip

`components/ClientProviders.tsx:28`: `<TooltipProvider delayDuration={700}
skipDelayDuration={300}>` wraps the whole app tree once; `components/ui/tooltip.tsx`'s `Tooltip`
export renders no `TooltipPrimitive.Provider` of its own.

Live trigger: the sidebar "Add to Quick Access" / "In Quick Access" pin (`Star` icon,
`app/components/layouts/demo1/components/menu-item-pin-button.tsx`), present on every menu
heading and toolbar-shaped in the same way a list-toolbar icon button is. Dispatched
`pointerover/pointerenter/pointermove` + `mouseover/mouseenter/mousemove` with
`pointerType: 'mouse'` (a bare `pointerenter`/`mouseenter` pair was not enough to trigger Radix's
tooltip - needed the full sequence including `pointermove`/`mousemove`):

- First pin: `[data-slot="tooltip-content"]` first appeared at t=725ms (`delayDuration={700}`
  plus dispatch overhead), `data-state` on the trigger's wrapper read `delayed-open` in the
  interim.
- Moved to an adjacent pin (well under the 300ms `skipDelayDuration` window): its tooltip
  appeared at t=21ms - "immediately" per spec.
- The second tooltip's `getComputedStyle(el).transform` was `"none"` at every one of 20 sampled
  frames while opacity changed - opacity-only, no scale/translate.

`console` across the entire run (every page visited) contains zero occurrences of "must be used
within TooltipProvider" - the only non-debug/non-Fast-Refresh lines were 30 repeats of a
pre-existing `Warning: Missing \`Description\` or \`aria-describedby={undefined}\` for
{DialogContent}` React dev warning, unrelated to this branch (many dialogs across the app lack an
explicit `DialogDescription`, a longstanding a11y nit, not introduced here). `errors` (uncaught
page errors) was empty throughout.

## Screenshots in this directory

- `M2-01-command-palette.png` - command palette open via Ctrl+Shift+K, fully opaque, no scale.
- `M2-04-normal-dialog-open.png` - Create Category modal open, for the "compare against a normal
  Dialog" contrast.
- `M2-04-searchable-select-popover-open.png` - Products > Filters > "All categories" SearchableSelect
  popover open (the instance with the instant-close defect documented above).
- `M2-05-alertdialog.png` - SLA Policy delete AlertDialog, scrim and panel both fully opaque.
- `M2-06-contextmenu.png` - right-click ContextMenu open on a file card, Resources > Files (grid).
- `M2-06-hovercard.png` - Spec Verification coverage-count HoverCard open.

## Cleanup

Dev server killed: `kill 68047` (parent `npm run dev`); its children `next dev` (68072),
`next-server` (68090) and the Turbopack `postcss.js` helper (68718) exited with it - confirmed via
a follow-up `lsof -i :3081` returning empty. Only the `m2tester` agent-browser session belonging
to this run was closed (`close`, not `close --all`). `.env.local` left in place per the brief. No
database writes were made - every check was a read/hover/open-close interaction; no create,
update, delete or import action was submitted.
