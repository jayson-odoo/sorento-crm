# UAC - UI and Motion Round 2

Contract for `PLAN-ui-motion-round2.md`. Where the two disagree, this file wins.
Every criterion names how it is verified: `[vitest]`, `[pytest]`, `[browser]` (agent-browser,
sidebar navigation from `/`, evidence under `documentation/plans/design-system/evidence/M<n>/`),
or `[review]` (a reviewer reads the diff). `[UX]` marks a criterion that came from the
`find-animation-opportunities` gate or the user's rulings.

Baseline measured on `origin/main` e1adad4d2, 2 Sep 2026.

## M4 List latency

- **M4-01** `[vitest]` A shared `LIST_QUERY_OPTIONS` exists in `lib/list-query/` and every list
  hook whose `queryKey` carries page, size, sort, filter or search state spreads it. An
  inventory test enumerates the hooks and fails on any miss. Baseline: 3 of 63 with
  `placeholderData`; shipped: 126 spread sites across 101 files. This walk reads
  `queryKey` text, so it is the hook-side FLOOR, not the whole rule - a hook keyed on a
  bare `filters` or `query` identifier names nothing it can see, and widening it to those
  two words would flag every report and detail query that keys on the same nouns. M4-01b's
  third walk is the ceiling that covers them. Two allowlisted exceptions, each with its
  reason in the test: `hooks/useListPager.ts` re-runs the LIST query in the background from
  a DETAIL page, purely to find the current record's neighbours, and renders no rows - with
  `keepPreviousData` it would answer from the previous page's items while a new page
  loads, so prev/next would step through neighbours the reader is not on; and
  `system-management/mcp-tools/hooks/useMcpAdmin.ts` reads an unpaginated 500-row catalogue
  whose only key change is an Active-only toggle, so keeping the previous answer would show
  inactive rows to a reader who just asked for active ones, which reads as a broken toggle.
- **M4-01b** `[vitest]` Every `<DataGrid>` that pages on the server forwards
  `isPlaceholderData` from its list query. Two inventory walks, because there are two ways
  to reach a grid: one walks hook to consumer to tag by imports, and one starts from the
  honest population - every non-test file under `app/` and `components/` that sets
  `manualPagination: true`, which is the code declaring that the server owns the page. The
  second is the grid-side CEILING and is what a new list has to get past; the import walk
  structurally cannot see a grid fed by props from its parent (`LeadsGrid`, `ProjectsGrid`)
  or one whose `useQuery` is inline. Shipped: 106 of the 190 `<DataGrid>` tags forward it,
  being 94 of the 97 server-paged files plus 12 client-paged grids fed by a spreading hook.
  Three allowlisted, with reasons in the test: `PriceTagRequestsList` (fetches in a
  `useEffect`, not react-query, so no query reports a placeholder window), `SpecTable` and
  `SpecProposalReview` (`manualPagination` with `pageCount: 1` is how they turn client
  paging OFF on prop-fed rows). A list fetched outside react-query is out of M4's scope:
  moving it onto a query is its own piece of work, not a flag to forward. This is what
  M4-02 depends on: TanStack reports the placeholder window as `isLoading: false,
  isFetching: true, isPlaceholderData: true`, so a grid that does not receive the flag
  never dims, whatever the hook spreads.
- **M4-02** `[browser]` On Products, Orders and Stock at 1280: pressing Next, changing sort,
  changing a filter and typing a search word each keep the current rows on screen (dimmed) until
  the new page arrives. No skeleton rows appear once a first page has loaded.
- **M4-03** `[vitest] [browser]` While a placeholder page is showing, the pagination strip stays
  rendered and interactive: Rows-per-page can be changed and Next can be pressed a second time;
  the second press wins. Baseline: both replaced by skeleton bars.
- **M4-04** `[vitest]` `QueryClient` sets `defaultOptions.queries = { retry: 1, staleTime:
  30_000, refetchOnWindowFocus: false }`; no hook under `app/**` or `hooks/**` sets
  `refetchOnWindowFocus: false` itself (grep-backed test). `useProducts` and `useOrders` no
  longer set `staleTime: Infinity`.
- **M4-05** `[review] [browser]` No list toolbar filter and no list primary action carries
  `disabled={isLoading}`. Typing in the Products search box never disables the Brand and
  Category selects or the Create button. Baseline: 8 files.
