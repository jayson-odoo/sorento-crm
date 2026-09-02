# M3 GPU and preferences - browser verification evidence (agent-browser, 2 Sep 2026)

Worktree `motion2-M3` (branch `feat/motion2-M3-gpu-preferences`, HEAD `632abb869`), FE dev server
`PORT=3081 npm run dev` (`npm run dev` PID 50800, `next dev` PID 50825), BE reused read-only on
`:8120` per `FASTAPI_INTERNAL_URL=http://localhost:8120` in `.env.local` (copied from the
`motion2-M2` worktree's shape, confirmed `NEXTAUTH_URL=http://localhost:3081`,
`AUTH_TRUST_HOST=true`, no `NEXT_PUBLIC_API_URL`). `lsof -i :3081` was empty before starting.
Login via `E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`. Session `--session m3tester` (isolated
browser). Viewport 1280x800 default, 375x812 for the mobile drawer check. Navigated by sidebar
clicks from `/`, plus the global footer "Support" link (a real UI element, not a deep URL) to
reach a ticket detail page.

**Method beyond the standard command set.** Three checks needed capability `agent-browser`
0.27.0 does not expose as a CLI command, so a small Node script (Node 22, native `WebSocket`)
attached directly to the daemon's Chrome via `agent-browser get cdp-url` and
`Target.attachToTarget` (flatten session), then issued raw CDP: `Emulation.setEmulatedMedia` for
coarse-pointer (M3-05), `Performance.getMetrics` + `Tracing.start/end` for the M3-06 trace, and a
`setPointerCapture` no-op patch for the M3-07 drag (below). This is layered ON TOP of the same
running session `agent-browser` already had open - not a second browser - confirmed by matching
`target.url` against `localhost:3081` before attaching.

**Tool quirks hit this run, all confirmed test-harness artifacts, not product defects:**

- `click @ref` silently no-ops on sidebar group toggles, DropdownMenu/ContextMenu items and the
  Products row "..." trigger - the same finding as M1/M2/M4 evidence. Worked around with a native
  `element.click()` or a full `pointerdown/mousedown/pointerup/mouseup/click` sequence dispatched
  via `eval --stdin`.
- Those synthetic `PointerEvent`s lack a real OS-tracked pointer, so any handler calling
  `setPointerCapture` on them throws `NotFoundError: ... No active pointer with the given id is
  found` (4 such console errors, from the Products list "product actions" trigger and the AI
  assistant resize handle). Confirmed synthetic-dispatch noise, not a regression: real user input
  always has an active pointer. Worked around for the M3-07 resize by monkey-patching
  `HTMLElement.prototype.setPointerCapture`/`releasePointerCapture` to a no-op for the duration of
  one `eval` call, which only skips the (irrelevant, in a real browser always-succeeding) capture
  call and lets the app's own `pointermove`/`pointerup` listeners attach normally.
- `agent-browser set media` (dark/light/reduced-motion) and every subsequent `agent-browser eval`
  call apparently reissue `Emulation.setEmulatedMedia` with the CLI's own tracked feature list,
  which REPLACES rather than merges CDP's override set - a directly-set custom feature (coarse
  pointer/no-hover, M3-05) gets silently wiped out the next time an unrelated `agent-browser`
  command runs. Worked around by doing the emulate-then-measure sequence for M3-05 entirely
  inside one Node/CDP script with no intervening `agent-browser` CLI call.
- Bare `pointer`/`hover` CDP media feature overrides had no effect (`window.matchMedia` still
  read `false`) until `Emulation.setTouchEmulationEnabled({enabled:true, maxTouchPoints:1})` and
  `Emulation.setEmitTouchEventsForMouse({enabled:true, configuration:'mobile'})` were also set -
  Chromium ties the pointer/hover primary-axis media features to touch/mobile emulation state,
  not to the bare feature override alone.
- Rapid, repeated toggling of the sidebar collapse button across several back-to-back script runs
  (chasing the above) triggered what looks like an unrelated preference-persistence race (the
  visible width kept climbing back toward the desktop default independent of any `:hover` match).
  A single clean run - fresh reload, one toggle, a settle wait, then measure - reproduced cleanly
  and is what is reported below. Flagged here so it is not mistaken for an M3-05 finding.

