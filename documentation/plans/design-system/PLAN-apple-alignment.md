# PLAN - Apple Alignment: pills, rows, detail header, pager, deferred actions, lightbox, tabs, mobile grids

> The design that fulfils `apple-alignment-acceptance-criteria.md`. That file is the contract;
> where this plan and the UAC disagree, the UAC wins.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md`.

**Slug:** `apple-alignment` | **Domain:** design-system (cross-cutting)
**Status:** IN PROGRESS - plan approved 2026-08-29 (lavish review + grill; D15, D16 added); S1 started 2026-08-29. S5 built 2026-08-30 (`feat/apple-S5-wayfinding`): PageHeader + the sweep of every module, GRN/SPO eyebrows, verb + noun labels, UUID titles, DataGrid `emptyAction`. S6 built 2026-08-30 (`feat/apple-S6-deferred-actions`): Phase 1 gave the deferred-action service, hook, countdown, toast and row dimming, with Users, Products and Orders on them against an in-memory `/pending-actions`. Phase 2 replaced that mock with the real routes (`app/api/v1/system/pending_actions.py`, mounted at `/pending-actions`), four handlers in `app/services/record_actions.py` on the widened form-action registry, the two System Settings windows (migration `s6_deferred_action_windows`, UNRUN) and the tests (30 pytest, 26 vitest). S6b built 2026-08-30 (`feat/apple-S6b-confirm-sweep`): 41 of the 69 `ConfirmDeleteDialog` importers migrated across master data, marketing, inventory, integrations, tickets, workflow forms, SLA, system management, user management, settings, dealer kit and SCM, plus all nine native `confirm()` calls; 45 new handlers in `record_actions.py` (49 record actions in the registry, beside the 13 form-SLA ones); `hooks/useDeferredRowAction.tsx` for the list-row shape; bulk delete on products and orders parks one action per selected row behind one aggregate countdown; migration `s6b_record_action_entity_id` widens `sla_form_actions.source_entity_id` to `VARCHAR(128)` because three of the swept records are keyed by a code rather than a uuid and a product's specification value is keyed by `<product id>:<spec key>`. 28 importers remain and `ConfirmDeleteDialog` is NOT yet deleted - 22 of them are project-sales, which authorises per RECORD rather than by a static slug and needs an engine change first (see S6-10 in the UAC for the trigger and for the four kept cases).
**UAC:** `documentation/plans/design-system/apple-alignment-acceptance-criteria.md`
**Audit:** artifact `https://claude.ai/code/artifact/86a2cb9e-41e2-4008-9fbd-1f86de8bb0db` (rounds 1-3, 29 Aug 2026)
**Supersedes:** `documentation/plans/PLAN-record-navigation-standardization.md` (D1 backend neighbours, D2 unfiltered fallback, D3 circular wrap). Reversed by the user on 29 Aug: the pager is page-scoped and client-side, boundaries page, the neighbours code is deleted.
**Branch:** one branch per slice, `feat/apple-S<n>-<slug>`, from `main`.

---

## 1. What is being built, in one paragraph

The frontend's shared primitives are brought to one standard so every screen inherits it: a
round tinted pill for status and tags; rows that open their record from anywhere on the row;
one detail-page header (Back alone on the toolbar row; pager, gear, primary on the record
card); a prev/next pager that walks the page the user came from out of the React Query cache;
dialogs that are true lightboxes; underline tabs everywhere a form or detail view has tabs;
grids and tab strips that scroll on a phone instead of squeezing or overlapping. The
confirmation dialog is replaced by the product's own grace-window model, generalised from the
form-action engine: the click creates a server-side pending action, the button becomes a
countdown with Cancel, and the server commits when the window lapses. Tokens the app already
references (`--mono`, semantic colours, dark surfaces, type scale, motion, materials) are
defined once; the motion layer moves to springs; lint stops the mechanical classes from
regrowing.

## 2. Why now (evidence)

- 0 pressed states in `button.tsx`; every control answers on release (audit P1).
- `dialog.tsx:33` defaults `modal ?? false`: 289 of 290 dialogs have no focus trap or scroll lock.
- `--mono` is referenced by 254 files and defined nowhere; page titles inherit body colour.
- `data-grid.tsx:248` has no horizontal scroll container: Stock shows one column at 375, Categories squeezes six, Complaints rows cannot be opened on a phone.
- `tabs.tsx` has no scroller: Settings hides 7 of 10 tabs at 375, Product create overlaps five pills.
- 78 of 193 lists open on row click; 26 have a detail route and no click; Users and Contacts fetch their own 100-row list for a pager that ignores the list the user left.
- 152 `ghost` badges (dot + text, no fill) beside 403 `rounded-md` tinted ones: two status languages.
- 126 AlertDialog confirms + 84 `ConfirmDeleteDialog` importers + 9 native `confirm()` for actions that the form-action engine already handles with a grace window.

