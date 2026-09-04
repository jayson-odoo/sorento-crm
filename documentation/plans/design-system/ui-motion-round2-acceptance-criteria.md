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
  shorthand) in `app/**`, `components/**` and `css/**` outside test files. Baseline: 12
  `transition-all`, and 19 bare `transition` (measured 2 Sep once the guard scanned class
  string literals instead of lines; every one of the 19 is in `app/**`).
- **M1-03** `[vitest]` Zero literal `duration-<N>` and zero `ease-in`/`ease-in-out` on an
  entering element in `app/**` and `components/**`, outside an allowlist that starts with only
  the two accepted alternating pulses in `css/styles.css` and the OTP caret period. Baseline: 10.
- **M1-04** `[vitest]` `css/design-tokens.test.ts` globs include `app/**` and
  `components/common/**`, and it asserts M1-02 and M1-03.
- **M1-05** `[vitest] [browser]` `DropdownMenuItem` carries `PRESSED_CLASS`; `ContextMenuItem`,
  `MenubarItem` and `CommandItem` carry `PRESSED_TRANSFORM_CLASS` instead - the shrink with no
  colour transition, because their highlight is moved by the arrow keys and motion on a
  keyboard-initiated action is a hard-fail. The sidebar menu items use `PRESSED_CLASS` and no
  longer carry `duration-75` or `active:scale-[0.98]`. A `DataGrid` row darkens on pointer-down
  (`active:bg-muted/60`) only where the row is clickable (`rowHref` or `onRowClick`) and the
  grid is not stripped; the loading skeleton row does not.
- **M1-06** `[vitest]` The 16 named unused motion components are deleted; `npm run build` is
  green; no file imports them.
- **M1-07** `[review]` `navigation-menu.tsx` viewport uses `origin-top`; `screen-loader.tsx`
  has no transition classes; `EntityActivitiesLayout.tsx` launcher has no `animate-pulse` and
  no raw `bg-red-600`; `drawer.tsx` overlay is `OVERLAY_CLASS_STATIC`;
  `AIAssistantBubble.tsx:450` has no `hover:w-9`.
- **M1-08** `[vitest]` A test enumerates every raw `<button` under `app/(protected)` and fails
  unless that element's own opening tag carries `PRESSED_CLASS`. The check is PER TAG and a
  file's `Button` import is ignored: a `<Button>` element never reaches the `<button` matcher,
  so importing the primitive says nothing about the hand-rolled buttons beside it. The test is
  allowed to be red at the end of M1 with the count recorded (baseline: 182 tags across 128
  files, measured 2 Sep); M7-01 turns it green.

## M2 Keyboard and timing

- **M2-01** `[vitest] [browser]` Cmd/Ctrl+Shift+K opens the command palette with no scale and
  no spring: the panel is fully opaque on the first painted frame after the keydown (DevTools
  Animations panel shows no running animation on the content node). Escape closes it the same way.
  **Escape clause (fix round).** The panel and the scrim share one `AnimatePresence`, and
  AnimatePresence holds a fragment mounted until every exiting child is done - so the scrim's
  own 150ms fade governs when the DOM node goes, not the panel. The first pass left the
  no-motion panel's `exit` equal to its `animate` (opacity 1), so it sat fully opaque over the
  fading scrim for ~150-185ms and then popped (measured, `evidence/M2/README.md`). Fixed by
  giving the no-motion content a real `exit: { opacity: 0 }` on a `{ duration: 0 }` transition:
  the panel is gone on the closing frame, the scrim keeps its fade, and under
  `prefers-reduced-motion` that scrim uses `REDUCED_MOTION_TRANSITION` instead of the 150ms
  tween. What this AC asserts is therefore the panel's own opacity on the closing frame, not
  the node's removal latency: the node may outlive it by the scrim's fade, by design.
- **M2-02** `[browser]` In the attachment lightbox, ArrowRight and ArrowLeft change the slide on
  the same frame; drag and dot navigation still animate.
  **Fix round.** The shared `Carousel` had its own `onKeyDownCapture` still calling the animated
  `scrollNext()`/`scrollPrev()`, so the rule held only where `AttachmentPreviewModal`'s handler
  ran; it now passes Embla's `jump` argument too, so arrow keys in ANY carousel jump. The modal
  keeps its own handler, and the two no longer collide: the carousel's is a capture listener on
  the carousel region, so with focus INSIDE that region the capture handler wins and stops
  propagation, and the modal's handler never runs; with focus anywhere else in the dialog the
  capture listener never sees the key and the modal's handler is what moves the slide. Stopping
  propagation is the round-3 fix - the capture handler called `preventDefault` only, so both
  fired and one press advanced two slides, which is the normal case because
  `CarouselPrevious`/`CarouselNext` render inside the region and a click on either leaves focus
  there.