- **M4-06** `[vitest] [browser]` Hovering a clickable `DataGrid` row calls `router.prefetch`
  once for that href; the Network panel shows the detail chunk request on hover, and the click
  that follows renders the detail page without a route-chunk request. The detail pager
  prefetches its prev and next hrefs on mount. The sidebar prefetches on pointer-enter, not on
  viewport.
  **Evidence note:** `router.prefetch` is a no-op in `next dev`, so the Network panel shows
  no prefetch request on the dev server whatever the code does. The browser evidence for
  this AC is therefore the code path plus `hooks/usePrefetchOnce.test.ts` (once per href,
  and the `(hover: none)` branch both ways); the network half is a production spot-check,
  deferred to the deploy.
- **M4-07** `[browser]` The SCM reorder grid (a list whose column set changes with its filter)
  shows no mismatched header for longer than one placeholder frame and no console error during
  a filter swap.

## M1 Motion perimeter hygiene

- **M1-01** `[vitest]` `PRESSED_CLASS` contains `duration-(--duration-fast)` and
  `ease-(--ease-standard)`. The `@theme` block in `css/config.reui.css` defines
  `--default-transition-timing-function: var(--ease-standard)` and
  `--default-transition-duration: var(--duration-fast)`.
- **M1-02** `[vitest]` Zero `transition-all` and zero bare `transition ` (the multi-property
  shorthand) in `app/**`, `components/**` and `css/**` outside test files. Baseline: 12.
- **M1-03** `[vitest]` Zero literal `duration-<N>` and zero `ease-in`/`ease-in-out` on an
  entering element in `app/**` and `components/**`, outside an allowlist that starts with only
  the two accepted alternating pulses in `css/styles.css` and the OTP caret period. Baseline: 10.
- **M1-04** `[vitest]` `css/design-tokens.test.ts` globs include `app/**` and
  `components/common/**`, and it asserts M1-02 and M1-03.
- **M1-05** `[vitest] [browser]` `DropdownMenuItem`, `ContextMenuItem`, `MenubarItem`,
  `CommandItem` carry `PRESSED_CLASS`; the sidebar menu items use `PRESSED_CLASS` and no longer
  carry `duration-75` or `active:scale-[0.98]`; a clickable `DataGrid` row darkens on
  pointer-down (`active:bg-muted/60`).
- **M1-06** `[vitest]` The 16 named unused motion components are deleted; `npm run build` is
  green; no file imports them.
- **M1-07** `[review]` `navigation-menu.tsx` viewport uses `origin-top`; `screen-loader.tsx`
  has no transition classes; `EntityActivitiesLayout.tsx` launcher has no `animate-pulse` and
  no raw `bg-red-600`; `drawer.tsx` overlay is `OVERLAY_CLASS_STATIC`;
  `AIAssistantBubble.tsx:450` has no `hover:w-9`.
- **M1-08** `[vitest]` A test enumerates every file under `app/(protected)` that renders a raw
  `<button` and fails unless the file imports `Button` or the element carries `PRESSED_CLASS`.
  The test is allowed to be red at the end of M1 with the count recorded (127 baseline); M7-01
  turns it green.

## M2 Keyboard and timing

- **M2-01** `[vitest] [browser]` Cmd/Ctrl+Shift+K opens the command palette with no scale and
  no spring: the panel is fully opaque on the first painted frame after the keydown (DevTools
  Animations panel shows no running animation on the content node). Escape closes it the same way.
- **M2-02** `[browser]` In the attachment lightbox, ArrowRight and ArrowLeft change the slide on
  the same frame; drag and dot navigation still animate.
- **M2-03** `[vitest]` `lib/motion.ts` exports `MENU_SPRING` (visualDuration 0.2) and
  `SURFACE_SPRING_EXIT` (0.2); `surfaceTransition(reduced, 'menu')` returns `MENU_SPRING`;
  `surfaceExitTransition(reduced)` returns `SURFACE_SPRING_EXIT`; both return
  `REDUCED_MOTION_TRANSITION` under reduced motion.
