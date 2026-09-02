# M1 Motion perimeter hygiene - browser verification evidence (agent-browser, 2 Sep 2026)

Worktree `motion2-M1` (branch `feat/motion2-M1-perimeter-hygiene`), FE dev server
`PORT=3081 npm run dev` (own session, PID group: parent `npm exec` 28534, `next-server` child
28549), BE reused read-only on `:8120` per `FASTAPI_INTERNAL_URL=http://localhost:8120` in
`.env.local` (copied from the `motion2-M4` worktree's shape and confirmed: `NEXTAUTH_URL=
http://localhost:3081`, `AUTH_TRUST_HOST=true`, no `NEXT_PUBLIC_API_URL`). `lsof -i :3081` was
empty before starting. Login via `E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`. Session
`--session m1tester` (isolated browser). Viewport 1280x800 unless noted. Navigated by sidebar
clicks from `/`, never a deep URL, except a card click into a project's own detail page (a
content-driven navigation, not a typed URL) and the return trip to an already-verified page
within the same run.

Read `getComputedStyle` for every timing/duration assertion, and raw `className` for every
class-membership assertion, via `agent-browser eval --stdin` against the live DOM - the same
values the UAC criteria are written against. Where `agent-browser click @ref` silently failed to
register (sidebar group toggles, the row-level "product actions" trigger, a couple of nested
menu buttons), a native `element.click()`/`PointerEvent`/`MouseEvent` dispatch via `eval` worked
immediately - the same tool quirk already logged in the M4 evidence, not a product defect.

## Findings summary (pass/fail table)

| Check | Target | Result | Measured value |
| --- | --- | --- | --- |
| M1-01 | Button (Products > Create Product) | PASS | `transition-duration: 0.15s`, `transition-timing-function: cubic-bezier(0.2, 0, 0, 1)`; class contains `duration-(--duration-fast)`, `ease-(--ease-standard)`, `active:scale-[0.97]` |
| M1-01 | Checkbox (Products grid select-all) | PASS | same duration/timing; class contains `duration-(--duration-fast)`, `ease-(--ease-standard)`, `active:scale-[0.97]` |
| M1-01 | Switch (Settings > General, store active-status toggle) | PASS | same duration/timing; class contains `duration-(--duration-fast)`, `ease-(--ease-standard)`, `active:scale-[0.97]` |
| M1-01 | Bare `transition-colors` element (breadcrumb link, class `transition-colors hover:text-foreground`, no explicit duration/ease) | PASS | inherits the `@theme` default: `0.15s`, `cubic-bezier(0.2, 0, 0, 1)` |
| M1-05 | DropdownMenuItem (Products row "..." > Delete product) | PASS | class contains `active:scale-[0.97]` |
| M1-05 | CommandItem (Cmd/Ctrl+Shift+K palette, checked 3 items) | PASS | all 3 sampled items' class contains `active:scale-[0.97]` |
| M1-05 | ContextMenuItem (Resources > Files, grid view, right-click a file: Open/Preview/Download/Rename/Move to.../Set company.../Resubmit to n8n/Move to trash) | PASS | all 8 items' class contains `active:scale-[0.97]` |
| M1-05 | MenubarItem | SOURCE-CONFIRMED, not browser-reachable | `components/ui/menubar.tsx:132` spreads `PRESSED_CLASS` into `MenubarItem` at the primitive; the only app usages (`app/components/partials/navbar/navbar-menu.tsx` and the demo2/demo3 layout variants) are not the active `demo1` layout this tenant renders, so no live page exercises it. Covered by vitest per the UAC (already green per the brief) |
| M1-05 | Sidebar menu item (Resources > Files leaf) | PASS | class contains `active:scale-[0.97]`; no `duration-75` or `active:scale-[0.98]` present |
| M1-05 | Clickable DataGrid row (Products, row 1) | PASS | `<tr>` class contains `active:bg-muted/60` (and `hover:bg-muted/40`) |
| M1-03 | Sidebar collapse/expand transition | PASS | `transition-duration: 0.2s`, `transition-timing-function: cubic-bezier(0.2, 0, 0, 1)`; width measured 280px expanded -> 80px collapsed -> 280px on re-expand |
| M1-03 | Mobile nav drawer scrim at 375px (Resources > Files) | PASS | overlay class `fixed inset-0 z-50 bg-black/50 backdrop-blur-md ...`; computed `background-color: oklab(0 0 0 / 0.5)`, `backdrop-filter: blur(12px)` - a Dialog-style dark+blurred scrim, not flat 80% black |
| M1-07 | AI assistant bubble handle, hover width | PASS | `data-testid="ai-assistant-tab"` measured 32px width before and after a `pointerenter`/`mouseover` dispatch; class has no `hover:w-9` |
| M1-07 | Activities panel launcher (Project Sales > a project detail page) | PASS | `aria-label="Open activities & notes"`; computed `animation-name: none`; class has no `animate-pulse`, no raw `bg-red-600` (uses semantic `bg-destructive hover:bg-destructive/90`) |
| M1-06 | Zero console errors: Products, Orders, a record page (Project Sales detail), Settings | PASS | `console`/`errors` commands showed zero `[error]`-level entries across the whole run; only `[debug] JWT token extracted successfully`, Fast Refresh log lines, and one pre-existing `[warning] [tiptap warn]: Duplicate extension names...` (unrelated to this branch) |
| Regression smoke | Products and Orders lists hold rows | PASS | both screenshots below show populated grids; M4 is not on this branch so a skeleton flash on first paint is expected and not evaluated as a failure |