## Findings summary (pass/fail table)

| Check | Target | Result | Measured value |
| --- | --- | --- | --- |
| M3-01 | ResizeObserver on the fill during the window | PASS (trivially) | 1 callback across a ~2.1s sample window on the toast-surface delete - but see the FAIL below for why this is a hollow pass |
| M3-01 | **Fill `transform: scaleX()` actually drains over the window** | **FAIL** | `bar.style.transitionDuration` read `""` (empty) and `bar.style.transform` stayed `"scaleX(1)"` for the ENTIRE window on BOTH surfaces tested (toast: Products list row delete; inline: Product Categories record page delete) - up to 4.5s sampled on one run. The bar visually never moves; only the `role="timer"` label ticks (`Deleting in 10s` -> `9s` -> `8s`, confirmed on both). Root-caused in source, see below. |
| M3-01 | Label decrements once per second | PASS | `10s -> 9s -> 8s` observed at the expected ~1s boundaries on both surfaces |
| M3-01 | Cancel before the window lapses | PASS | Cancelled at ~3s on every arm; `[data-testid="deferred-countdown"]` gone within 400ms of the click; the acted-on row (`VLDWT5879-GM` product, then a product category) confirmed intact after a hard page reload each time |
| M3-01 | `motion-reduce:transition-none` under reduced motion | PASS (but moot) | Computed `transitionDuration: "0s"` under `prefers-reduced-motion: reduce` - correct per spec, but indistinguishable from the FAIL above since the bar never transitions either way in this dev session. Label still counted (`10s -> 9s`) |
| M3-03 | Activities panel does not resize the record body | PASS | Ticket detail page (`/ticket-management/tickets/<id>`, reached via the global "Support" footer link): `<main>` width `1000px` and `getComputedStyle(main).marginRight` `"0px"` identically before and after opening the panel; `document.documentElement.scrollWidth === clientWidth === 1280` in both states (no horizontal scrollbar); the `<aside>` panel (`x:860-1280, w:420`) genuinely overlaps `<main>` (`x:280-1280`) - confirmed via a bounding-box overlap test |
| M3-03 | A DataGrid specifically, in this page's body | NOT EXERCISED | Neither `ticket-management/tickets/[id]` nor `project-sales/[projectId]` (the two live users of `EntityActivitiesLayout`) renders a `DataGrid`/`<table>` in its own body in this codebase (`grep DataGrid` on both is empty) - the UAC's own two named examples don't carry one. Verified the substantive claim (no reflow, no scrollbar, overlay not push) against the page's actual content instead |
| M3-04 | Sidebar collapse instant under reduced motion | PASS | `getComputedStyle(sidebar).transitionDuration: "0s"`, `transitionProperty: "none"`; sampled every rAF across the click, width jumped `280 -> 80` between two consecutive frames with no intermediate value |
| M3-04 | **Mobile nav drawer travels, not instant** | **FAIL** | At 375px, `[data-vaul-drawer]` computed `transitionDuration: "0.15s"` (150ms) under reduced motion, not the intended `1ms`, and visibly slid (`translateX` sampled `-281px -> -194 -> -78 -> -34 -> -17 -> -9 -> -4 -> -1.6` over ~150ms). Root cause: CSS specificity, see below |
| M3-04 | **Activities panel not covered by the reduced-motion block at all** | **FAIL** | `<aside>`'s own computed `transitionDuration: "0.2s"` (200ms) under `prefers-reduced-motion: reduce` - unchanged from normal motion. Its class is `transition-transform duration-200 ease-out`, which matches none of the four things `css/styles.css`'s reduced-motion block actually targets (`.demo1 .sidebar/.wrapper/.header`, `[data-vaul-drawer]`, `[class*="transition-["]`, or the `[data-slot$="-content"]` group - the `<aside>` carries no `data-slot` at all) |
| M3-04 | Countdown bar steps under reduced motion | PASS (but moot, same caveat as M3-01) | `transitionDuration: "0s"` correctly computed; cannot be visually distinguished from "always frozen" given the M3-01 bug |
| M3-05 | Coarse pointer + no-hover tap does not expand a collapsed sidebar | PASS | 1280px, `Emulation.setEmulatedMedia` (`pointer: coarse`, `hover: none`) plus touch/mobile emulation enabled, confirmed via `window.matchMedia` (`hoverNone: true`, `pointerCoarse: true`); collapsed sidebar held at exactly `80px` across 10 samples over 372ms after a `pointerover`/`pointerenter` (`pointerType: 'touch'`) dispatch on the sidebar |
| M3-06 | DevTools trace of a sidebar collapse + expand, Orders list, 50 rows | RECORDED, dropped frames observed | See detail below - trace saved, numbers below |
| M3-07 | No message re-render per pointer move during resize | PASS | 4-message conversation loaded (`Show conversation history` > "the hanlim one"); message bubble DOM node references (`document.querySelectorAll('[class*="rounded"][class*="max-w"]')`) were **the exact same array of references, by `===`,** before the drag started and after `pointerup` - zero remount/re-render of the transcript across a 20-step, ~320ms drag |
| M3-07 | Panel width tracks the pointer per move | PASS | `panel.style.width` climbed monotonically `384px -> 387 -> 390 -> ... -> 444px` across the drag, in lockstep with the dispatched `pointermove` steps |
| M3-07 | Panel keeps its size on release | PASS | `444px x 640px` held after `pointerup`, matching the last in-drag sample |
| M3-07 | Handle fades over `--duration-fast` while panel springs in | PASS | On open: handle opacity `1 -> 0.887 -> 0.719 -> ... -> 0.003` over ~150ms (matches `transition={{duration:0.15}}`) while the panel's own opacity (`0 -> 0.85`) and scale (`matrix` diagonal `0.92 -> 0.985`) climbed simultaneously - a genuine spring, not a linear fade, confirming both halves of the M3-07 design in one sample |
| Console | Zero real `[error]`-level entries | PASS (with caveats above) | Only pre-existing `Warning: Missing \`Description\`...` React dev warnings (unrelated) and the 4 synthetic-dispatch `NotFoundError`s from this run's own tool workarounds (see quirks above) |