- **M2-04** `[browser]` Frame-by-frame at 4x: DropdownMenu and Popover open in ~200ms and
  close in ~200ms; Dialog and Sheet open in ~300ms and close in ~200ms. Reopening a dialog
  mid-close continues from its current scale (no jump to 0.96).
- **M2-05** `[vitest] [browser]` AlertDialog renders through `AnimatePresence` with the
  lightbox spring and `OVERLAY_CLASS_STATIC`; at 4x the scrim and the panel reach full opacity
  on the same frame.
- **M2-06** `[vitest]` `DropdownMenuSubContent`, `ContextMenuContent`, `ContextMenuSubContent`,
  `HoverCardContent` and `MenubarContent` contain no `animate-in`/`animate-out` classes and
  render a `motion.div` on the menu spring.
- **M2-07** `[vitest] [browser]` Exactly one `TooltipProvider` is mounted (in
  `ClientProviders.tsx`) with `delayDuration={700}` and `skipDelayDuration={300}`; `Tooltip`
  renders no provider of its own. Hovering a toolbar: the first tooltip appears after ~700ms,
  the next sibling within 300ms appears immediately, content fades only (no `zoom-in-95`).
- **M2-08** `[review]` `DESIGN-LANGUAGE.md` section 3 records the menu preset and the exit
  preset as shipped and removes the "follow-up work" note.

## M3 GPU and preferences

- **M3-01** `[vitest] [browser]` The deferred-action countdown fill animates `transform:
  scaleX()` from `origin-left` with one `linear` transition whose duration equals the remaining
  window, set once when the action parks; the tick interval is 1000ms and only updates the
  timer label. A `ResizeObserver` on the fill reports 0 size changes during the window
  (baseline: one per 100ms tick). `motion-reduce:transition-none` is kept and the label still
  counts down.
- **M3-02** `[review]` `TakeoverCountdown.tsx` and `CashBudgetPanel.tsx` bars animate
  `transform` only, on the tokens, with `motion-reduce:transition-none`.
- **M3-03** `[browser]` Opening the Activities panel on a record page does not change the
  width of the record content (no `margin` transition; the panel overlays). The grid on that
  page reports 0 layouts during the open.
- **M3-04** `[vitest] [browser]` The `prefers-reduced-motion` block in `css/styles.css` covers
  `.demo1 .sidebar`, `.demo1 .wrapper`, `.demo1 .header`, `[data-vaul-drawer]` and
  `[class*='transition-[']`. With the OS preference on: sidebar collapse is instant, the mobile
  nav drawer appears without travel, the activities panel appears in place, the countdown bar
  steps per second without tweening.
- **M3-05** `[vitest] [browser]` The sidebar hover-expand rule sits inside
  `@media (hover: hover) and (pointer: fine)`; on a coarse-pointer emulation a tap on the
  collapsed sidebar does not expand it.
- **M3-06** `[browser]` A DevTools performance trace of a sidebar collapse on the Orders list
  (50 rows) is recorded under `evidence/M3/`. If it shows dropped frames, a follow-up ticket is
  filed for the transform rewrite and linked in the PR; if not, the transition is made instant
  and the trace justifies it. Either outcome is stated in the PR.
- **M3-07** `[browser]` Resizing the AI assistant panel with a long transcript loaded does not
  re-render the message list per pointer move (React DevTools highlight shows no message
  re-render until pointer-up); the handle fades out over `--duration-fast` while the panel
  springs in.

## M5 Loading, error and list shells

- **M5-01** `[vitest]` Every route segment under `app/(protected)` whose directory renders a
  `<DataGrid` has a `loading.tsx`; the inventory test holds the count (baseline 10 of 123).
- **M5-02** `[vitest]` Zero non-demo files render the string `Loading...` or `Loading…`
  (baseline 50).
- **M5-03** `[vitest] [browser]` `ListPageSkeleton` rows are 60px tall and the crumb bar is
  above the title; loading Products then landing shows no vertical shift of the title or the
  first row (measured with `getBoundingClientRect` before and after in the evidence run).
- **M5-04** `[browser]` `app/(protected)/error.tsx` exists; a forced render throw on a detail
  page shows a Reset button with the sidebar and header still present; Reset recovers without a
  full reload. `not-found.tsx` renders for an unknown record id inside the shell.