- **M2-03** `[vitest]` `lib/motion.ts` exports `MENU_SPRING` (visualDuration 0.2) and
  `SURFACE_SPRING_EXIT` (0.2); `surfaceTransition(reduced, 'menu')` returns `MENU_SPRING`;
  `surfaceExitTransition(reduced)` returns `SURFACE_SPRING_EXIT`; both return
  `REDUCED_MOTION_TRANSITION` under reduced motion.
- **M2-04** `[browser]` Frame-by-frame at 4x: DropdownMenu and Popover open in ~200ms and
  close in ~200ms; Dialog and Sheet open in ~300ms and close in ~200ms. Reopening a dialog
  mid-close continues from its current scale (no jump to 0.96).
  **Settle time is not visualDuration.** `visualDuration` is the contract, and a critically
  damped spring keeps creeping after it: the settle time a frame-by-frame run measures (first
  frame at opacity >= 0.99) reads ~50 to 100ms longer. The tester measured menus at ~230-275ms
  against a 200ms preset and dialogs at ~375-420ms against 300ms, all of which PASS. Read a
  measured value against the preset plus that tail, not against the preset alone.
  **Portalled popovers (fix round).** `PopoverPortal` wrapped `PopoverContent` in Radix's own
  Portal, which drops its subtree the moment `open` flips false and took the exit spring with
  it - every `SearchableSelect`/`SearchableMultiSelect` dropdown and the 14 SCM/project-sales
  popovers closed in ~21ms with no fade (measured; the same pair unportalled faded over
  ~300ms). `PopoverPortal` now only sets a context and `PopoverContent` renders
  `Portal forceMount` from inside its own `AnimatePresence`, the shape `DropdownMenuContent`
  already used. Verify on a `SearchableSelect`, not only on a bare `Popover`.
- **M2-05** `[vitest] [browser]` AlertDialog renders through `AnimatePresence` with the
  lightbox spring and `OVERLAY_CLASS_STATIC`; at 4x the scrim and the panel reach full opacity
  on the same frame.
- **M2-06** `[vitest]` `DropdownMenuSubContent`, `ContextMenuContent`, `ContextMenuSubContent`,
  `HoverCardContent` and `MenubarContent` contain no `animate-in`/`animate-out` classes and
  render a `motion.div` on the menu spring.
- **M2-07** `[vitest] [browser]` Exactly one `TooltipProvider` is mounted (in
  `ClientProviders.tsx`) with `delayDuration={700}` and `skipDelayDuration={300}`; `Tooltip`
  renders no provider of its own. Hovering a toolbar: the first tooltip appears after ~700ms,
  the next sibling within 300ms appears immediately, and the content is **instant in and out** -
  no scale, and no fade either.
  **Fix-round note (M2 round 2).** The shipped `opacity-0 transition-opacity ->
  data-[state=delayed-open]:opacity-100` pairing was dead in both directions and has been
  removed rather than repaired: Radix mounts the content already carrying
  `delayed-open`/`instant-open` (its `stateAttribute` is only `closed` while the content is
  unmounted), so the entry fade has no starting value to travel from, and Radix's Presence
  waits on `animationend` only, so a transition-only style unmounts on the closing frame
  before an exit fade can run. Hover sits in the frequency table's "none or `--duration-fast`
  opacity only" band, so none is a legitimate answer. A per-instance `delayDuration` on a
  `Tooltip` Root is allowed where the icons carry no labels: `CanvasToolbar` (15 icons) sets
  300ms, which Radix honours without a second provider.
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
  **Outcome (fix round): dropped frames, so the FIRST branch.** One collapse + expand cycle on
  Orders at 1280x800 with 50 rows traced 34 layouts and 34 style recalcs; 19 of 54 sampled
  frames ran over 16.7ms and 2 over 33ms (60.1ms and 59.6ms, about one per direction). Raw
  trace `evidence/M3/M3-06-sidebar-collapse-trace.json` (6636 events), method in
  `evidence/M3/README.md`. Follow-up ticket **#559** ("Sidebar collapse: transform-only
  rewrite") is filed and linked in the PR; the transition is NOT made instant, and the decision
  is recorded at the site in `css/demos/demo1.css`. A transform-only rewrite is not retried in
  this slice: S8-03 tried it and reverted it for distorting both end states, so it needs its own
  piece of work rather than a hurried second attempt.