## Detail notes

### M3-01 - the fill never drains (dev-mode finding, root cause identified)

Confirmed on BOTH surfaces `useDeferredAction` supports:

- **toast** (Products list row "..." > Delete product, `VLDWT5879-GM`)
- **inline** (Product Categories record page > gear > Delete category)

In both cases, `document.querySelector('[data-testid="deferred-countdown-bar"]').style` never
gained a `transitionDuration`/`transitionProperty`/target `transform` - it sat at the initial
`scaleX(1)` with an empty `transitionDuration` for as long as sampled (up to 4.5s on one run),
while the separate `role="timer"` label correctly ticked down every second. This is a real,
reproducible failure of the visible countdown fill under this repo's actual `npm run dev`
configuration - a user watching a real delete in this dev environment sees a still-full red bar
next to a ticking "Deleting in 3s" label.

**Root cause, from source.** `hooks/useDrainingScaleXFill.ts`'s arm effect:

```ts
useEffect(() => {
  if (targetMs <= 0 || armedTargetRef.current === targetMs) return;
  armedTargetRef.current = targetMs;
  setStyle({ transform: `scaleX(${startFraction})` });
  const remaining = Math.max(0, targetMs - Date.now());
  let raf2 = 0;
  const raf1 = requestAnimationFrame(() => {
    raf2 = requestAnimationFrame(() => {
      setStyle({ transform: 'scaleX(0)', transitionProperty: 'transform', ... });
    });
  });
  return () => {
    cancelAnimationFrame(raf1);
    if (raf2) cancelAnimationFrame(raf2);
  };
}, [targetMs]);
```

`next.config.mjs` has `reactStrictMode: true`, and `npm run dev` is development mode, so React
18/19 double-invokes every effect on mount: mount -> cleanup -> mount again, synchronously, before
the browser ever paints a frame. On the FIRST pass, `armedTargetRef.current` is set to `targetMs`
and `raf1` is scheduled. StrictMode's synthetic cleanup runs immediately after and calls
`cancelAnimationFrame(raf1)` - cancelling it before either requested frame ever fires. The SECOND
pass then sees `armedTargetRef.current === targetMs` (set during the first pass, never reset by
the cleanup) and returns immediately, doing nothing. Net effect: the double-rAF that is supposed
to flip the style to the draining transform never completes, permanently, for that pending
action's whole life - exactly the frozen-at-`scaleX(1)` behaviour measured on both surfaces.