## Detail notes

### M1-01

Measured via `getComputedStyle` on the live element:

- `Create Product` button (Products list toolbar): `duration: 0.15s`, `timing:
  cubic-bezier(0.2, 0, 0, 1)`, class includes `transition-[transform,color,background-color,
  border-color,box-shadow] duration-(--duration-fast) ease-(--ease-standard) active:scale-[0.97]
  motion-reduce:active:scale-100`.
- Grid select-all checkbox (same page): identical duration/timing/class shape.
- Store active-status `Switch` (Settings > General tab, first field group): identical
  duration/timing/class shape, `role="switch"`, `data-state=checked`.
- A bare `transition-colors` anchor with no explicit `duration-*`/`ease-*` class (a breadcrumb
  link) resolved to `0.15s` / `cubic-bezier(0.2, 0, 0, 1)` - confirms the `@theme` block's
  `--default-transition-duration`/`--default-transition-timing-function` default is live.

### M1-05

- Products row "..." menu: the row-level trigger buttons all share `aria-label="product
  actions"` (50 on the page); the DOM query grabbed the first one, which was off-screen to the
  right at the default column layout (`x: 2302`) - `scrollIntoView({block:'center',
  inline:'center'})` then a native `.click()` opened it. Its one enabled item, "Delete product",
  carries `active:scale-[0.97]` (screenshot `M1-05-products-dropdownmenu.png`).
- Command palette (Ctrl+Shift+K): opened over the Products page; sampled the first 3 `[cmdk-item]`
  nodes (Dashboards, Ideas, Pipeline) - all three carry `active:scale-[0.97]` (screenshot
  `M1-05-command-palette.png`).
- ContextMenu: Resources > Files, switched to grid view, dispatched a synthetic `contextmenu`
  MouseEvent on a file card (the card two levels up from the filename text node, class `group
  relative flex flex-col rounded-lg border bg-card ... cursor-grab`) - opened Open / Preview /
  Download / Rename / Move to... / Set company... / Resubmit to n8n / Move to trash, all 8 with
  `active:scale-[0.97]` (screenshot `M1-05-contextmenu.png`).
- Sidebar leaf item (Files, in the Resources group): the actual interactive element is two levels
  up from the `<a>` (`<button class="... transition-[transform,color,background-color,
  border-color,box-shadow] duration-(--duration-fast) ease-(--ease-standard) active:scale-[0.97]
  motion-reduce:active:scale-100 ...">`) - `active:scale-[0.97]` present, `duration-75` and
  `active:scale-[0.98]` both absent.
