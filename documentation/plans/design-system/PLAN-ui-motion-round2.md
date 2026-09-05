# PLAN - UI and Motion Round 2: latency, perimeter motion, list rules

> The design that fulfils `ui-motion-round2-acceptance-criteria.md`. That file is the contract;
> where this plan and the UAC disagree, the UAC wins.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md` +
> `documentation/reference/DESIGN-LANGUAGE.md` (outranks the installed design skills).

**Slug:** `ui-motion-round2` | **Domain:** design-system (cross-cutting)
**Status:** IN PROGRESS - M4 built, three fix rounds, browser runs 2 and 3 green (evidence/M4), PR open. Audit 2 Sep 2026
(three read-only sweeps of `origin/main` e1adad4d2 with `review-animations`,
`find-animation-opportunities`, `emil-design-eng`, `apple-design`); user
approved all seven slices on the lavish review page 2 Sep 2026, order M4, M1+M2, M3, M5, M6, M7.
Issues: M4 #512, M1 #513, M2 #514, M3 #515, M5 #516, M6 #517, M7 #518. M1-M3 and M6-M7 unbuilt.
M5 run 1 of 3 done (`feat/motion2-M5-shells-and-list-rules`): M5-05 (sticky header, movable
columns, bounded scroller as `DataGrid` defaults), M5-06 (raw-table guardrail, red-proved with
27 offenders, all allowlisted - no migration yet, that is run 3), M5-07 (Back to list restores
the row, `from=`), M5-08 (docs). M5 run 2 of 3 done (same branch): M5-01 (loading.tsx inventory
widened from S7-04's hard-coded ten to a walk, 113 segments added, 123 of 123 covered), M5-02
(zero bare `Loading...`/`Loading…` strings, 50 files fixed, new shared `SectionSkeleton`
primitive), M5-03 (`ListPageSkeleton` row/header geometry now matches `data-grid-table.tsx`
exactly; its title/crumb order was corrected against the real `PageHeader.tsx` DOM order rather
than the brief's assumed one - see the coder's note in the commit and in the UAC), M5-04
(`app/(protected)/error.tsx` + `not-found.tsx`, render inside the shell). M5 run 3 of 3 done
(same branch): 24 of the 27 M5-06 allowlist entries migrated to `DataGrid` (the other 3
permanently exempt, below), one module per commit -
`PanelDataGrid` moved from `project-sales/_shared/components` to `components/common` (its first
caller outside project-sales, in the SLA commit) since 18+ callers across modules now share it.
The "inline editing may prove a real blocker" concern on `OrderLinesCard.tsx`,
`PurchaseRequestDocumentEditCard.tsx` and `PurchaseRequestForm.tsx` did not materialise:
`OrderLinesCard` turned out to be read-only (add/import are modal dialogs), and the two
react-hook-form `useFieldArray` line tables migrated cleanly to a plain `DataGrid`
(`getCoreRowModel` only, no pagination) - a dedicated focus-retention test confirms typing and
row-append keep the same input identity a hand-rolled `<table>` did. Only the three permanent
M5-06 exemptions (two `app/(auth)` portal pages, `ReportPivotTable.tsx`) remain allowlisted.
M5 is now fully built; still open: browser re-verification of the full run-3 diff (not yet
walked in `agent-browser`, unlike runs 1-2).
**M5 run 3 review (Phase 3) fixed:** BL-2 (`data-grid-table.tsx`'s history rewrite now merges
into the list's own URL params rather than replacing them, and only rewrites when the row's
detail href is a child route of the list - see M5-07 note below), BL-1 (scroller guardrail
enumeration missed `SLAPolicyTiersTable.tsx`), SF-1 through SF-8 (dialog scroller opt-out on
`AttachmentDetailModal.tsx`, restored header tooltips, right-aligned numeric headers across six
files, `SourceProformaInvoicesCard`'s Card-in-Card, `PanelDataGrid` gains a `paginate` prop so a
document's own line table renders every row, `fields.length` out of two columns memo deps, a
missing bulk-delete test on `TicketsList`) - see `685345d9a`. **M5 code is now complete; still
open: the browser walk of run 3 (tester next).**
**UAC:** `documentation/plans/design-system/ui-motion-round2-acceptance-criteria.md`
**Audit reports:** session scratchpad `audit-A-existing-motion.md` (36 rows, `/review-animations`
verdict Block, narrow), `audit-B-opportunities.md` (6 survivors, 10 rejects),
`audit-C-latency-ux.md` (20 findings, 18 censuses). Review page: lavish `ui-motion-audit.html`.
**Predecessor:** `PLAN-apple-alignment.md` S1-S9 (all on main by 31 Aug). This round is what the
skills found AFTER that work landed.
**Branch:** one branch per slice, `feat/motion2-M<n>-<slug>`, from `main`. One coder per
worktree; `/code-review` between slices; the two-slot rule applies.

---

## 1. What is being built, in one paragraph

The motion and loading standard the Apple Alignment round put inside `components/ui` is pushed
out to the rest of the app and made the default path: every list keeps its rows and its pager
while the next page arrives, every route the product is built around is prefetched on hover,
every press runs on the house curve, keyboard-initiated surfaces appear on the same frame, the
four progress bars and the shell stop animating layout, the reduced-motion preference reaches
everything that moves, and two list rules the user set as absolute become primitive defaults:
every table is a `DataGrid` with a sticky header and reorderable, resizable columns, and Back to
list returns the reader to the row they left. Six small motion additions land where the audit's
gate let them through. Guardrail tests are widened so the perimeter cannot drift again.

## 2. Why now (evidence, all measured on origin/main e1adad4d2)

- 60 of 63 paginated list hooks have no `placeholderData`; page, sort, filter and search are in
  the query key, so every change unmounts 186 grids to a skeleton and replaces the pager with
  two skeleton bars (`data-grid-pagination.tsx:150,180`, 151 call sites).
- `router.prefetch` appears nowhere; the only two `prefetch=` are `prefetch={false}`
  (`sidebar-menu.tsx:205,303`). Row click, the detail pager and every sidebar item cold-fetch.
- `PRESSED_CLASS` (`primitive-classes.ts:47`) has no duration or easing, and
  `--default-transition-timing-function` is not set in `@theme`, so every press and every bare
  `transition-*` runs on Tailwind's `cubic-bezier(0.4, 0, 0.2, 1)` ease-in-out.
- Two hard-fails verbatim from DESIGN-LANGUAGE: Cmd/Ctrl+Shift+K opens the command palette
  through the 300ms spring (`search-dialog.tsx:52-63`); arrow keys in the attachment lightbox
  run a ~330ms embla scroll (`AttachmentPreviewModal.tsx:164` via `carousel.tsx:57`).
- The sidebar collapse animates `width`, `padding-inline-start` and `inset-inline-start` for a
  literal `0.3s ease` across the whole page (`css/demos/demo1.css:4-5,36,73,141,146`), its
  hover-expand at `:77` is ungated, and none of it is in the reduced-motion block.
- 12 `transition-all` sites, 10 literal `duration-N` classes, 0 `@media (hover: hover)` gates,
  16 motion-bearing components with zero importers, 9 surfaces still on tw-animate keyframes
  beside 5 on the spring, one 300ms spring for menus and lightboxes alike.
- `SharedConversationComposer.tsx:737,825` disables its textarea on send; nothing refocuses in
  the `finally` at `:468`; no optimistic bubble.
- 10 `loading.tsx` for 123 list segments; 50 files render a bare `Loading...` string; 0
  `error.tsx` / `not-found.tsx` in 368 segments; `ListPageSkeleton` rows are 42px against a
  60px grid row (180px shift on every loading route).
- `providers/query-provider.tsx:18` sets no `defaultOptions`: 404 queries refetch on window
  focus, 314 have `staleTime: 0`, 325 retry 3 times; Products and Orders set `staleTime: Infinity`.
- 0 of 176 product `DataGrid` call sites set `headerSticky`; 24 product files still render a raw
  `<Table>` from `components/ui/table`; `BackToList` restores the query string but not the row.
- 127 files under `app/(protected)` render a raw `<button>` with no `PRESSED_CLASS`.

## 3. Standards (the design)

### 3.1 List query standard (M4)

**The shipped rule, in one sentence:** the primitive dims the body while
`isPlaceholderData` is true, every list forwards that flag from its own list
query, and the inventory tests are what keep both halves true.

- `lib/list-query/options.ts`: `export const LIST_QUERY_OPTIONS = {
  placeholderData: keepPreviousData } as const satisfies Partial<UseQueryOptions>`.
  Every paginated list hook spreads it: `useQuery({ ...LIST_QUERY_OPTIONS,
  queryKey, queryFn })`. The 3 hooks that already set it (e.g.
  `useIntegrationLogs.ts:62`) use the constant instead. Shipped: 126 spread
  sites across 101 files, with 2 allowlisted refusals (`hooks/useListPager.ts`,
  `mcp-tools/hooks/useMcpAdmin.ts` - see the walk descriptions below).
- **`isPlaceholderData` is forwarded at the call site, always.** The spread
  alone keeps the previous page's ROWS; it does not dim them. TanStack 5.90
  reports the window as `isLoading: false, isFetching: true,
  isPlaceholderData: true`, so a grid left to infer the state from `isLoading`
  never dims at all - which is exactly what shipped in the first two rounds and
  was caught in the browser. So each list reads the flag off its query
  (`const { data, isLoading, isPlaceholderData } = useOrders(params)`) and passes
  it: `<DataGrid ... isLoading={isLoading} isPlaceholderData={isPlaceholderData}>`.
  Shipped: 106 of the 190 `<DataGrid>` tags in `app/` and `components/` forward
  it, which is 94 of the 97 that page on the SERVER plus 12 client-paged grids
  fed by a hook that spreads the constant. The remaining tags page in the
  browser off rows they already hold, so there is no placeholder window for them
  to report and forwarding the flag would dim rows that are not placeholders.
- **Skeleton only when there is nothing worth showing.** `useBodySkeleton()` in
  `data-grid-table.tsx` is the single gate: `loadingMode === 'skeleton'` AND
  `isLoading` AND a page size AND (no rows yet OR column preferences are still
  resolving). `DataGridTable`, both drag variants and `DataGridPagination` all
  call it, so the pager and the rows cannot disagree about what a first load is.
  Column preferences are in the gate because painting rows under the DEFAULT
  layout and re-laying them out a tick later is a flash, and a reader who saw the
  wrong columns first does not trust the second answer either.
  `DataGridTableBody` keeps a second dim clause, `isLoading && rows.length > 0`,
  for the grids whose call site feeds it `isLoading || isFetching`.
- **Three guardrail walks, in `lib/list-query/options.inventory.test.ts` - a
  hook-side floor, and a grid-side ceiling.**
  - **Walk 1 (M4-01), the floor.** Every `useQuery` in `app/`, `components/`,
    `hooks/` and `services/`; fails on a list key that does not spread the
    constant. A list key is one that (1) names page/size/sort/filter/search
    state inline, (2) comes from a named list-key builder, or (3) carries a
    `params` / `listParams` bag - trigger 3 is what caught the ten hooks whose
    key names none of the words. It reads queryKeys, so it is a floor and not
    the whole rule: a hook keyed on a bare `filters` or `query` identifier names
    nothing it can see, and widening the regex to those two words would flag
    every report and detail query that keys on the same nouns. Allowlist (2):
    `hooks/useListPager.ts` (background neighbour lookup, renders no rows) and
    `mcp-tools/hooks/useMcpAdmin.ts` (unpaginated 500-row catalogue whose only
    key change is a filter toggle, so keeping the previous answer would show
    inactive rows to a reader who just asked for active ones).
  - **Walk 2 (M4-01b, import side).** From each spreading declaration to the
    files that import it; fails on any `<DataGrid>` there that does not pass
    `isPlaceholderData`.
  - **Walk 3 (M4-01b, the ceiling).** Every non-test file under `app/` and
    `components/` that sets `manualPagination: true` - the code declaring that
    the SERVER owns the page - must pass `isPlaceholderData` on every
    `<DataGrid>` tag in it. 97 files qualify. This is the check a new list
    actually has to get past, and it is what caught the four prop-fed and
    inline-query grids walk 2 structurally cannot reach (`LeadsGrid`,
    `ProjectsGrid`, `api-call-logs/page.tsx`, `MessageSnippetsList`,
    `ReorderResultsGrid`, `ReorderPolicyGrid`). Allowlist (3):
    `PriceTagRequestsList` (fetches in a `useEffect`, not react-query),
    `SpecTable` and `SpecProposalReview` (both `manualPagination` with
    `pageCount: 1`, which is how they turn client paging OFF on prop-fed rows).
  - **Out of M4's scope, stated once:** a list fetched outside react-query has
    no query to report a placeholder window, so it is allowlisted rather than
    converted. Moving those to react-query is its own piece of work.
- `providers/query-provider.tsx`: `defaultOptions.queries = { retry: 1, staleTime:
  30_000, refetchOnWindowFocus: false }`. The 173 per-hook `refetchOnWindowFocus: false`
  repeats are deleted in the same PR (mechanical, one module per commit).
  `useProducts.ts:52` and `useOrders.ts:108` drop `staleTime: Infinity` (the default
  now applies).
- The 8 list files carrying `disabled={isLoading}` on toolbar filters or the primary action
  (`ProductsList.tsx:733,789,802,815,826` and 7 more; census 5 in audit C) drop the guard.
  Mutation guards on forms and dialogs are untouched.
- Prefetch: `LinkableBodyRow` in `data-grid-table.tsx` calls `router.prefetch(href)` on
  `onPointerEnter`, through `usePrefetchOnce` (one `Set` ref, and a `(hover: none)`
  guard so a tap does not pay for a prefetch the click is already making).
  `useListPager` prefetches the prev and next hrefs when the current record
  mounts. `sidebar-menu.tsx` KEEPS `prefetch={false}` and adds the same
  pointer-enter prefetch on top: a Next 15 App Router `Link` prefetches on
  viewport by default in production, which on a ~100-item menu is the whole menu
  on mount, and that is why the flag was set. Hover is the middle ground.

### 3.2 Motion perimeter (M1)

- `primitive-classes.ts:47`: `PRESSED_CLASS` gains `duration-(--duration-fast)
  ease-(--ease-standard)`. `css/config.reui.css` `@theme` gains
  `--default-transition-timing-function: var(--ease-standard)` and
  `--default-transition-duration: var(--duration-fast)`.
- The 12 `transition-all` sites become exact property lists on the tokens: `progress.tsx:23`
  `transition-transform`, `progress.tsx:98,212` `transition-[stroke-dashoffset]`,
  `accordion.tsx:37,59`, `accordion-menu.tsx:354`, `collapsible.tsx:24` drop the class (height
  is keyframe-driven), `accordion.tsx:47` `transition-[transform,opacity]`, `badge.tsx:137`
  `transition-opacity`, `input-otp.tsx:44` `transition-[color,border-color,box-shadow]`,
  `AIAssistantBubble.tsx:450` drops `transition-all hover:w-9`, `company-documents.tsx:325`
  `transition-[stroke-dashoffset] duration-(--duration-base)`.
- Literal durations go to tokens: `demo1.css:4-5` `var(--duration-base)` /
  `var(--ease-standard)`; `sidebar-menu.tsx:156,159` replace the hand-rolled press with
  `PRESSED_CLASS`; `navigation-menu.tsx:63` `transition-transform duration-(--duration-fast)`;
  `navigation-menu.tsx:93` `origin-top-center` becomes `origin-top`; `screen-loader.tsx:7`
  drops its three dead transition classes; `EntityActivitiesLayout.tsx:156` drops `animate-pulse`
  and `bg-red-600` (use `bg-destructive`).
- `PRESSED_CLASS` added to `DropdownMenuItem`, `ContextMenuItem`, `MenubarItem`, `CommandItem`.
  Clickable `DataGrid` rows get `active:bg-muted/60` (not scale).
- `drawer.tsx:27` overlay uses `OVERLAY_CLASS_STATIC`.
- Delete the 16 unused motion components (`marquee`, `text-reveal`, `shimmering-text`,
  `sliding-number`, `counting-number`, `gradient-background`, `hover-background`,
  `grid-background`, `stepper`, `word-rotate`, `typing-text`, `avatar-group`, `video-text`,
  `github-button`, `skeleton-with-pattern`, `svg-text`); a vitest asserts zero importers
  before deletion and the build proves it after.
- `css/design-tokens.test.ts` globs widen to `app/**` and `components/common/**`; new
  assertions: no `transition-all`, no `transition-[width|height|margin|padding|inset]`
  (allowlist: the three `animate-accordion/collapsible` keyframe sites), no literal
  `duration-<N>` outside an allowlist file, no `ease-in`/`ease-in-out` on an entering element.
  A second test asserts every file under `app/(protected)` that renders `<button` either imports
  `Button` or carries `PRESSED_CLASS` (allowlist for the `sm` cluster carve-out).

### 3.3 Keyboard and timing (M2)

- `lib/motion.ts` gains `MENU_SPRING = { type: 'spring', bounce: 0, visualDuration: 0.2 }` and
  `SURFACE_SPRING_EXIT = { type: 'spring', bounce: 0, visualDuration: 0.2 }`;
  `surfaceTransition(prefersReducedMotion, kind: 'lightbox' | 'menu' = 'lightbox')` and a new
  `surfaceExitTransition(prefersReducedMotion)`. Dialog and Sheet keep 0.3 in, 0.2 out; Popover
  and DropdownMenu run 0.2 in, 0.2 out. DESIGN-LANGUAGE section 3 is updated (the ruling table
  already names the menu preset as follow-up).
- `CommandDialog` (`command.tsx:24`) takes `motion={false}` and renders `DialogContent` with
  `transition={{ duration: 0 }}` and no scale; `search-dialog.tsx` passes it. The overlay keeps
  a `--duration-fast` opacity fade. Escape close is also same-frame.
- `AttachmentPreviewModal.tsx:164-165`: arrow keys call `api.scrollNext(true)` /
  `api.scrollPrev(true)` (embla jump). Drag and dot navigation keep `duration: 20`.
- AlertDialog migrates to `useOpenState` + `AnimatePresence` + `surfaceVariants` +
  `surfaceTransition('lightbox')` exactly as `dialog.tsx:230-278`, overlay
  `OVERLAY_CLASS_STATIC`. `DropdownMenuSubContent` (`dropdown-menu.tsx:72`), `ContextMenuContent`
  and `SubContent`, `HoverCardContent`, `MenubarContent` move to the same path with `'menu'`.
  `NavigationMenu` viewport keeps tw-animate (one consumer, low traffic) but on the tokens.
- Tooltip: `tooltip.tsx` becomes a bare `Root`; one `TooltipProvider delayDuration={700}
  skipDelayDuration={300}` mounts in `ClientProviders.tsx`; content animates opacity only on
  `--duration-fast`, no zoom.

### 3.4 GPU and preferences (M3)

- `DeferredActionButton.tsx:95-103`: the fill is `origin-left` with
  `style={{ transform: 'scaleX(0)', transitionProperty: 'transform', transitionDuration:
  `${remainingMs}ms`, transitionTimingFunction: 'linear' }}` set once when the action parks
  (from `scaleX(1)` via a double rAF), `motion-reduce:transition-none` kept; the tick drops to
  1000ms and drives only the `role="timer"` label. `TakeoverCountdown.tsx:85` and
  `CashBudgetPanel.tsx:120` get the same `scaleX` treatment with tokens and `motion-reduce`.
- `EntityActivitiesLayout.tsx:144` stops animating `margin`: the panel overlays (the sibling at
  `:169` already uses `translate-x-full`); the content column no longer shifts.
- `css/styles.css` reduced-motion block adds `.demo1 .sidebar, .demo1 .wrapper, .demo1 .header
  { transition: none !important; }`, `[data-vaul-drawer] { transition-duration: 1ms !important; }`,
  and `[class*='transition-['] { transition-duration: 1ms !important; }`.
- `demo1.css:77` hover-expand wrapped in `@media (hover: hover) and (pointer: fine)`; the width
  transition also gated on `@media (prefers-reduced-motion: no-preference)`. The sidebar collapse
  itself (`width`/`padding`/`inset` for 300ms) is NOT rewritten here: a transform-only rewrite
  was tried and reverted (file comment). M3 records a DevTools trace on the Orders list during a
  collapse; if it drops frames, a separate ticket designs the transform version, else the
  transition becomes instant (rung 1).
- `AIAssistantBubble.tsx:269-277`: `onMove` writes `panelRef.current.style.width/height`
  directly (rAF-throttled) and commits to state on `pointerup`; the handle at `:443` joins the
  panel's `AnimatePresence` with a `--duration-fast` opacity exit.

### 3.5 Loading, error and list shells (M5)

- `loading.tsx` re-exporting `ListPageSkeleton` on every list segment under `app/(protected)`
  that renders a `<DataGrid` (113 to add; the inventory test at
  `app/(protected)/loading-inventory.test.tsx` holds the count). The 50 bare `Loading...`
  strings become `ListPageSkeleton` (list shapes) or a `Skeleton` block sized to the section.
- `ListPageSkeleton.tsx`: rows `px-4 h-[60px]` to match `data-grid-table.tsx:68`; the crumb bar
  renders ABOVE the title to match `PageHeader.tsx:145-156`.
- `app/(protected)/error.tsx` (client component, Reset button, renders inside the layout so the
  shell survives) and `app/(protected)/not-found.tsx`.
- **Sticky header (user ruling, absolute):** `data-grid.tsx:208` default `headerSticky: true`
  with `tableClassNames.headerSticky` defaulting to `sticky top-0 z-10 bg-background`; the
  `DataGridScroller` gets a bounded height by default (`max-h-[calc(100dvh-<toolbar+pager>)]`,
  one token `--grid-max-h` in `config.reui.css`, overridable per list) so the sticky header is
  observable. `columnsResizable` already defaults true; `columnsMovable` defaults to true
  (31 lists already opt in). The 24 product files rendering a raw `<Table>` from
  `components/ui/table` (list in audit C, e.g. `TicketsList.tsx`, `SLAPolicyTiersTable.tsx`,
  `FormSLAConfigList.tsx`, `EmailEventConfigsTable.tsx`, `McpToolsList.tsx`, `team-members-list.tsx`,
  the product detail tabs, the procurement detail sections) migrate to `DataGrid`, one module
  per commit; the detail-page line tables (`OrderLinesCard`, `PackingListLinesTab`,
  `PurchaseRequestDocumentEditCard`) migrate too unless their inline editing proves a real
  blocker, which the PR must state. A vitest asserts no product file imports
  `@/components/ui/table` outside an allowlist that starts empty.
- **Back to list restores the row (user ruling, absolute):** `appendListState` in
  `data-grid-table.tsx:27` appends `from=<row id>` to the detail href; `useHrefWithListState`
  forwards it unchanged (it already forwards the whole string). On list mount, `DataGridTable`
  reads `from` from `useSearchParams()`, and when a row with that id is on the current page it
  calls `scrollIntoView({ block: 'center' })` on it and sets `data-returned` for a
  `bg-primary/5` highlight that clears on the next pointer event. `parseDetailSearch` adds
  `from` to its reserved set. `useListPager` carries `from` as it steps so the row the user ends
  on is the one restored. `DESIGN-LANGUAGE.md` sections 4 and 7 and `PR-CHECKLIST.md` gain both
  rules.

### 3.6 Composer, mobile, toasts, focus (M6)

- `SharedConversationComposer.tsx`: the textarea and the attachment/emoji controls are never
  `disabled` during send; re-entry is the existing `if (sending) return` at `:415`; the sent
  text renders immediately as an optimistic bubble (`opacity-60`, replaced by the server row on
  refetch, removed with the error toast on failure); `finally` refocuses the textarea via the
  `queueMicrotask` pattern at `:195`. Send stays disabled while `sending`.
- `notifications-sheet.tsx:237`, `AIAssistantBubble.tsx:471`, `ConversationsInbox.tsx:89`:
  `vh` to `dvh`. `input.tsx` default size gains `pointer-coarse:text-base`. No `maximum-scale`.
- `ClientProviders.tsx:28` `<Toaster position="top-center" />`; `query-provider.tsx:64,79` drop
  their per-call `position`. New `lib/toast.ts` wrapping sonner: `toast.success` 4000ms,
  `toast.error` `duration: Infinity` with `closeButton`; the 1576 call sites switch import path
  (mechanical, one module per commit); a vitest asserts no direct `from 'sonner'` import outside
  `lib/toast.ts` and `components/ui/sonner.tsx`. `toast.custom` does not inherit that contract for
  free - sonner never gives a `jsx` toast its own close button, `Toaster`'s global `closeButton`
  prop notwithstanding - so `query-provider.tsx`'s two `toast.custom` error toasts (permission-
  denied and the generic path) each pass `duration: Infinity` and render their own `<Alert
  close onClose={() => toast.dismiss(id)}>`, using the id sonner's `custom` render prop hands
  back; the permission-denied path keeps its fixed `id: 'permission-denied'` dedupe.
- `dialog.tsx:267` drops `outline-0 focus:outline-hidden` on `DialogClose`.
- The four portal search boxes (`PortalLanding.tsx:373`, `AsyncCombobox.tsx:129`,
  `MultiPillInput.tsx:92`, `AsyncMultiCombobox`) adopt `useDebouncedSearch`, replacing every
  hand-rolled `setTimeout(..., 250|300)` in `app/(auth)/portal`. Only `PortalLanding`'s plain
  search box also moves to `ListSearchInput`: the other three are comboboxes (dropdown, keyboard
  nav, free text) that `ListSearchInput` does not support, so they keep their own inputs and fold
  `isSettling` into the "Searching..." state they already render.
- `RespondChatList.tsx:348-352` chat image inside an `aspect-[4/3]` box with `object-contain`.
- `DynamicClientProviders.tsx` `ssr: false` is recorded as a decision in
  `documentation/adr/` (accepted for an authenticated internal app), not changed.

### 3.7 Motion additions (M7)

Only the six that passed the gate. Each cites its recipe; each ships with a
`prefers-reduced-motion` branch through `useReducedMotion`.

- Pressed feedback sweep: the 127 feature files either render `Button` or add `PRESSED_CLASS`
  (M1's guardrail test turns red until they do; M7 makes it green).
- `data-grid-table.tsx:523`: `<tr>` gets `transition-opacity duration-(--duration-fast)
  ease-(--ease-standard) motion-reduce:transition-none` unconditionally.
- `DownloadRow.tsx:161` and `UploadSessionRow.tsx:41-72`: the Ready cluster inside
  `<AnimatePresence>` with `surfaceVariants` / `surfaceTransition`, `className="origin-right"`.
- `notifications-sheet.tsx:207-215` and `UploadActivityIcon.tsx:41-48`: `motion.span`
  `key={unreadCount}`, `initial={{ opacity: 0, scale: 0.6 }}`, `animate={{ opacity: 1, scale: 1 }}`,
  `transition={surfaceTransition(reduced, 'menu')}`.
- `LeadWizardDialog.tsx`: one `motion.div key={step}` around the branch block, incoming only,
  `initial={reduced ? { opacity: 0 } : { opacity: 0, transform: 'translateX(12px)' }}` with the
  sign from a `prevIndexRef`, `animate={{ opacity: 1, transform: 'translateX(0px)' }}`. No exit.
- The countdown bar itself lands in M3.

## 4. Slices and order

Issues (jayson-odoo/sorento-crm): M4 #512, M1 #513, M2 #514, M3 #515, M5 #516, M6 #517, M7 #518.

| Slice | Branch | Contents | Phase 1 (mock) | Phase 2 (tests) |
|---|---|---|---|---|
| M4 | `feat/motion2-M4-list-latency` | 3.1 | n/a (primitives + hooks) | vitest: `LIST_QUERY_OPTIONS` inventory, pagination stays live on placeholder, prefetch called once per href; browser: Products/Orders/Stock page turn keeps rows, Next twice works, Network shows prefetch on hover |
| M1 | `feat/motion2-M1-perimeter-hygiene` | 3.2 | n/a | vitest: widened token tests green, zero-importer test, press-class inventory; browser: press curve on a button, sidebar menu item, dropdown item |
| M2 | `feat/motion2-M2-keyboard-timing` | 3.3 | n/a | vitest: `CommandDialog motion={false}` renders no `motion.div` transition, `surfaceTransition('menu')` returns 0.2, tooltip provider single mount; browser frame-by-frame: palette same-frame, menu 200/200, AlertDialog scrim and panel in sync |
| M3 | `feat/motion2-M3-gpu-preferences` | 3.4 | n/a | vitest: countdown fill uses `transform`, reduced-motion CSS block contains the three selectors; browser: ResizeObserver count on the fill is 0 during a window, OS reduced-motion leaves the shell still, DevTools trace of a sidebar collapse on Orders recorded under `evidence/M3/` |
| M5 | `feat/motion2-M5-shells-and-list-rules` | 3.5 | n/a | vitest: loading inventory count, no `ui/table` import in product code, `headerSticky` default true, `from` param appended and restored; browser: Back from row 38 lands on row 38 highlighted, header sticks on Products at 1280 and 375, error.tsx keeps the sidebar |
| M6 | `feat/motion2-M6-composer-mobile-toasts` | 3.6 | n/a | vitest: composer keeps focus and shows the optimistic bubble, toast wrapper durations, no direct sonner import; browser at 375: bell/assistant/inbox bottoms visible, input focus does not zoom (device-emulated), toasts top-center |
| M7 | `feat/motion2-M7-motion-additions` | 3.7 | n/a | vitest: reduced-motion branch on each addition; browser frame-by-frame review recorded under `evidence/M7/` |

Order: M4 first (largest felt win, no dependency), then M1 and M2 together (clears the
`review-animations` Block; M2 depends on M1's `@theme` defaults only for cohesion), then M3, M5,
M6, M7. M7 depends on M1 (press token) and M3 (countdown bar). M5's two list rules are
independent of everything and may be split out if the raw-table migration grows.

## 5. Testing seams (agreed before Phase 2)

- Backend tests run on Postgres only (`tests/_pg_fixture.py`); this round has no backend change
  except none expected (all frontend). If a slice touches the API, it says so in the PR.
- Every browser run: agent-browser, sidebar navigation from `/`, 375 and 1280, evidence under
  `documentation/plans/design-system/evidence/M<n>/`. Frame-by-frame reviews use the DevTools
  Animations panel at 4x slow-down.
- Inventory tests (loading.tsx count, `LIST_QUERY_OPTIONS`, `ui/table` imports, press class,
  sonner imports) are the guardrails that keep each rule true after the slice merges.

## 6. Not built (deferred to `documentation/backlogs/backlog.md`)

- Sidebar collapse transform rewrite: gated on the M3 trace.
- Sheet `x`/`y` and `surfaceVariants` `scale` shorthand to full transform strings: measure first.
- AI panel rubber-banding at the resize clamp (polish).
- `ssr: false` on the provider tree: recorded, not changed.
- A stronger ease-out curve than `--ease-standard`: ADR only, per DESIGN-LANGUAGE section 1.
- The ten rejected motion candidates in audit B (command palette, row expand, dashboard stagger,
  portal typeahead scale, idle-to-countdown crossfade, view-to-edit crossfade, record slide on
  prev/next, PWA banner height, counting numbers, skeleton crossfade). Do not re-propose.

## 7. Risks

- `placeholderData` keeps stale rows visible while a new page loads; a list whose columns change
  with the filter (grouped views) may show a mismatched header for one frame. The dim state
  makes it legible; verify on the SCM reorder grid, which swaps column sets.
- Dropping `refetchOnWindowFocus` globally changes freshness on detail pages that relied on it;
  the 30s `staleTime` default plus mutation invalidation covers the known cases. The conversation
  surfaces keep their own `refetchInterval`.
- `headerSticky` needs a bounded scroller; a list inside a dialog or a tab with its own scroll
  container may double-scroll. The default is overridable per list and M5's browser sweep covers
  the 24 migrated tables plus the three longest lists.
- Migrating 24 raw tables to `DataGrid` touches inline-editing line tables; a table whose
  editing cannot be expressed as a `DataGrid` cell stays on the allowlist with the reason in the
  PR, and the allowlist is reviewed at the next round.
- The sonner wrapper touches 1576 call sites; one module per commit so a wrong import is
  bisectable, and the no-direct-import test catches stragglers.
- The 127-file press sweep is mechanical but wide; M1's guardrail test defines done.