## 3. Standards (the design)

### 3.1 Pill (`components/ui/badge.tsx`)

- Base: `inline-flex items-center gap-1.5 rounded-full h-6 px-2.5 text-xs font-medium` (size `md`); `sm` is `h-5 px-2`. `lg` and `xs` removed unless a call site proves a need.
- `appearance`: `light` (default: tinted fill + matching text) and `outline`. `ghost` deleted; the 152 sites become `light`.
- New prop `status?: string`: renders the 6px dot and resolves `variant` through `getStatusBadgeVariant(status)` so the caller passes the raw status string. `BadgeDot` stays exported for the few non-status dots.
- `shape="circle"` unchanged (count badges).
- Migration is mechanical: `appearance="ghost"` -> drop; `<Badge variant={getStatusBadgeVariant(x)}><BadgeDot/>{x}</Badge>` -> `<Badge status={x}>{label}</Badge>`.

### 3.2 Row click (`components/ui/data-grid*.tsx`)

- New prop `rowHref?: (row: TData) => string`. The grid renders each body row as a real link target: `<tr>` gets `tabIndex=0`, `role="link"`, `onClick` -> `router.push(href)`, `onAuxClick` (middle) -> `window.open`, Enter/Space -> push. Cells that carry their own interactive control keep `stopPropagation` as today.
- The href appends the grid's list state: the grid already receives `table` (TanStack) so it reads `pagination`, `sorting`, `globalFilter`/search from `table.getState()` and serialises via `buildDetailSearch` (`lib/listNavQuery.ts`). Extra filters a list keeps outside TanStack are passed by the list through a second arg: `rowHref={(row) => detailHref(row.id, extraFilters)}`; S1 built the first mechanism only (the grid appends the list state to the `rowHref` result, and a caller's own query string rides along and wins); no `detailHref` helper was added. S3 may add one if the 39 detail pages need it.
- `onRowClick` stays for lightbox-editing lists. Neither prop -> no `cursor-pointer`, no `role`.

### 3.3 Detail header

- Toolbar row stays `Toolbar > ToolbarHeading (ToolbarTitle + Breadcrumb) + ToolbarActions (Back)`. `BackToList({ listPath, label })` reads `useSearchParams()` and appends the query string. Nothing else goes in `ToolbarActions` on a detail page.
- New `components/common/DetailActions.tsx`: `{ pager?: ListPagerProps; secondary?: MenuItem[]; onDelete?: DeferredAction; primary?: ReactNode }`. Renders `[ListPager] [gear DropdownMenu: secondary..., separator, Delete (destructive)] [primary]` in a `flex flex-wrap gap-2 justify-end` group that wraps under the identity at 375. Delete is rendered through S6's `DeferredActionMenuItem`; until S6 lands it opens the existing `ConfirmDeleteDialog` (expand-contract seam).
- One action set per entity (D15): `app/(protected)/<module>/<entity>/actions.tsx` exports `use<Entity>Actions(record): RecordAction[]` (`{ key, label, icon, permission, kind: 'secondary' | 'destructive', run | deferred }`). `DetailActions` renders it in the gear; a new `RowActionsMenu` (extends the existing `components/common/DetailActionsMenu.tsx`, 15 consumers) renders the same array as the list row's "..." cell. Permission checks happen once, in the definition. The 79 icon-button `actions` columns become `RowActionsMenu`; the primary action is the row click on the list and the primary button on the record. First case: Users (Impersonate, Send invitation link, Delete).
- Migration: the 34 record cards that already hold Edit/Delete/Nav swap to `DetailActions`; the 5 toolbar-pager pages (users, contacts, integration-logs, LoadingPlanView, SeriesDetailClient) move pager + gear + primary into their record card (Users' "Send invitation link" becomes a secondary item; Contacts' "Delete contact" moves to the gear).

### 3.4 Page-scoped pager (`hooks/useListPager.ts` + `components/common/ListPager.tsx`)