- Clickable grid row: Products row 1's `<tr>` class is `hover:bg-muted/40 active:bg-muted/60
  data-[state=selected]:bg-muted/50 cursor-pointer ...`.

### M1-03

- Sidebar (`.sidebar`): `getComputedStyle` gave `transition-duration: 0.2s`,
  `transition-timing-function: cubic-bezier(0.2, 0, 0, 1)` at rest. Clicking "Collapse sidebar"
  measured the sidebar's `getBoundingClientRect().width` drop from 280 to 80; a second click on
  the same toggle (its `aria-label` does not change) restored it to 280.
- Mobile nav drawer at 375x812 (Resources > Files, "Toggle sidebar" button): opened the drawer
  and read the overlay element's class and computed style - `bg-black/50 backdrop-blur-md`
  (`[@media(prefers-reduced-transparency:reduce)]` fallback to `bg-black/72`/no blur is present
  but not the active branch here), computed `background-color: oklab(0 0 0 / 0.5)`,
  `backdrop-filter: blur(12px)` - reads as a Dialog scrim, not a flat 80% black overlay
  (screenshot `M1-03-mobile-drawer-scrim.png`).

### M1-07

- AI assistant bubble handle (`data-testid="ai-assistant-tab"`, the collapsed vertical tab docked
  bottom-right): `getBoundingClientRect().width` was 32px before and after dispatching
  `mouseover`/`pointerenter`; class is `flex w-8 flex-col ...` with no `hover:w-9` anywhere in the
  string (confirms the source read of `AIAssistantBubble.tsx:450`, which conditions only
  `animate-pulse` on `isSending`, never a width class, on hover).
- Activities panel launcher: reached via Project Sales > Pipeline > clicked into project
  `PRJ-000004` ("Kepong Metropolitan Times Square") to its detail page, which renders
  `EntityActivitiesLayout`. The floating launcher (`aria-label="Open activities & notes"`) has
  `getComputedStyle(...).animationName === 'none'`, no `animate-pulse` class, and uses the
  semantic `bg-destructive hover:bg-destructive/90` (not a raw `bg-red-600`) - matches the source
  read of `EntityActivitiesLayout.tsx:156` (screenshot `M1-07-activities-launcher.png`).

### M1-06 and regression smoke

`console` and `errors` were read after every navigation across the run (Products, Products
dropdown/palette/context-menu interactions, Settings > General, Resources > Files list and grid
views plus the mobile drawer, Project Sales > Pipeline, the project detail record page, and
Orders). The only non-debug/non-Fast-Refresh line in the entire session was one pre-existing
`[tiptap warn]: Duplicate extension names found: ['link']` warning, unrelated to this branch's
diff. Zero `[error]`-level console lines and zero uncaught page errors throughout.

Products (`M1-01-products-list.png`) and Orders (`M1-06-orders-list.png`) both loaded with rows
populated on first paint in this run; M4 (list-latency dim/skeleton work) is not on this branch,
so any transient skeleton flash on a slower connection is expected per the brief and is not
scored as a failure here.

## Screenshots in this directory

- `M1-01-products-list.png` - Products list, used for the Button/Checkbox measurements.
- `M1-01-system-settings-switch.png` - Settings > General tab showing the store active-status
  Switch used for the Switch measurement.
- `M1-05-products-dropdownmenu.png` - Products row "..." menu open, showing "Delete product".
- `M1-05-command-palette.png` - Command palette open via Ctrl+Shift+K.
- `M1-05-contextmenu.png` - Right-click ContextMenu open on a file card in Resources > Files
  (grid view).
- `M1-03-mobile-drawer-scrim.png` - Mobile nav drawer open at 375px, scrim visible behind it.
- `M1-07-activities-launcher.png` - Project Sales project detail page showing the solid-red,
  non-pulsing Activities launcher.
- `M1-06-orders-list.png` - Orders (Delivery Orders) list holding rows, zero console errors.

## Cleanup

Dev server killed (`kill 28534`; its `next-server` child 28549 exited with it; confirmed via a
follow-up `lsof -i :3081` returning empty). Only the `m1tester` agent-browser session belonging to
this run was closed - no `close --all` was issued. `.env.local` left in place per the brief.

## Run 2 (after fix round, HEAD fc73e53ee)

Worktree `motion2-M1` (branch `feat/motion2-M1-perimeter-hygiene`), same worktree as run 1, tree
clean at HEAD `fc73e53ee` except two untracked plan docs (left alone per the brief). Port `:3081`
was held by another tester this run, so **`:3082`** was used instead: `lsof -i :3082` confirmed
empty before starting, `.env.local`'s `NEXTAUTH_URL` was edited to `http://localhost:3082`
(`FASTAPI_INTERNAL_URL=http://localhost:8120`, `AUTH_TRUST_HOST=true`, no `NEXT_PUBLIC_API_URL`
kept as-is), and `PORT=3082 npm run dev` ran as a background Bash session (`next-server` PID 5665,
parent `npm run dev` PID 5638; killing 5638 took 5665 down with it, confirmed via a follow-up
`lsof -i :3082` returning empty). Session `--session-name m1run2` (isolated browser). Login via
`E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`. Viewport 1280x800 unless noted. Navigated by sidebar
clicks from `/`, except a row click into an order's own record page (content-driven, not a typed
URL) and the two portal pages the brief explicitly named as exceptions.