**This was NOT verified against a production build** (`next build && next start`) per this repo's
standing "never build for iteration" rule - only `npm run dev` was exercised, which is also this
repo's own documented default browser-verification environment. Whether this specific StrictMode
interaction also reproduces without `reactStrictMode` is not established here, but the mechanism
itself (an effect that MUST survive an uncancelled two-frame async gap to do anything) is fragile
under React's own documented dev-mode contract regardless, and StrictMode is explicitly `true` in
this repo's `next.config.mjs`, not a special/opt-in test-only setting - so this is a real, everyday
result on this codebase's own default dev loop, not an exotic edge case. Recorded as a FAIL to
report, not something a reviewer should have to be told is "probably a test artifact."

No database write resulted from either arm: `pending-actions/current` for the product entity
confirmed `"pending": null` after the toast case's window (it also carried a stale, unrelated
`last_outcome` from 30 Aug reflecting a real FK-constraint failure - `purchase_order_lines`
references that product - so a genuine commit attempt on this specific row would fail server-side
regardless), and a hard page reload after every Cancel confirmed the acted-on row/record still
present.

### M3-03 - Activities panel overlay

`app/(protected)/ticket-management/tickets/[id]/page.tsx`, ticket `TCK-2026-000981`, reached via
the global footer "Support" link (present on every page, `app/components/layouts/demo1/components/
footer.tsx`) rather than a deep URL. At 1280x800:

```
before open: main width=1000, marginRight="0px", doc scrollWidth=1280=clientWidth
after open:  main width=1000, marginRight="0px", doc scrollWidth=1280=clientWidth
aside rect: {x:860, width:420, right:1280}; main rect: {x:280, right:1280} -> overlap: true
```

Screenshot `M3-03-activities-overlay.png`. Neither page that uses `EntityActivitiesLayout`
(`ticket-management/tickets/[id]`, `project-sales/[projectId]`) renders an actual `DataGrid`
component in its own body (`grep -rn DataGrid` on both files returns nothing) - the UAC's two
named examples don't literally carry one in this codebase today. Verified the layout claim
(no width change, no margin transition, no scrollbar, genuine overlay) against the page's real
content instead, which is what the claim is actually about.

### M3-04 - two real gaps in the reduced-motion coverage

**Sidebar (PASS).** `.demo1 .sidebar` computed `transition: none !important` under
`prefers-reduced-motion: reduce`; collapsing it landed at `80px` between two consecutive
`requestAnimationFrame` samples with no width in between.