- Input: `{ listQueryKey: (params) => QueryKey, fetchPage: (params) => Promise<Page>, detailPath, currentId }`. It parses the URL with `parseDetailSearch`, reads `queryClient.getQueryData(listQueryKey(params))`; if absent (deep link / refresh) it `useQuery`s that page with the same key so the list and the pager share one cache entry.
- Position = `items.findIndex(id)`; counter `"${idx+1} / ${items.length}"`. Prev on idx 0 with page > 1 -> fetch page-1 and navigate to its last item; Next on the last idx with `page * limit < total` -> fetch page+1 and navigate to its first. Navigation pushes `${detailPath}/${id}?${buildDetailSearch(newParams)}` so the URL always names the page the record sits on. Disabled at absolute ends. Record not on the page -> render nothing.
- `RecordNavigation.tsx` shrinks to the presentational chevrons + counter (keep the file, drop the ids/list dual mode).
- Deleted in the same slice: `hooks/useRecordNeighbours.ts`, the 14 `useXxxNeighbours` wrappers, the 20 `*Navigation.tsx` components, backend `@router.get("/neighbours")` in the 14 route files, `compute_neighbours` in the shared service, their pytest and vitest files. Alembic untouched (no tables).

### 3.5 Deferred actions (grace window) - generalising `sla_form_actions`

- Backend keeps the existing table and engine (`app/models/sla.py` `FormAction` row, `form_action_registry`, `form_action_grace`, `form_action_dispatch`, sweeper) and widens the registry: `register(FormAction(key="product.delete", entity_type="product", execute=..., window="destructive"))`. `source_entity_type` already exists; `action_key` already exists. New keys follow `<entity>.<verb>`: `.delete`, `.archive`, `.unlink`, `.set_status`. A `FormAction` gains `window: Literal["destructive","reversible"]`; `form_action_grace` maps destructive -> `system_settings.deferred_delete_seconds` (default 10), reversible -> `deferred_action_seconds` (default 5), migration adds both columns to `system_settings` (and both manual dict builders per CLAUDE.md), and System Settings > General gets the two fields (D16) so the windows are tuned without a deploy.
- Generic routes in a new `app/api/v1/system/pending_actions.py`: `POST /pending-actions` (create; idempotent on `(entity_type, entity_id, action_key, status=pending)`), `POST /pending-actions/{id}/cancel`, `GET /pending-actions/current`. RBAC: the handler declares the permission slug it requires (`master_data.products.delete`); the route checks it before parking the row. The existing `/form-actions/*` routes stay for forms.
- Frontend: `hooks/useDeferredAction.ts` `{ start(actionKey, entity, payload), cancel(), state: idle|pending{commitAt, windowSeconds}|committing|done|failed }`, polling `current` on focus so a second tab shows the countdown. `components/common/DeferredActionButton.tsx` (button morphs into `TakeoverCountdown` + "Cancel"), `DeferredActionMenuItem.tsx` (gear item that starts the action and hands the countdown to the primary area), `deferredToast()` for list rows (sonner toast with the bar and Cancel; row dims via a `data-pending` attribute on the grid row). On commit: invalidate the list keys, navigate to the list with the query string if the record was deleted.
- Rollout: S6 = engine + primitives + Users, Products, Orders (record + list). S6b = the remaining `ConfirmDeleteDialog` importers and destructive `AlertDialog`s, one module per commit, then delete `ConfirmDeleteDialog`. **Delivered 41 of 69** (see S6-10); the component survives S6b because project-sales cannot move until `FormAction` can declare a record-level authorisation callback that the POST runs at the click. A slug alone is not enough there: `assert_can_edit_project` answers per project, and pushing that refusal to commit time would deliver it ten seconds after the button it belonged to has gone.

### 3.6 Lightbox (`dialog.tsx`, `alert-dialog.tsx`, `sheet.tsx`)

- `modal ?? true`; delete the `[data-ai-assistant-root]` branch of `guardOutsideInteraction` (Radix inerts the bubble). Shared overlay class `bg-black/50 backdrop-blur-md` + fade; `alert-dialog` and `sheet` content get `max-h-[90dvh] overflow-y-auto`; `SheetBody` gets `flex-1 min-h-0 overflow-y-auto`; `sheet.tsx` content gets `data-slot="sheet-content"`. Left/right sheets are already `inset-y-0 h-full` (a viewport cap) and scroll via `SheetBody`; `max-h-[90dvh]` applies to the `top`/`bottom` variants only (S1 as built). Utility sheets (`MyDownloadsDrawer`, `UploadActivityDrawer`, `notifications-sheet`) pass `overlay={false}`. `drawer.tsx` stays for S8 (vaul).