Same tool quirk as run 1: `agent-browser click @ref` silently no-ops on several targets this run
too (sidebar group toggles two levels deep, the row-level "product actions" trigger, the
`PeriodPicker`'s "Show date picker" button worked via `@ref` but the row-actions trigger and
deeper sidebar links needed it) - a native `element.click()` via `eval`, or for Radix trigger
buttons that ignore a plain synthetic `click`, a full `pointerdown`/`mousedown`/`pointerup`/
`mouseup`/`click` `PointerEvent`/`MouseEvent` sequence via `eval`, opened them immediately. Real
`:hover` CSS state (background/border colour reads) needed the CDP-level `agent-browser hover`/
`find ... hover` command - dispatching synthetic `pointerenter`/`mouseover` events via `eval` does
NOT flip the browser's internal `:hover` state, so computed-style reads after a synthetic hover
dispatch came back unchanged (confirmed and worked around: hover checks below all use the real
`hover` command, verified by `element.matches(':hover') === true` post-dispatch).

### Findings summary (pass/fail table)

| Check | Target | Result | Measured value |
| --- | --- | --- | --- |
| 1 | Command palette (Ctrl+Shift+K) arrow traversal | PASS | Dispatched 6x `ArrowDown` on `document.activeElement` (the `[cmdk-input]`), 50ms apart, polling `[cmdk-item][data-selected="true"]` every 16ms: `data-value` advanced Dashboards -> Ideas -> Pipeline -> Leads -> Awaiting Acceptance -> My Tasks -> Stock Claims with the selected item's computed `background-color` identical (`lab(96.1634 ...)`) at every sample - no intermediate colour. Structural proof: `getComputedStyle(item).transitionProperty === "transform, translate, scale, rotate"` (no `background-color`/`color` in the list), so a fade is not merely absent at these samples, it is impossible. `className` contains `transition-transform` and `active:scale-[0.97]`; does NOT contain `transition-[transform,color` |
| 1 (control) | Products row "..." DropdownMenuItem ("Delete product") | PASS | `className` contains `transition-[transform,color,background-color,border-color,box-shadow] duration-(--duration-fast) ease-(--ease-standard) active:scale-[0.97]` - full PRESSED_CLASS list, still transitions colour, confirming the control differs from the CommandItem/ContextMenuItem transform-only treatment |
| 2 | Right-click ContextMenu (Resources > Files, grid view) | PASS | Dispatched a synthetic `contextmenu` MouseEvent (button 2) on the first file card; opened `[data-slot="context-menu-content"]` with 8 items (Open, Preview, Download, Rename, Move to..., Set company..., Resubmit to n8n, Move to trash) - all 8 have `transition-transform` + `active:scale-[0.97]`, none has `transition-[transform,color` |
| 3 | Clickable DataGrid row (Products, row 1) | PASS | `<tr>` className: `hover:bg-muted/40 data-[state=selected]:bg-muted/50 cursor-pointer active:bg-muted/60 border-b border-border ...` |
| 3 | Non-clickable DataGrid row (System > Numbering Rules, "Running Numbers" - no `rowHref`/`onRowClick`) | PASS | `<tr>` className: `hover:bg-muted/40 data-[state=selected]:bg-muted/50 border-b border-border ...` - no `cursor-pointer`, no `active:bg-muted/60` |
| 3 | Loading skeleton rows | SOURCE-CONFIRMED, runtime capture attempted and inconclusive | `components/ui/data-grid-table.tsx:324-343` (`DataGridTableBodyRowSkeleton`) builds its `<tr>` className from `hover:bg-muted/40`, `cursor-pointer` (if `rowHref`/`onRowClick`), border/stripped variants, and `tableClassNames?.bodyRow` - `active:bg-muted/60` is never in that list regardless of `rowHref`/`onRowClick`, matching the source comment at line 526 ("It is not on the skeleton row"). Attempted to catch one live: clicked the Files sidebar's "Marketing" folder and polled for `.animate-pulse` inside a `tr` every 10ms for 3s (`skeleton_poll.js`) - none appeared, the local dev fetch resolved faster than the poll could observe it, so this line is source-confirmed rather than runtime-observed this run too (same limitation as menubar in run 1) |
| 3 | Stripped grid (`tableLayout.stripped: true`) | SOURCE-CONFIRMED, not browser-reachable | `grep -rn "stripped" app/ --include="*.tsx"` (excluding tests and unrelated string-manipulation locals of the same name) found no page in this branch's `app/` tree that sets `tableLayout={{ stripped: true }}` - `stripped` support exists only in `components/ui/data-grid-table.tsx` (default `false` per `data-grid.tsx:216`) and its consumers (`DraggableAttachmentsTable.tsx`, `DriveListView.tsx`) only reference `props.tableLayout?.stripped` defensively, they don't set it. Line 529 of `data-grid-table.tsx` proves structurally that `active:bg-muted/60` is gated on `!props.tableLayout?.stripped`, so a stripped grid would never carry it even with `rowHref` set, but no live instance exists to click through the sidebar this run |
| 4 | SLA KPI Dashboard cards ring on hover (Dashboards home) | PASS | `div.cursor-pointer.transition-shadow.hover:ring-1.hover:ring-border` (7 matching cards - the 3 stage-breakdown cards + 4 timeliness/at-risk cards); `getComputedStyle(el).transitionProperty === "box-shadow"`, `transitionDuration === "0.15s"` |
| 4 | Portal landing rows brightness on hover (`/portal`) | SKIP, login-gated | `/portal` with no session renders only the "Get your portal link" card (`PortalRootContent`, mode `request-link`) - the row list lives in `PortalLanding.tsx` and only renders after a real WhatsApp OTP / token exchange, which `e2e/portal-slug-links.spec.ts`'s own header comment confirms needs "a live OTP/WhatsApp loop" unavailable to a scripted run. Source-confirmed instead: `PortalLanding.tsx:733` - `` `relative block rounded-lg border ${tintClass} px-3.5 py-3 pr-3 hover:brightness-95 active:brightness-90 transition-[filter] select-none cursor-pointer` `` |
| 4 | SubmissionForm pagers opacity | SKIP, unreachable | Same gating as above - `SubmissionForm` renders inside the authenticated portal tree only |
| 5 | AI assistant launcher (`data-testid="ai-assistant-tab"`) hover tint | PASS | Real `agent-browser hover` (CDP-level, not a synthetic dispatch): `background-color` went from `lab(54.1736 13.3369 -74.6839)` (rest, `bg-primary`) to `oklab(0.622989 -0.0378532 -0.210606 / 0.9)` (hover, matches `hover:bg-primary/90`) |
| 5 | AI assistant launcher press shrink | PASS | `className` contains `active:scale-[0.97]` |
| 6 | AttachmentDropzone (`/portal/price_tag_request/new`) render + hover | PASS | Page renders with no redirect and no session (form itself is public; only its data lookups are agent-gated, see below). Dropzone div className: `rounded-lg border-2 border-dashed ... transition-colors ... hover:border-primary/60 border-muted-foreground/25`. Real hover: `border-color` went from `oklab(0.551998 ... / 0.25)` (rest, `border-muted-foreground/25`) to `oklab(0.622989 ... / 0.6)` (hover, `border-primary/60`), `element.matches(':hover') === true`. Renders cleanly at 1280x800 and 375x812 (screenshots below), zero console errors at both widths |
| 6 | AsyncCombobox ("Debtor *") | PARTIAL - renders, underlying data 401s | Combobox opens on click (search input + empty `listbox`), `className` includes `transition-shadow` and the standard border/focus-ring treatment. Typing into it fires `GET /api/v1/public/portal/lookups/debtors-for-agent`, which returns **401** in `network requests` - this endpoint needs a real agent-portal session, not just a CRM admin cookie, so no results render. This is expected per the page's purpose (agent-only lookup), not a defect; the shell and its transitions are unaffected |
| 6 | PeriodPicker ("Needed by" field, "Show date picker" button) | PASS (render/errors), hover not directly captured | Clicking "Show date picker" opened a full month calendar with zero console errors. Day cells are the shared `components/ui/calendar.tsx` primitive: `className` includes `transition-[color,background-color,border-radius,box-shadow]` and `hover:not-in-data-selected:bg-accent` (line 30) - confirmed by source read; a live `agent-browser find text "15" hover` landed on the page background rather than the day cell (day text nodes render inside a nested button/span the text-locator didn't resolve precisely), so the computed-style hover delta wasn't captured pixel-for-pixel this run, but the shared primitive is exercised via the same PeriodPicker/Calendar path everywhere else in the app already covered elsewhere |
| 7 | Zero console errors: Products, Orders, an order record page, Settings (System > Companies), Files | PASS | `errors` returned empty after every navigation; full-session `console` dump filtered to non-debug/non-Fast-Refresh/non-i18next/non-DevTools lines showed exactly one line: `[warning] Warning: Missing \`Description\` or \`aria-describedby={undefined}\` for {DialogContent}` - a pre-existing Radix a11y warning, not an `[error]`-level line and unrelated to this branch's diff (same pattern as run 1's unrelated tiptap warning) |