- **M5-05** `[UX] [vitest] [browser]` **Sticky header, absolute rule.** `DataGrid` defaults
  `headerSticky` to true with a bounded scroller; on Products, Orders and Stock at 1280 and 375
  the column header stays visible when scrolled to row 40. `columnsResizable` and
  `columnsMovable` default true; a column can be dragged to a new position and resized on
  Products without any per-list prop.
- **M5-06** `[UX] [vitest]` No product file imports `@/components/ui/table` (baseline 24). Any
  file that cannot migrate sits on an allowlist in the test with a one-line reason, and the PR
  lists them.
- **M5-07** `[UX] [vitest] [browser]` **Back to list restores the row, absolute rule.** A row
  click appends `from=<row id>` to the detail href; Back, the post-delete push and Edit all
  carry it; on list mount the row with that id is scrolled into view (`block: 'center'`) and
  highlighted until the next pointer event. Browser: open row 38 on Products page 2, press Back,
  row 38 is centred and highlighted; the same after stepping prev/next three times on the
  detail pager.
- **M5-08** `[review]` `DESIGN-LANGUAGE.md` sections 4 and 7 and
  `documentation/reference/PR-CHECKLIST.md` state both rules; a new list without them is a
  checklist failure.

## M6 Composer, mobile, toasts, focus

- **M6-01** `[vitest] [browser]` Sending a message in the conversation composer never disables
  the textarea; the caret and focus ring are present throughout and after the send; a second
  Enter during the send is ignored (re-entry guard); the sent text appears immediately as a
  dimmed optimistic bubble and is replaced by the server row on refetch; on failure the bubble
  is removed and the error toast shows.
- **M6-02** `[review] [browser]` The notifications sheet, the AI assistant panel and the
  conversations inbox size with `dvh`; at 375 in a mobile-Safari-emulated viewport their bottom
  edge is visible.
- **M6-03** `[vitest]` The default `Input` size renders at 16px under `pointer-coarse`; the
  app declares no `maximum-scale`.
- **M6-04** `[vitest] [browser]` One `<Toaster position="top-center">` is mounted; query
  errors and mutation errors both appear top-center. `lib/toast.ts` gives success 4000ms and
  error `Infinity` with a close button; no file outside `lib/toast.ts` and
  `components/ui/sonner.tsx` imports from `sonner` directly.
- **M6-05** `[browser]` Tabbing to a dialog's close X shows the global focus ring.
- **M6-06** `[review]` The four portal search boxes use `useDebouncedSearch` and
  `ListSearchInput`; no hand-rolled `setTimeout(..., 300)` remains in `app/(auth)/portal`.
- **M6-07** `[browser]` A conversation thread with three images auto-scrolls to the bottom and
  stays there while the images load (each image is inside a fixed-aspect box).
- **M6-08** `[review]` `documentation/adr/` records the `ssr: false` provider decision.

## M7 Motion additions

- **M7-01** `[UX] [vitest]` The press-class inventory test from M1-08 is green: every raw
  `<button` under `app/(protected)` carries `PRESSED_CLASS` or is a `Button`.
- **M7-02** `[UX] [vitest] [browser]` A pending row-level delete dims the row over
  `--duration-fast` on `--ease-standard` (the `<tr>` carries `transition-opacity`); under
  reduced motion the dim is instant but present.
- **M7-03** `[UX] [browser]` In My Downloads and Upload Activity, when a job reaches Ready the
  Preview/Download cluster fades and scales in from the row's right edge on the surface spring;
  under reduced motion it fades only.
- **M7-04** `[UX] [browser]` The notification and upload-activity badges scale from 0.6 to 1
  on the menu spring when they appear AND when their count changes; under reduced motion they
  fade only.
- **M7-05** `[UX] [browser]` Advancing or going back in the lead wizard slides the incoming
  step 12px in the direction of travel with a fade, incoming only, no exit animation; under
  reduced motion it fades only. The PR states whether the height jump between steps reads as
  acceptable at 4x and with fresh eyes, and files a follow-up if not.
- **M7-06** `[vitest]` Each addition has a unit test asserting its reduced-motion branch
  (opacity-only variants) via a mocked `useReducedMotion`.
- **M7-07** `[review]` None of the ten rejected candidates in the plan's section 6 gained
  motion in this slice.