### 3.7 Tabs (`tabs.tsx`)

- Base list: `flex items-center shrink-0 min-w-0 max-w-full overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden` plus a right-edge mask (`[mask-image:linear-gradient(to_right,black_calc(100%-24px),transparent)]` when scrollable). Default `variant: 'line'` in both cva blocks and the context. S1 pinned every `<TabsList>` that had no variant (25 tags in 21 files, not 17: the inventory undercounted) with an explicit `variant="default"` so nothing migrated silently; S4 reconciles that list against its 19 migrations and removes the pin from each one it converts.

### 3.8 DataGrid on a phone

- `DataGridContainer` (`data-grid.tsx:248`) has zero call sites; every list renders `CardTable > ScrollArea > DataGridTable`, so S1 put the scroller (`DataGridScroller`) inside `DataGridTable`. `DataGridContainer` is dead code: S9 deletes it. Original intent, kept for reference: the wrapper gains `overflow-x-auto overscroll-x-contain` and the right-edge fade; table gets `min-w-max` when `table.getTotalSize() > containerWidth` (ResizeObserver, already needed for the fade). No per-list configuration. S1's automatic `columnPinning` of the first non-select column under `sm` was removed on 2026-08-30 at the user's call: the whole row scrolls as one. A list that pins a column deliberately still gets the pinned styles.
- `data-grid-list-toolbar.tsx`: `flex-wrap`; Quick filters / Group by stay reachable.

### 3.9 Wayfinding (`components/common/PageHeader.tsx`)

- `PageHeader({ title, eyebrow?, crumbs?, actions? })`: title at one scale; crumbs from `useMenu().getBreadcrumb(pathname)` unless `crumbs` overrides; last crumb is `BreadcrumbPage`; root crumb "Dashboards". GRN / SPO pages pass `eyebrow="GRN"` and `title="Goods Receipt Notes"`. Replaces `ToolbarTitle` + hand-rolled crumbs in 102 + 243 sites (mechanical, one module per commit).

### 3.10 Tokens, type, motion, materials (`css/config.reui.css`, `css/styles.css`, `app/layout.tsx`)

As specified in the audit report sections "Fix these first" 3, 4, 5, 7 and "Materials" systemic fixes: `--mono` and semantic pairs; dark ramp; `@theme` type scale + `--font-sans` (Inter via `variable: '--font-inter'`) + `font-optical-sizing`; motion tokens; material tokens + z-scale; preference block; `.material-edge`.

### 3.11 Motion (S8) and guardrails (S9)

- `lib/motion.ts` presets; `AnimatePresence` on Dialog/Sheet/Popover/DropdownMenu; origin anchoring; sidebar `transform`; `vaul` for the mobile nav (`header.tsx:90`) and bottom sheets; AI bubble materialise + pointer capture; row DnD sensors + `DragOverlay`; embla `duration`.
- ESLint rules (warn) + `text-[Npx]` ban; aria-labels; `role="content"` removed; skip link; ring on the 73 `outline-none` sites; `IssuedKeyDialog` Escape allowed.

## 4. Slices and order

Issues (jayson-odoo/sorento-crm): S1 #372, S2 #373, S3 #374, S4 #375, S5 #376, S6 #377, S6b #378, S7 #379, S8 #380, S9 #381.

| Slice | Branch | Contents | Phase 1 (mock) | Phase 2 (tests) |
|---|---|---|---|---|
| S1 | `feat/apple-S1-primitives` | 3.1, 3.2, 3.6, 3.7, 3.8 + pressed states, hit areas, grid defaults, toolbar wrap, sonner close | n/a (primitives) | vitest on each primitive; agent-browser at 375/1280 on Users, Products, Settings, Stock, Categories |
| S2 | `feat/apple-S2-tokens` | 3.10 | n/a | vitest on token resolution (computed style); browser shots light + `.dark` class |
| S3 | `feat/apple-S3-detail-header-pager` | 3.3 (incl. `recordActions` + `RowActionsMenu` on the 79 action columns), 3.4, neighbours deletion | `DetailActions` + `ListPager` against mocked cache | vitest for pager boundaries; pytest green after route deletion; browser run Orders, Users, Sales Orders |
| S4 | `feat/apple-S4-tabs-rows-mobile` | 19 tab migrations, 26 + lightbox lists row click, mobile one-offs, 35 raw tables | n/a | vitest for tabs inventory (no grid-cols TabsList), browser sweep of all 50 screens at 375 |
| S5 | `feat/apple-S5-wayfinding` | 3.9, labels, UUIDs, emptyAction | PageHeader | vitest for crumb derivation |
| S6 | `feat/apple-S6-deferred-actions` | 3.5 engine + primitives + Users/Products/Orders | button + toast against a mocked `/pending-actions` | pytest test-first: create/idempotent/cancel/sweeper/window/RBAC; vitest hook; browser run with a real 10s lapse |
| S6b | `feat/apple-S6b-deferred-sweep` | remaining importers, delete `ConfirmDeleteDialog`, 9 `confirm()` | n/a | vitest: no `ConfirmDeleteDialog` import remains |
| S7 | `feat/apple-S7-feedback` | mutation factory, debounced search, onTouched, loading.tsx | n/a | vitest for optimistic rollback |
| S8 | `feat/apple-S8-motion` | 3.11 motion | n/a | browser frame-by-frame review; vitest for reduced-motion branch |
| S9 | `feat/apple-S9-guardrails` | 3.11 guardrails | n/a | lint runs in CI |

