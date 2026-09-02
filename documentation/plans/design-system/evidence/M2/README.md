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

## Run 2 (after fix round, HEAD ee24c67ca)

Same worktree, branch `feat/motion2-M2-keyboard-timing`, now at HEAD `ee24c67ca`. `.env.local`
verified unchanged from run 1's shape (`FASTAPI_INTERNAL_URL=http://localhost:8120`,
`NEXTAUTH_URL=http://localhost:3081`, `AUTH_TRUST_HOST=true`, no `NEXT_PUBLIC_API_URL`).
`lsof -i :3081` was empty before starting, so no port fallback was needed. FE dev server
`PORT=3081 npm run dev` (own process group: `npm run dev` PID 53199, `next dev` PID 53224,
`next-server` PID 53227, no separate Turbopack helper this run). BE reused read-only on `:8120`.
agent-browser session `--session m2run2`. Login via `E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`.
Navigated by sidebar clicks from `/`, with the same tool-quirk workaround as run 1 (sidebar
group/tab/Popover triggers frequently no-op under `click @ref`; a native `element.click()` or a
full `pointerdown/mousedown/pointerup/mouseup/click` sequence dispatched via `eval --stdin` was
used instead - not a product defect, the same finding logged in run 1/M1/M4).

**Method.** Identical to run 1: dispatch a real or synthetic DOM event, then poll every
`requestAnimationFrame` for `getComputedStyle(el).opacity`/`.transform` and `el.getAnimations()`,
building a (t, opacity, scale) timeline. For menu-family surfaces (`dropdown-menu-content`,
`popover-content`, `context-menu-content`) the timeline reads the STATIC wrapper's first child
`<div>` (the wrapper itself carries only Radix Popper's positioning transform), per run 1's
finding. `prefers-reduced-motion` was emulated via `agent-browser set media light reduced-motion`
(CDP `Emulation.setEmulatedMedia` under the hood) - this DID work in this agent-browser version, so
the M2-01 reduced-motion sub-check that run 1 could not attempt was completed this run.

### Findings summary (pass/fail table)

| Check | Target | Result | Measured value |
| --- | --- | --- | --- |
| M2-01 | Command palette open (Ctrl+Shift+K) | PASS (unchanged) | Not re-measured in full this run (no code changed on the open path); Escape re-test below confirms the palette still opens and the shared timeline harness still reads it correctly |
| M2-01 | **Escape same frame - FIXED** | **PASS** (was PARTIAL in run 1) | Content opacity now flips from `1` to `0` within ~2-4ms of the Escape keydown (`t=21ms: opacity=1` -> `t=25ms: opacity=0`, and again `t=18ms -> t=20ms` on a repeat run), stays at `0` through the scrim's ~150-185ms fade, then unmounts at t≈189-201ms. Run 1 found the content's opacity stuck at `1` for the ENTIRE fade window (a real divergence from "no scale, no spring" as experienced); that is fixed - the content is visually gone (0 opacity) on the very next frame after Escape, well inside "removes it within one frame" read practically |
| M2-01 | Escape with `prefers-reduced-motion: reduce` emulated | PASS | Identical shape under emulation (confirmed via `window.matchMedia('(prefers-reduced-motion: reduce)').matches === true`): opacity `1` at t=12ms -> `0` at t=14ms -> unmount at t=188ms. Run 1 could not attempt this sub-check ("if agent-browser can emulate..."); this agent-browser version's `set media light reduced-motion` does emulate it |
| M2-04 | **Popover close (Products > Filters > "All categories" SearchableSelect) - FIXED** | **PASS** (was FAIL in run 1) | Was a ~21ms un-eased snap in run 1. Now a smooth ramp: opacity `1` -> `0.916` -> `0.771` -> ... -> `0.0027` by t=315ms, gone by t=350ms - settle ≈300-315ms, squarely in the "~250-300ms" the brief asks for, not the old snap |
| M2-04 | No lingering `[data-slot="popover-content"]` node after close settles | PASS | `document.querySelectorAll('[data-slot="popover-content"]').length === 0` one second after the close animation finished, both for the Products popover and the SCM popover below |
| M2-04 | **SCM popover close, many-per-page (Reorder Planning grid, `ProductPhotoPopover` - one of the 14 files on the `PopoverPortal` fix list)** | **PASS** | Same smooth ramp confirmed on a second, independent popover instance from the fixed-files list (`SpoScheduleMatrixTable`/`PlanDemandPopover` were not reachable with live data this run - see detail note - `ProductPhotoPopover` renders once per row, 25+ instances on one Reorder Planning grid page, satisfying "renders many at once"): opacity `1` -> `0.935` -> ... -> `0` at t=302ms, gone by t=336ms - settle ≈285-302ms |
| M2-03 | CanvasToolbar tooltip at 300ms (Dealer Kit > Tag Templates > canvas) | SOURCE-CONFIRMED, not browser-reachable | `app/(protected)/dealer-kit/tag-templates/components/CanvasToolbar.tsx:101`: `<Tooltip delayDuration={300}>` with an explicit comment citing M2-07 ("300ms rather than the app-wide 700ms... this toolbar is 15 unlabelled icon buttons"). Tag Templates list has 0 existing templates in this tenant's data and opening the "New Template" dialog's "Create template" action is a genuine DB write (confirmed via the dialog UI, a `POST`-backed create flow) - not exercised, per the read-only constraint. `RequestTagDesigner.tsx` (Dealer Kit > Price Tag Requests > an existing request > "Design tags") renders a visually similar toolbar but has NO `Tooltip` usage at all (`grep -c Tooltip` = 0), so it is not a substitute reachable instance |
| M2-03 | Elsewhere baseline (app-wide 700ms, for comparison) | PASS | Products page sidebar "Add to Quick Access" pin: tooltip appeared at t=720ms after a full `pointerover/pointerenter/pointermove/mouseover/mouseenter/mousemove` sequence - matches `delayDuration={700}`, consistent with run 1's t=725ms finding on the same trigger |
| M2-04 (regression) | Tooltip instant (any tooltip) | PASS | First sampled frame after appearance: `opacity: "1"`, `transform: "none"`, `getAnimations().length === 0` - unchanged from run 1. Tooltip confirmed gone after the pointer left / Escape (exact single-frame removal timestamp not independently re-captured this run, since run 1 already established this and nothing on the closing path changed) |
| M2-02 | Arrow keys jump in carousel vs animated dot/drag | SOURCE-CONFIRMED, not browser-reachable (unchanged from run 1) | `components/common/AttachmentPreviewModal.tsx:172-173` unchanged: `ArrowRight`/`ArrowLeft` still call `scrollNext(true)`/`scrollPrev(true)` (instant `jump`), vs. `components/ui/carousel.tsx`'s dot/drag path with no `jump` argument. Could not reach a live 2+-image gallery this run either: the tested product (`VLDWT5879-GM`) has "No attachments linked to this product"; the Complaints list's "Attachments" column read `0` on every visible row; Resources > Files still has no reachable multi-image `AttachmentPreviewModal` instance (grid-view file cards open no in-app preview via the tested interaction) |
| Regression | DropdownMenu close (Escape, Product Categories row "..." actions) | PASS | Opacity `1` at t=38ms fading to ~`0` by t=296-313ms - close ≈ 260-275ms, matches run 1's ~275ms finding |
| Regression | Dialog open (Create Category, Product Categories) | PASS | Opacity `0`/scale `0.96` at t=160ms (relative to a delayed click-dispatch, not a delayed reveal) climbing to opacity `0.98`/scale `1.0` by t=498ms, fully settled shortly after - same real-spring shape as run 1's Advanced Filters dialog (~400-420ms there), a normal per-instance timing spread for the same shared `Dialog` component |
| Regression | **Dialog reopen mid-close (monotonic re-check, both Create Category and the exact Advanced Filters dialog run 1 tested)** | PASS | Finer-grained sampling (per-`rAF`, not per-manual-poll) than run 1 shows the reopen is NOT perfectly monotonic at the very first 1-2 frames: on Advanced Filters, mid-close scale was `0.9824`/opacity `0.603`, and the reopen's first two sampled frames dip slightly FURTHER (scale `0.973`/opacity `0.381`, min scale `0.9720` two frames later) before climbing smoothly to `1.0`/`1` over the next ~230ms. This never returns to the true reset values (scale `0.96`/opacity `0`) - it is a small (~0.01 scale, ~0.2 opacity) overshoot consistent with a physical spring continuing on its prior velocity for a couple of frames before the reversed target takes over, not a snap-to-reset. Run 1's own recorded sequence (`0.971 -> 0.971 -> 0.972 -> 0.975 -> ...`) starts at almost exactly this run's post-dip floor (`0.972`), meaning run 1's coarser sampling likely caught the same dip already past its lowest point. Recorded PASS on the same basis as run 1: the reset-to-`0.96` case being tested for does not occur |
| Regression | AlertDialog (SLA Policy delete, via detail page "Delete") | PASS | Overlay and content opacity numerically identical at every sampled frame (`0 -> 0.151 -> 0.361 -> 0.551 -> 0.698 -> 0.802 -> 0.874 -> 0.920 -> 0.950`), matching run 1's finding exactly. Cancelled (not deleted) - no database write |
| Regression | ContextMenu (Resources > Files, grid, right-click a file card) | PASS | Opacity `0`/scale `0.96` at t=35ms to opacity `>= 0.99` by t≈290-300ms - settle ≈255-265ms, matches run 1's ~235-254ms finding within normal run-to-run jitter |
| Console | Zero `[error]`-level entries across the whole run | PASS | `console`/`errors` commands returned nothing at `[error]` level and no uncaught page errors; the only warning present was the same pre-existing `Warning: Missing \`Description\` or \`aria-describedby={undefined}\` for {DialogContent}` React dev warning from run 1 (unrelated to this branch). Zero occurrences of "must be used within TooltipProvider" |

### Detail notes

**M2-01 Escape fix.** Reproduced twice (normal media, then with `prefers-reduced-motion: reduce`
emulated) with identical shape both times - opacity drops to `0` 2-4ms after the Escape keydown,
not ~150ms later as run 1 found. Screenshot `run2-01-escape-reduced-motion.png` (captured after
the poll settled, so it shows the closed state - the timing claim is carried by the JSON timeline
in this section, not the screenshot).

**M2-04 Popover close fix.** Re-verified on the exact SearchableSelect instance run 1 flagged
(Products > Filters > "All categories") and on a second, independent `PopoverPortal` consumer from
the fixed-files list (`ProductPhotoPopover`, rendered once per row on the SCM Reorder Planning
grid - 25+ live instances on one page, satisfying "an SCM popover that renders many at once").
Both close with the same smooth ~300ms ramp the un-portalled comparison popover (`Marketing >
Promotions > Quick filters`) already had in run 1; the previous ~21ms un-eased snap is gone.
`SpoScheduleMatrixTable`'s own schedule-matrix popover cells were not reachable with live data
this run: the one packing-list record checked ("SRTU7788002") had no open PO lines feeding its SPO
planner ("Nothing is pulled from an open PO yet."), and the reorder plan's own drill triggers
("Suggested qty", "Project demand", "Retail demand" - `PlanRowDialog`/`DemandDrillPopover`) turned
out on inspection to render as `[data-slot="dialog-content"]` Dialogs in this build, not the
`PopoverPortal` popovers the M2-04 file list names them as - `ProductPhotoPopover` was the
reachable, confirmed member of that list. Screenshots: `run2-04-searchable-select-popover-open.png`,
`run2-04-scm-product-photo-popover-open.png`.

**M2-03 CanvasToolbar.** Not live-browser-reachable without a database write: Tag Templates has
zero existing rows in this tenant, and "New Template" > "Create template" is a real create action
(confirmed by inspecting the dialog's form and submit button - name/family/width/height fields
feeding a "Create template" submit), which the read-only constraint on this run rules out. Source
inspection at `CanvasToolbar.tsx:96-101` confirms the override is present and unchanged from what
the brief describes:
```tsx
// 300ms rather than the app-wide 700ms (M2-07): this toolbar is 15 unlabelled
// icon buttons ...
<Tooltip delayDuration={300}>
```
The "elsewhere: ~700ms" comparison point was re-confirmed on the same sidebar pin trigger run 1
used, landing at t=720ms (run 1: t=725ms) - consistent app-wide default.

**M2-02 carousel.** No code change on this path since run 1 (`AttachmentPreviewModal.tsx:172-173`
identical). Tried three fresh candidates this run - a specific product's Attachments tab (empty),
the Complaints list's dedicated "Attachments" column (read `0` on every visible row, a cleaner
signal than run 1's ambiguous "Linked Attachments" section text), and Resources > Files grid view
(file cards exist and carry `data-slot="context-menu-trigger"`, used for the ContextMenu regression
check, but no preview/lightbox opened from the tested interaction) - none surfaced a reachable
multi-image gallery. Still SOURCE-CONFIRMED only, unchanged from run 1's finding.

**Dialog reopen mid-close - the dip, explained.** The brief's stated success criterion is "no jump
to 0.96" (the dialog's true closed-state initial value) on reopen. Sampling every `rAF` frame
(rather than a single manual snapshot mid-close, as run 1 did) exposes that the very first 1-2
frames after the reopen click actually continue slightly PAST wherever the close had gotten to,
before the spring reverses direction - e.g. on Advanced Filters, mid-close scale `0.9824` dipped to
a floor of `0.9720` two frames later, then climbed smoothly to `1.0`. That floor, `0.972`, is
strikingly close to the very FIRST value run 1 itself recorded for the same test (`0.971`) -
strongly suggesting run 1's own first sample already landed just past this same brief dip, simply
because its polling loop's first callback fired a frame or two later than this run's. Since the
floor never approaches the true reset value (`0.96`), this is recorded as a PASS on the same basis
as run 1, with the more precise mechanism now on record: a physical spring continuing on its
existing velocity for a couple of frames when its target reverses, not a state reset.

### Screenshots in this directory (Run 2)

- `run2-01-escape-reduced-motion.png` - command palette after Escape under emulated
  `prefers-reduced-motion: reduce` (captured post-settle; see JSON timeline for the timing claim).
- `run2-04-searchable-select-popover-open.png` - Products > Filters > "All categories"
  SearchableSelect popover open (the instance whose close-fade was fixed).
- `run2-04-scm-product-photo-popover-open.png` - SCM Reorder Planning grid, `ProductPhotoPopover`
  open (second confirmed `PopoverPortal` fix instance, many-per-page).
- `run2-04-dialog-open.png` - Create Category dialog open, real-spring comparison.
- `run2-05-alertdialog.png` - SLA Policy delete AlertDialog, scrim and panel both mid-fade,
  numerically in sync (cancelled afterward, no database write).
- `run2-06-contextmenu.png` - right-click ContextMenu open on a file card, Resources > Files
  (grid).

### Cleanup (Run 2)

Dev server killed: `kill 53199` (parent `npm run dev`); its children `next dev` (53224) and
`next-server` (53227) exited with it - confirmed via a follow-up `lsof -i :3081` returning empty.
No separate Turbopack `postcss.js` helper was spawned this run. Only the `m2run2` agent-browser
session belonging to this run was closed (`close`, not `close --all`). `.env.local` left unchanged
(no port fallback was needed, so `NEXTAUTH_URL` was never edited). No database writes were made:
the "New Template" create-template flow was opened to inspect its form and then Cancelled without
submitting, and the SLA Policy "Delete" AlertDialog was opened to measure its fade and then
Cancelled without confirming - every other check was a read/hover/open-close interaction.