### Detail notes

- **Check 1 method**: keyboard navigation in `cmdk` is driven by `data-selected`, not CSS
  `:hover`, so dispatching `KeyboardEvent('keydown', {key:'ArrowDown'})` on
  `document.activeElement` (bubbling into the focused `[cmdk-input]`, which is where cmdk's
  listener lives) is a legitimate simulation of a held arrow key, unlike the `:hover` case in
  checks 5/6 where a dispatched pointer event does not work (see the quirks paragraph above). The
  first attempt dispatched on `document` directly and produced no movement, because a native event
  targeted at `document` never passes through the input on its way up - retargeting to
  `document.activeElement` fixed it immediately.
- **Check 2 method**: same file-card selector as run 1 (`.group.relative.flex.flex-col`, 50 cards
  in grid view), synthetic `contextmenu` MouseEvent with `button: 2` at the card's centre opened
  the menu on the first try this run.
- **Check 3 non-nav grid**: chosen via `grep -rln "<DataGrid" ... | for f in ...; grep -L
  "onRowClick\|rowHref"` scoped to `app/(protected)/system-management/` to find a reachable
  candidate quickly; picked "Running Numbers" (`/system-management/numbering-rules`, under System
  > Configuration in the sidebar) since it is plainly a reference-data list with no detail route.