**Mobile drawer (FAIL).** At 375px, the `[data-vaul-drawer]` element's `data-slot` attribute is
`"drawer-content"` - it ends in `-content`, and is NOT excluded by either `:not()` in
`[data-slot$="-content"]:not([data-slot="dialog-content"]):not([data-slot="sheet-content"])`
(the M2-era rule that resets Tailwind's `animate-in`/`animate-out` timing to zero for menu/dialog
surfaces). That selector has specificity `(0,3,0)` (one base attribute selector + two `:not()`
attribute arguments) and sets `transition-duration: 0.15s !important`. The intended
`[data-vaul-drawer], [class*="transition-["] { transition-duration: 1ms !important; }` rule has
specificity `(0,1,0)`. Both are `!important`, both are author-origin, so CSS's own tie-break rule
(higher specificity wins regardless of source order) picks the `0.15s` rule. Confirmed by reading
the full concatenated `@media (prefers-reduced-motion: reduce)` block's `cssText` and by sampling
the drawer's `transform` live: it visibly slides `-281px -> -194 -> -78 -> -34 -> -17 -> -9 ->
-4 -> -1.6` over ~150ms rather than snapping. 150ms reads far better than the un-fixed 500ms
default, but it is not what M3-04 asks for ("appears without travel").

**Activities panel (FAIL).** `EntityActivitiesLayout.tsx`'s `<aside>` uses
`"transition-transform duration-200 ease-out"` - a NAMED Tailwind duration utility, not an
arbitrary-value `transition-[...]` class, so `[class*="transition-["]` does not match it, and it
carries no `data-slot` at all, so none of the other three reduced-motion selectors reach it
either. Its computed `transitionDuration` was `0.2s` identically with and without
`prefers-reduced-motion: reduce` emulated - the panel is simply not covered, despite the UAC text
naming "the activities panel appears in place" as one of this check's four claims.

Screenshot `M3-04-reduced-motion-375.png` (drawer open, post-settle - the timing claim is carried
by the sampled transform sequence above, not the still image).

### M3-05 - coarse pointer gate (clean pass, after a tooling detour)

`css/demos/demo1.css`'s `@media (hover: hover) and (pointer: fine) { .demo1.sidebar-collapse
.sidebar:hover { width: var(--sidebar-default-width); } }` is confirmed the ONLY occurrence of
this selector anywhere in the loaded stylesheets (`grep`-equivalent scan of every `CSSStyleSheet`
in `document.styleSheets`) - no duplicate, ungated copy exists elsewhere.

Clean, single-pass measurement (fresh `Page.reload`, confirm collapsed, THEN apply emulation,
THEN measure - see the tool-quirks note above for why the first several attempts gave a false
"still expands" reading purely from repeated toggling of the collapse button across script runs):

```
after fresh reload:      isCollapsed=true, width=80
media check:              hoverNone=true, pointerCoarse=true (via matchMedia)
right before dispatch:    isCollapsed=true, width=80
10 samples over 372ms
  after pointerover+pointerenter (pointerType:'touch'):  width=80 at every single sample
```

Screenshot `M3-05-coarse-pointer-collapsed.png`.

### M3-06 - sidebar collapse/expand trace, Orders list (50 rows)

`/order-management/orders` at 1280x800, confirmed 50 rows in `<tbody>`. `Performance.enable` +
`Performance.getMetrics` bracketing one full collapse-then-expand cycle (300ms CSS transition each
direction, 400ms settle wait either side), plus a per-`requestAnimationFrame` gap sampler running
across the whole window, plus a `Tracing.start`/`Tracing.end` capture
(`devtools.timeline,disabled-by-default-devtools.timeline,blink.user_timing`) saved to
`M3-06-sidebar-collapse-trace.json` (6636 trace events, 1.3MB).

```
LayoutCount delta (collapse + expand):      34
RecalcStyleCount delta (collapse + expand): 34
frame gaps sampled: 54 (covering both transitions + settle waits)
  frames over 16.7ms (missed 60fps):  19
  frames over 33ms (a genuinely dropped frame): 2  (60.1ms, 59.6ms - roughly one per direction)
```

**Verdict: dropped frames observed - YES.** Two distinct frame-time gaps over 33ms (worse than
30fps) were measured, one attributable to each direction of the toggle, on a page whose body holds
a 50-row DataGrid. This matches the in-code rationale already left at the fix site
(`css/demos/demo1.css`, commit `368b8ea0c`): this collapse still animates `width` (plus
`.wrapper`'s `padding-inline-start` and `.header`'s `inset-inline-start`) rather than `transform`,
because a prior transform-only rewrite attempt (S8-03) was tried and reverted for distorting both
end states. Per that comment and the UAC's own instruction, since dropped frames ARE present here,
**a follow-up ticket for the transform rewrite is the outcome this evidence supports, not making
the transition instant** - the PR should file and link it rather than treat this trace as a
clean bill of health.

Screenshot `M3-06-orders-list-50rows.png`; raw trace `M3-06-sidebar-collapse-trace.json` (loadable
via `chrome://tracing` or `npx agent-browser trace` tooling, or `JSON.parse` for the flat
`traceEvents` array this script wrote).

### M3-07 - AI assistant resize (clean pass, after a tooling detour)