One coder at a time (two-slot rule), each in its own worktree, each PR reviewed by `/code-review` before the next slice starts. S1 and S2 first; S3 depends on S1 (`rowHref`); S6 depends on S3 (`DetailActions` seam); S6b depends on S6; S4, S5, S7, S8, S9 depend only on S1/S2.

### 4.1 Where each slice comes from

S1, S2, S4, S7, S8, S9: the Apple-design audit (rounds 1-2). S3: the user's asks of 29 Aug (row click, Back placement, page-scoped pager, D15 action parity). S5: audit round 1 wayfinding, scoped by the grill (Q14, Q15). S6/S6b: the grill (Q13, Q23, Q24), not the audit; the audit had proposed Undo toasts, the user chose the grace-window model instead.

## 5. Testing seams (agreed before Phase 2)

- Primitives: vitest renders `Dialog`, `TabsList`, `DataGrid` with a 3000px table, `Badge status`, and asserts classes and ARIA; a jsdom `matchMedia` stub for `pointer: coarse` and `prefers-reduced-motion`.
- Pager: `useListPager` tested with a seeded QueryClient (page 1 and 2 cached) for the four boundary cases and the deep-link fetch.
- Deferred actions: pytest against Postgres (`tests/_pg_fixture.py`), seeding its own product/user/order chain; sweeper invoked directly with a frozen clock; RBAC denial per action key.
- Browser evidence: agent-browser runs recorded per slice under `documentation/plans/design-system/evidence/S<n>/`, sidebar navigation from `/`, 375 and 1280.

## 6. Not built (deferred to `documentation/backlogs/backlog.md`)

- Dark mode toggle (tokens only, D12).
- Card-per-row mobile grid layout (D10 chose scroll; the pin was tried and dropped).
- Soft-delete / restore endpoints (D7 uses the pending window, not post-commit restore).
- Deleting `drawer.tsx`/`vaul` (used by S8 instead).
- `Reports`, `Price Tags`, After-sales screens: not in this tenant's sidebar during the sweep; they inherit the primitives.

## 7. Risks

- Sticky header vs horizontal scroller (S1 open question): `overflow-x: auto` on the grid scroller makes it the scroll container, so `sticky top-0` on `<thead>` only sticks if the grid has a bounded height. Not a regression (call sites already wrapped in a `ScrollArea` with the same effect), but S1-07's sticky header is not observable until a list gives its grid a `max-h`. S4 decides per long list (Stock, Products, Orders) whether to bound the grid height; otherwise the default stays inert.
- `appearance="ghost"` is a deprecated alias of `light` since S1 (127 sites render as filled tints); S4 removes the alias after its badge sweep.
- Three existing test files were adapted in S1 because a surface behind an open dialog is now inert (`RevisionSnapshotDialog.test.tsx`, `SalesOrdersPanel.delete.test.tsx`, `SpoPlannerTable.test.tsx`); the SPO planner flow (open drill, close, Create SPO) is on the S1 browser checklist.

- `modal ?? true` changes 290 dialogs at once: the nested-dialog guard (`dialog.tsx:132-141`) may become dead; keep it until the attachment-type flow is browser-verified.
- Deleting 14 backend routes: MCP tools or n8n could reference `/neighbours`. Grep `sorento_crm_mcp/` and the n8n catalogue before deletion; none found in the frontend.
- Pill migration touches ~600 call sites; one module per commit so a wrong colour is bisectable.
- Deferred delete on entities with FK cascades: the handler runs the same service delete as today; no new cascade semantics.