- **M3-07** `[browser]` Resizing the AI assistant panel with a long transcript loaded does not
  re-render the message list per pointer move (React DevTools highlight shows no message
  re-render until pointer-up); the handle fades out over `--duration-fast` while the panel
  springs in.

## M5 Loading, error and list shells

- **M5-01** `[vitest]` Every route segment under `app/(protected)` whose directory renders a
  `<DataGrid` has a `loading.tsx`; the inventory test holds the count (baseline 10 of 123).
  **Shipped (M5 run 2):** `app/(protected)/loading-inventory.test.tsx` rewritten from S7-04's
  hard-coded ten-file list to a walk (same exclusions as `raw-table.inventory.test.ts`); proved
  red at 113 of 123 segments missing, green after adding the 113 (123 of 123 covered - the walk
  measured 123, not the plan's "roughly 123", so that is the number this test holds).
  **Review fix (M5 run 2 review B1/S1):** the run-2 predicate counted a segment's own files OR
  everything in its `components/` subdir, which false-positived on detail routes whose
  `components/` folder holds an unrelated grid used by a sibling tab (`scm/purchase-orders/[id]`,
  `project-sales/[projectId]`, `scm/sales-orders/[id]`, `scm/proforma-invoices/[id]`,
  `project-sales/[projectId]/sales-orders/[psoId]` - 5 `loading.tsx` files deleted) and, on four
  segments whose header comes from a parent `layout.tsx`, painted a second title/crumb bar under
  the real one. Fixed: for a `[dynamic]`-named leaf segment, only its own `page.tsx` (and same-
  directory imports) count - `components/` is never consulted for these. For every other
  segment, the walk now follows relative/`@/` imports from `page.tsx` (bounded to
  `app/(protected)`) instead of a single-hop directory scan, which found 12 real list routes the
  run-2 walk missed (`procurement-management/sponsorship-forms`,
  `workflow-forms-management/definitions`, `workflow-forms-management/submissions`,
  `workflow-forms-management/forms/[definitionId]/submissions`, `project-sales/pipeline`,
  `project-sales/reports`, `resource-management/trash`, `scm/market-signals`, plus 4 more the
  walk turned up beyond the plan's own list: `procurement-management/packing-lists/[id]/lines`,
  `procurement-management/packing-lists/[id]/spo`,
  `project-sales/[projectId]/sales-orders/[psoId]/revisions`,
  `user-management/contacts/[id]/access`). The predicate itself now measures 129 (not 123); a
  manually curated `BODY_ONLY_SEGMENTS` map in the test adds a `bodyOnly` variant on 8 segments
  (4 with a parent-layout header, 4 genuinely headerless) plus one exception the predicate does
  not find at all - `user-management/contacts/[id]` keeps a `loading.tsx` even though it has no
  `<DataGrid` of its own, the same "a record page under a list is held by the same shape"
  reasoning `ListPageSkeleton`'s own doc comment gives - for 130 required segments total. Five
  `dealer-kit` descendants (`design`, `design/summary`, `pages/[pageId]`, `bundles`,
  `price-tag-requests/[id]/design`) that inherited `dealer-kit/loading.tsx`'s list skeleton by
  Next.js's ancestor-fallback rule now carry their own `loading.tsx` rendering `SectionSkeleton`
  instead.
  **Evidence run 1, scope note (`project-sales/pipeline`):** the route's `loading.tsx` correctly
  imports and returns `ListPageSkeleton` per the predicate above, but the route DEFAULTS to a
  kanban/card view (a "grid card" vs "table" toggle, card view selected), so `ListPageSkeleton`'s
  row-bar shape is the wrong shape for what actually paints once the client component mounts -
  the evidence run's browser check caught a genuine card-shaped skeleton mid-load, not this
  file's `ListPageSkeleton`. Ruling: keep `ListPageSkeleton` here - the route has a real list
  view behind the toggle and the skeleton is content-shaped enough for either - rather than
  building a per-view skeleton for one route; noted, no code change.
  **Fixed (M5 run 3):** the DataGrid migration batch that landed on this branch (attachments,
  complaints, procurement, orders line tables on `DataGrid`) turned 10 more segments into list
  segments the walk now finds - `procurement-management/purchase-requests/new`,
  `procurement-management/purchase-requests/[id]/edit`,
  `procurement-management/sponsorship-forms/new`,
  `procurement-management/sponsorship-forms/[id]/edit` (all four get `SectionSkeleton rows={6}`:
  `PurchaseRequestForm` puts a line-items DataGrid inside a multi-field form, not a list page, and
  each page draws its own `PageHeader` directly, so neither `ListPageSkeleton` nor its `bodyOnly`
  variant fits), `system-management/app-store/bundles` and `system-management/email-event-configs`
  (default `ListPageSkeleton` - real lists with their own `PageHeader`), `system-management/health`
  (`SectionSkeleton rows={6}` - `HealthDashboard` is a stack of status cards, one of which holds a
  DataGrid; the grid is a section, not the whole page), `system-management/mcp-tools`
  (`ListPageSkeleton bodyOnly` - headerless, `McpToolsList` titles itself with a `CardTitle`, not a
  route header), `ticket-management/tickets` (default `ListPageSkeleton`), and
  `user-management/settings/notifications` (`ListPageSkeleton bodyOnly` - `user-management/
  settings/layout.tsx` already renders the `PageHeader` for every settings page, same reason
  `settings/portal-revisions` is `bodyOnly`). `BODY_ONLY_SEGMENTS` gained the latter two entries;
  the required-segment total moves from 130 to **139** (two of the ten were already counted by the
  walk before this run - being added to `BODY_ONLY_SEGMENTS` only changes their shape, not the
  count).
- **M5-02** `[vitest]` Zero non-demo files render the string `Loading...` or `Loading…`
  (baseline 50).
  **Shipped (M5 run 2):** `app/(protected)/loading-strings.inventory.test.ts`; proved red at 50,
  green after every occurrence became `ListPageSkeleton`/`ListPageSkeleton bodyOnly` (list
  shapes), the new `components/common/SectionSkeleton.tsx` (card/dialog/sidebar/widget bodies -
  the majority of the 50), an inline styled `span` where the real element is an `h2`/`p`
  (`DialogTitle`, `SheetDescription`, which may only hold phrasing content, not the `Skeleton`
  `div`), or a reworded label where the text stays a label (button/select/data-value "in
  flight" text, not a skeleton candidate per the brief's own carve-out).
- **M5-03** `[vitest] [browser]` `ListPageSkeleton` rows are 60px tall and the crumb bar is
  above the title; loading Products then landing shows no vertical shift of the title or the
  first row (measured with `getBoundingClientRect` before and after in the evidence run).
  **Corrected against the real file (M5 run 2):** `components/common/PageHeader.tsx` (only
  commit: #396) renders the `<h1>` title BEFORE the `<Breadcrumb>` trail in DOM order -
  `ToolbarHeading` is a plain `flex-col`, no reverse - so the crumb sits BELOW the title, not
  above it as this line and the plan's measured facts both assumed. `[vitest]` shipped:
  `components/common/ListPageSkeleton.test.tsx`, proved red (rows were `px-5`, no `h-[60px]`, no
  markers) then green: rows are `h-[60px] px-4` and the header row is `px-4`, matching
  `data-grid-table.tsx` exactly; the title bar renders before the crumb bar, matching the real
  order above. `[browser]` (Products load-then-land shift) still open for the tester.
- **M5-04** `[browser]` `app/(protected)/error.tsx` exists; a forced render throw on a detail
  page shows a Reset button with the sidebar and header still present; Reset recovers without a
  full reload. `not-found.tsx` renders for an unknown record id inside the shell.
  **Shipped (M5 run 2, `[vitest]` done, `[browser]` open):** `app/(protected)/error.tsx` and
  `not-found.tsx` (a `Card`, the message/copy, a Try again `Button` calling `reset()` on the
  error page, a `BackToList`-styled link to `/` on both); `app/(protected)/error.test.tsx` and
  `not-found.test.tsx` cover the content (message shown, Try again calls `reset`, link href).
  `grep -rn` for an existing `app/(protected)/**/error.tsx` or `not-found.tsx` found none before
  this - every detail page still falls through to these two. The `[browser]` half (shell
  survives a forced throw, Reset recovers, 404 renders inside the shell) is still open.
  **Review fix (M5 run 2 review B2/S3):** `error.tsx` rendered raw `error.message` - in
  production that is Next's own developer boilerplate (server-component throw), a generic
  client-throw string, or a rethrown API message that can carry a record id (a UUID-in-the-UI
  violation). Now fixed copy ("Something went wrong on this page.") plus a `Reference:
  <digest>` line when `error.digest` is present - the one token that correlates with the
  server log; `console.error(error)` unchanged. `error.test.tsx` asserts the fixed copy, the
  digest line, and that the raw message is never rendered. `not-found.tsx` is a scaffold, not
  yet adopted: zero protected pages call `notFound()` today (the only callers are the four
  portal routes under `app/(auth)/portal`); its own comment previously implied otherwise and
  is corrected. The adoption trigger is a detail page that today hand-rolls inline "X not
  found" copy calling `notFound()` instead - `user-management/contacts/[id]/layout.tsx` (its
  inline `<p>Contact not found</p>` branch) is the first candidate. No `notFound()` calls are
  added in this fix; that is separate follow-up work.
- **M5-05** `[UX] [vitest] [browser]` **Sticky header, absolute rule.** `DataGrid` defaults
  `headerSticky` to true with a bounded scroller; on Products, Orders and Stock at 1280 and 375
  the column header stays visible when scrolled to row 40. `columnsResizable` and
  `columnsMovable` default true; a column can be dragged to a new position and resized on
  Products without any per-list prop.
  **Shipped (M5 run 1, `[vitest]` done, `[browser]` open):**
  `components/ui/data-grid.defaults.test.tsx`; `DataGridScroller`'s default max-height comes
  from a new `--grid-max-h` token (`css/config.reui.css`), overridable per list with
  `tableLayout.scrollerMaxHeight`. The `[browser]` sweep (Products/Orders/Stock at 1280 and
  375, drag-to-reorder + resize on Products) is still open - the next browser-verification pass
  covers it.
  **Captain ruling (M5 run 2 review):** the column-header Move Left/Right menu
  (`headerControls` in `components/ui/data-grid-column-header.tsx`) is not rendered on main -
  dead since `63b93d74b` ("personalized columns"), confirmed by that file's own module doc
  comment (M5 review run 1, S4). Column reorder today is by drag (`columnsDraggable`, default
  true), so M5-05 holds through drag regardless. `columnsMovable: true` stays the default for
  whenever the menu is wired up - wiring `headerControls` into the render tree (a settings icon
  and dropdown on every column header across roughly 200 grids) is a separate design call, not
  part of M5.
  **Evidence run 1, pinned-column check scope note:** no in-app list has a pinned column by
  default and no sidebar/topbar/in-app link reaches one - the ONLY grid with
  `initialState.columnPinning` set is `project-sales/stock-debt/components/StockDebtClient.tsx`,
  and that route has no navigation entry anywhere in the app. The evidence run reached it by a
  one-off deep URL (explicitly allowed for exactly this kind of unreachable-otherwise case), not
  a sidebar walk. Verified there: a pinned header cell is `z-index:6` and a pinned body cell is
  `z-index:5`, so the header wins the stacking order through a scroll with no visual collision -
  M5-05 holds. Whether Stock Debt needs a nav entry is a separate captain's call, out of M5.
  **Evidence run 1, Finding 2 (review B2, `BoardCellBreakdownDialog.tsx`):** four
  simultaneously-scrollable `overflow-y:auto` regions were found nested inside the Fulfilment
  Planning board cell breakdown dialog: (1) `DialogBody` itself
  (`app/(protected)/project-sales/fulfilment-planning/components/BoardCellBreakdownDialog.tsx:947`),
  (2) `CellStockTable.tsx:375` (`max-h-[50vh]` table wrapper), (3) `StockDocumentsPanel.tsx:745`
  (`max-h-[35vh]` nested panel), (4) the Contributing lines tab's own `PanelDataGrid` scroller.
  Checked against main (`b9150f493`): (1), (2) and (3) all predate M5 unchanged - PRE-EXISTING,
  out of M5 scope, left as found. Only (4) is M5's: `scrollerMaxHeight={false}` (890ac2622,
  M5 review run 1 B2) opted the grid's own bounded scroller OUT so it does not nest a second
  scrollport inside `DialogBody`'s. This fix (evidence run 1 fix, commit 2) adds a test proving
  the prop actually reaches the rendered scroller (`data-slot="data-grid-scroller"` carries no
  `max-h-` class) - `BoardCellBreakdownDialog.test.tsx`, plus the same check on
  `scm/components/PlanRowDialog.tsx`'s `DrillTable` (via `ProjectRetailTabs`) and
  `scm/reorder/components/PlanRowDialogs.tsx`'s own file-local `DrillTable` (via
  `PlanRowDialog`'s `project`/`retail` kind), the two other families the brief named as unreached
  by the evidence run. All three pass: none of the three families' grid scrollers carries a
  bounding `max-h-` inside its own dialog body today.
- **M5-06** `[UX] [vitest]` No product file imports `@/components/ui/table` (baseline 24). Any
  file that cannot migrate sits on an allowlist in the test with a one-line reason, and the PR
  lists them.
  **Shipped (M5 run 1, guardrail only - no migration yet, that is run 3):**
  `components/ui/raw-table.inventory.test.ts`, proved red against an empty allowlist (27
  offenders - the plan's 26 plus `PurchaseRequestForm.tsx`, found by this scan). All 27 land on
  the allowlist as `pending migration, M5 run 3`; three are flagged for the captain's ruling on
  whether they can migrate at all (`app/(auth)/approval/page.tsx`,
  `app/(auth)/view/request/page.tsx`, `components/reports/ReportPivotTable.tsx`).
  **Shipped (M5 run 3, migration complete):** all 27 `pending migration` entries removed from
  the allowlist, one module per commit (SLA, system-management, tickets, user-management,
  products, complaints, attachments, procurement, then the three inline-editing files). Most
  moved to `PanelDataGrid` (`components/common/PanelDataGrid.tsx` - moved there from
  `project-sales/_shared/components` in the SLA commit, its first caller outside project-sales);
  a handful of standalone lists and one detail-page section already inside a `Card` use a plain
  `DataGrid` + `DataGridTable` instead, matching the existing convention at
  `master-data-management/units-of-measure`. The captain's ruling on the three flagged files
  landed as PERMANENT exemptions (not migrations): the two `app/(auth)` portal pages are outside
  the authenticated shell entirely, and `ReportPivotTable.tsx` reshapes rows into a matrix, which
  is not a DataGrid's one-row-per-record model - both reasons are recorded in the allowlist
  itself. The "inline editing may prove a real blocker" concern on `OrderLinesCard.tsx`,
  `PurchaseRequestDocumentEditCard.tsx` and `PurchaseRequestForm.tsx` did not materialise:
  `OrderLinesCard` turned out to be read-only (its add/import flows are modal dialogs, not
  inline cells), and the two react-hook-form `useFieldArray` line tables migrated to a plain
  `DataGrid` (`getCoreRowModel` only, no pagination row model, so no rows hidden behind a page 2
  on a form) with a dedicated focus-retention test proving typing into a cell, and appending a
  row, keep the same input identity a hand-rolled `<table>` keyed by `field.id` did. Final
  allowlist: the three permanent exemptions above, nothing else.
  **Review fix (M5 run 3 review, SF-5/SF-6):** the focus-retention claim above held for typing
  and for row-append in isolation, but not together: `fields.length` sat in BOTH line tables'
  columns `useMemo` deps (`PurchaseRequestForm.tsx`, `PurchaseRequestDocumentEditCard.tsx`), so
  an append or remove recreated every cell type and remounted every input - values survived
  (react-hook-form owns them), input IDENTITY did not. The delete button's
  `disabled={fields.length <= 1}` is the only place inside the memo that read `fields.length`;
  it now reads `table.getRowModel().rows.length` off the `CellContext` instead, and `fields.length`
  is out of both deps arrays. Corrected claim: typing into row 1, THEN appending a row, keeps row
  1's value AND its input node identity - proven by a new test in each `*.lineItems.test.tsx`
  (`PurchaseRequestForm.lineItems.test.tsx`, `PurchaseRequestDocumentEditCard.lineItems.test.tsx`,
  the latter's harness now also calling `form.watch('products')` so it re-renders on every
  keystroke the way the real parent, `PurchaseRequestForm`, does - without that the harness never
  re-rendered while typing and could not tell a memo keyed on `fields.length` apart from one that
  is not).
  **Ruling (M5 run 3 review, SF-8):** `PanelDataGrid`'s default `pageSize = 10` paginates detail
  sections that previously rendered every row. A line table ON A DOCUMENT (an order's own lines,
  a purchase request's own line items, a container's own source invoices) renders every row -
  `PanelDataGrid` gains a `paginate` prop (default `true`, unchanged for the other ~15 callers);
  `paginate={false}` sets `pageSize` to `Number.MAX_SAFE_INTEGER` and hides the pager. Applied to
  `OrderLinesCard.tsx`, `PurchaseRequestDetail.tsx` (`PurchaseRequestLineItemsGrid`) and
  `SourceProformaInvoicesCard.tsx`. `GRNDetail.tsx`'s picking lines and the two react-hook-form
  line tables above were already unaffected - all three render on a plain `DataGrid` with
  `getCoreRowModel` only, no pagination row model at all.
- **M5-07** `[UX] [vitest] [browser]` **Back to list restores the row, absolute rule.** A row
  click appends `from=<row id>` to the detail href; Back, the post-delete push and Edit all
  carry it; on list mount the row with that id is scrolled into view (`block: 'center'`) and
  highlighted until the next pointer or key event. Browser: open row 38 on Products page 2,
  the in-app "Back to list" button restores it centred and highlighted; the browser's own Back
  button does too, in one press, from a plain row-open. After stepping prev/next three times on
  the detail pager, the in-app Back to list button restores the record the reader ended on in
  one press; the browser Back button walks the pager's own history first (one press per step,
  N steps need N presses to reach the list) before it restores the list the same way - the
  pager keeps `router.push` per step on purpose (a reader may want to walk back through the
  records it visited), so this is the honest shape of the guarantee, not a defect.
  **Shipped (M5 run 1, `[vitest]` done, `[browser]` FAIL - see evidence run 1, Finding 1):**
  `components/ui/data-grid-table.listState.test.tsx`, `lib/listNavQuery.test.ts` (reserved-key
  case), `hooks/useListPager.test.ts` (`from=<landing id>` case). The browser walk found the
  browser's native Back button returned to the list's BARE original URL (no page, no `from`) in
  both the row-38-on-page-2 and pager-then-Back shapes, because `appendListState` only ever
  wrote list state into the DETAIL href - nothing wrote it into the LIST's own history entry.
  **Fix (evidence run 1 fix):** `LinkableBodyRow` (`components/ui/data-grid-table.tsx`) now
  calls `window.history.replaceState(window.history.state, '', <list path>?<same list
  state + from=<row id>>)` on the list's own history entry immediately BEFORE `router.push`ing
  the detail href open (row click and keyboard Enter both go through this one function; the
  middle-click/new-tab `window.open` path does not, since it leaves this tab's history alone).
  `history.state` is passed through unchanged so Next's own router state on that entry survives;
  `history.replaceState` is used rather than `router.replace` because the latter re-renders the
  list (and can refetch) for a navigation that is about to leave it anyway. Both `appendListState`
  and the new call build their params through the same `listStateParams`/`splitHref` helpers, so
  the list's own entry and the detail href it hands the reader cannot disagree. Tests:
  `components/ui/data-grid-table.listState.test.tsx` ("rewrites the list's own history entry
  before pushing" describe block) - `replaceState` fires once, before `push` (call-order
  assertion), naming page/limit/sort/dir/`from`, preserving `history.state`; the middle-click
  path does not call it; a keyboard Enter open does. The row-click and page-1 shapes are fixed by
  this same mechanism; the pager-step shape's `[browser]` half needs a **re-test** against the
  honest wording above (in-app Back to list in one press; browser Back walks the pager history
  first) rather than the original "press Back once" framing.
  **Review run 1 fix (S5/S7):** `returnedFromId` used to be resolved by a hook called PER ROW
  (N document listeners, N independent `cleared` states, a row mounting after the reader's
  first pointer event re-armed its own highlight). Now resolved ONCE per rendered grid
  (`DataGridTable`/`DataGridTableDnd`/`DataGridTableDndRows`) and passed down as a prop; a
  `keydown` listener clears it alongside `pointerdown`, hence "next pointer OR key event" above.
  **Review fix (M5 run 3 review, BL-2):** the history rewrite REPLACED the list's entire URL
  search with the detail href's own search, which has two failure modes proven against real call
  sites. (a) it wiped any param the list reads off its own URL but never echoes into `rowHref` -
  `GRNList.tsx` reads `spo_allocation_id` off its own URL (`GRNList.tsx:48`) but its `rowHref`
  (`:94-107`) never carries it, so Back landed on the unfiltered GRN list; `PurchaseOrdersList.tsx`'s
  `documents` filter (`:155`) has the same shape. (b) it fired even when the grid is not the
  current route's OWN list at all - `SeenInProductsTab.tsx`'s `rowHref` (`:91-92`) points at
  `/master-data-management/products/${id}`, not a child of the spec-key detail route
  (`SpecKeyRecordDetail.tsx`) it renders inside, so a row click there clobbered THAT page's own
  pager state (`page=1&limit=10` from the tab) onto the spec-key detail page's URL. Two rules fix
  both, in one place (`data-grid-table.tsx`'s `LinkableBodyRow`): (a) seed the replacement from
  `new URLSearchParams(window.location.search)` (the list's CURRENT params) and `.set()` onto it
  only the reserved list-state keys (`RESERVED_LIST_STATE_KEYS`: `page`, `limit`, `sort`, `dir`,
  `query`, `advFilter`, `from`), read off the already-built detail href - every other existing
  param survives untouched; (b) only rewrite when the detail href's path starts with
  `window.location.pathname + '/'` (a child route of the current page) - anywhere else, history is
  left alone entirely. Tests added to `data-grid-table.listState.test.tsx`: a list that arrived
  with `?spo_allocation_id=X&page=2` keeps `spo_allocation_id` and gains `from` plus the grid's own
  current page (`page=1`, from table state, overriding the stale `page=2` the URL arrived with); a
  grid whose `rowHref` points outside the current pathname does not call `replaceState` at all. The
  three run-1 tests (call order, middle-click, keyboard Enter) still pass unchanged.
- **M5-08** `[review]` `DESIGN-LANGUAGE.md` sections 4 and 7 and
  `documentation/reference/PR-CHECKLIST.md` state both rules; a new list without them is a
  checklist failure.
  **Shipped (M5 run 1):** `DESIGN-LANGUAGE.md` section 4 (`DataGrid` roster row) and section 7
  (bounded scroller + the `from=` rule); `PR-CHECKLIST.md` gains both under Apple Alignment.

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
  `components/ui/sonner.tsx` imports from `sonner` directly. `providers/query-provider.tsx`'s
  own error toasts (`toast.custom`, both the permission-denied and the generic path) are sticky
  too - `duration: Infinity` and a rendered close button that dismisses by the toast's own id -
  the same "wait for the reader" contract `toast.error` gives everywhere else.
- **M6-05** `[browser]` Tabbing to a dialog's close X shows the global focus ring.
- **M6-06** `[review]` The four portal search boxes adopt `useDebouncedSearch`; no hand-rolled
  `setTimeout(..., 250|300)` remains in `app/(auth)/portal`. `PortalLanding`'s plain search box
  also moves to `ListSearchInput`. `AsyncCombobox` / `MultiPillInput` / `AsyncMultiCombobox` are
  comboboxes (a dropdown, keyboard nav, free text) that `ListSearchInput` does not support, so
  they keep their own inputs and adopt only the hook, folding `isSettling` into their existing
  "Searching..." state the way `ListSearchInput`'s spinner does.
- **M6-07** `[browser]` A conversation thread with three images auto-scrolls to the bottom and
  stays there while the images load (each image is inside a fixed-aspect box).
- **M6-08** `[review]` `documentation/adr/` records the `ssr: false` provider decision.

## M7 Motion additions

- **M7-01** `[UX] [vitest]` The press-class inventory test from M1-08 is green: all 182 raw
  `<button` tags under `app/(protected)` carry `PRESSED_CLASS` on their own opening tag (or the
  element is replaced by the shared `Button`, which removes it from the inventory entirely).
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
