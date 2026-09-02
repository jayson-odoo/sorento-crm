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