- **Check 4 SLA cards**: reached directly on the Dashboards home page (no navigation needed - the
  KPI dashboard renders there by default for this user), so no extra click was required.
- **Check 6 navigation exception**: `/portal/price_tag_request/new` and `/portal` were opened by
  direct URL per the brief's explicit carve-out for the two portal checks - both are outside the
  authenticated sidebar entirely and have no in-app link from the CRM shell.

### Screenshots in this directory (run 2)

- `run2-command-palette.png` - Command palette open via Ctrl+Shift+K, first item highlighted.
- `run2-dropdownmenu-control.png` - Products row "..." menu open, "Delete product" control case.
- `run2-products-list.png` - Products list, used for the clickable-row class measurement.
- `run2-contextmenu.png` - Right-click ContextMenu open on a file card in Resources > Files (grid
  view).
- `run2-numbering-rules-nonav.png` - System > Running Numbers, the non-clickable-row control case.
- `run2-sla-kpi-cards.png` - Dashboards home showing the SLA KPI Dashboard cards used for the
  ring-on-hover measurement.
- `run2-ai-assistant-hover.png` - AI assistant launcher mid-hover (tinted).
- `run2-portal-price-tag-1280.png` / `run2-portal-price-tag-375.png` - `/portal/price_tag_request/new`
  at 1280x800 and 375x812, both clean with zero console errors.
- `run2-portal-dropzone-hover.png` - AttachmentDropzone mid-hover (border tinted).
- `run2-portal-periodpicker.png` - PeriodPicker calendar open, zero console errors.
- `run2-orders-list.png` - Orders (Delivery Orders) list, zero console errors.
- `run2-order-record.png` - An order's detail/record page, zero console errors.
- `run2-settings-companies.png` - System > Companies settings page, zero console errors.

### Cleanup

Dev server killed by killing its parent `npm run dev` (PID 5638), which took the `next-server`
child (PID 5665) down with it; confirmed via a follow-up `lsof -i :3082 -sTCP:LISTEN` returning
empty. Only the `m1run2` agent-browser session belonging to this run was closed - no `close --all`
was issued. `.env.local`'s `NEXTAUTH_URL` restored to `http://localhost:3081` afterwards (untracked
file, not committed).