CDP-synthesized `pointerdown` on the resize handle throws inside the app's own
`handle.setPointerCapture(e.pointerId)` (`NotFoundError`, no OS-tracked pointer for a
JS-dispatched event) BEFORE the function reaches its `addEventListener('pointermove'/'pointerup',
...)` calls, so no naive dispatch could ever move the panel. Worked around by temporarily patching
`HTMLElement.prototype.setPointerCapture`/`releasePointerCapture` to a no-op for the one `eval`
call that drives the drag (a real user's browser always succeeds at this call, so this only
removes an inert side effect, not a step the app depends on for its resize logic).

Conversation "the hanlim one" loaded via Show conversation history (4 message bubbles). Captured
`document.querySelectorAll('[class*="rounded"][class*="max-w"]')` as an array of DOM node
references BEFORE dispatching `pointerdown`, then a 20-step `pointermove` sequence (~16ms apart,
moving up-left, matching the `axis: 'corner'` drag direction) sampling `panel.style.width/height`
each step, then `pointerup`, then re-queried the same selector and compared by `===`:

```
widthSamples: 384px -> 387 -> 390 -> ... -> 444px (20 steps, monotonic, matches pointer travel)
heightSamples: 600px -> 602 -> ... -> 640px (same shape)
after pointerup: width/height held at 444px/640px
msgNodeCountBefore: 4, msgNodeCountAfter: 4
sameNodesReferenceEqual: true   <- the exact same 4 DOM Element objects, not just equal content
```

Zero remount of the transcript across the whole drag - strictly stronger evidence than a "no
visible re-render" read, since a `key`-driven remount that happened to reuse identical markup
would still fail a strict reference-equality check.

**Handle fade / panel spring on open**, sampled every rAF from the moment the (now-closed) handle
was clicked:

```
t=28ms   handle=1.000  panel exists, opacity=0,      scale=0.920
t=101ms  handle=0.300  panel opacity=0.389,           scale=0.944
t=168ms  handle=0.003  panel opacity=0.714,           scale=0.973
t=186ms  handle mid-unmount (opacity read flips to 1 for one frame, then gone at t=203ms)
```

Handle opacity falls smoothly `1 -> ~0` over ~150ms (matches the file's `transition={{duration:
0.15}}`), while the panel's own opacity and `transform` scale climb simultaneously and
independently (a spring, not a linear fade) - both halves of the M3-07 design confirmed in one
sample. Screenshot `M3-07-ai-assistant-resized.png` (panel at its dragged-to size, 444x640).

## Screenshots in this directory

- `M3-01-deferred-countdown.png` - Product Categories record page, "Delete category" armed
  (countdown visible, bar full - see the FAIL note above for why the bar never actually drains).
- `M3-03-activities-overlay.png` - ticket detail page with the Activities & notes panel open,
  overlapping the content column without resizing it.
- `M3-04-reduced-motion-375.png` - mobile nav drawer open at 375px under emulated
  `prefers-reduced-motion: reduce` (post-settle; the travel/timing claim is in the sampled
  transform sequence above, not this still image).
- `M3-05-coarse-pointer-collapsed.png` - collapsed sidebar (80px) under coarse-pointer/no-hover
  CDP emulation after a touch-style hover dispatch, still collapsed.
- `M3-06-orders-list-50rows.png` - Orders list at 1280px with 50 rows, the page the trace below
  was recorded against.
- `M3-06-sidebar-collapse-trace.json` - raw Chrome DevTools trace of one collapse + one expand
  cycle on that page (6636 events).
- `M3-07-ai-assistant-resized.png` - AI assistant panel after the drag, resized to 444x640 with
  the 4-message "the hanlim one" transcript still showing.

## Cleanup

Dev server killed: `kill 50800` (parent `npm run dev`); its child `next dev` (50825) exited with
it - confirmed via a follow-up `lsof -i :3081` returning empty. Only the `m3tester` agent-browser
session belonging to this run was closed (`close`, not `close --all`). The direct-CDP Node scripts
used for M3-05/M3-06/M3-07 attached to and detached from the SAME session's target - they never
opened a second browser. `.env.local` left in place per the brief. No destructive database writes:
every deferred-delete countdown armed for M3-01 (twice: a product, then a product category) was
Cancelled well inside its window and confirmed intact via a hard page reload; no create, archive,
or commit-through action was allowed to complete.
