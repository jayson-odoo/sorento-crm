# Apple Alignment - Acceptance Criteria

**Slug:** `apple-alignment`
**Domain:** design-system (cross-cutting, every module)
**Source:** Fluid Interface Audit, 29 Aug 2026 (artifact `86a2cb9e`), rounds 1-3, plus the grill of 29 Aug.
**Supersedes:** `documentation/plans/PLAN-record-navigation-standardization.md` D1-D3 (backend neighbours, circular wrap). See S3.

---

## Journey

A staff user opens a list from the sidebar, on a laptop or a phone. Every row reads as one
thing: the status is a rounded tinted pill with a dot, the same shape and size on every list
and every detail page. They tap anywhere on a row and the record opens: its detail page if it
has one, otherwise its edit lightbox. The detail page arrives carrying the list's state in the
URL (page, limit, sort, filters, search). Its header row is title and breadcrumb on the left,
one "Back to [list]" on the right, nothing else on that line. The record card shows the
identity on the left and, on the right, a prev/next pager that walks the rows of the page they
were looking at ("3 / 50"), a gear holding the secondary actions with Delete last, and one
primary button. When they act on something that changes or removes a record, no dialog asks
them to confirm: the button becomes a countdown they can cancel, and the server commits the
action when the window lapses, even if they have closed the tab. Every popup they meet is a
lightbox that owns the screen; every form and detail view has the same underline tabs; on a
phone, wide grids scroll sideways as whole rows, and tab strips scroll
instead of overlapping. Nothing is asked of them that the screen already knew.

---

## Decisions (locked 29 Aug 2026)

| ID | Decision |
|----|----------|
| D1 | Scope is the whole audit, delivered as nine slices, one coder at a time, one PR each. |
| D2 | Pill: `rounded-full`, tinted fill + matching text, 24px tall; status pills carry a 6px dot; tags do not; `ghost` retired; count badges stay circles. Status colour from `getStatusBadgeVariant`. |
| D3 | Row click opens the record's primary view: detail route if one exists, else the edit lightbox. Log and sub-tables are not clickable and carry no pointer cursor. Whole row is the target, keyboard included. |
| D4 | Prev/next is page-scoped and client-side: it reuses the rows the list page has in the React Query cache, counter "n / pageSize", next on the last row fetches the following page. The 14 backend `/neighbours` endpoints, their wrappers, hook and tests are deleted. |
| D5 | The list hands its state to the detail in the URL via `buildDetailSearch`; DataGrid gains a `rowHref` prop that appends it. Back carries it back. |
| D6 | Detail header: toolbar = title + crumbs left, one Back right. Record card actions, left to right: pager, gear (secondary actions, separator, Delete in red last), one primary button. Wrap under the identity at 375. |
| D7 | Confirmation model: no confirm dialogs. Destructive and reversible actions are server-deferred pending actions (generalising `sla_form_actions`): 10s window for hard delete, 5s for reversible. Countdown on the button for the record on screen, in a toast for list rows. Escape does not cancel. Closing the tab still commits. `ConfirmDeleteDialog` retired. |
| D8 | Lightbox: dialogs modal by default, scrim 50% black + 8px blur shared by dialog, alert and sheet, height caps everywhere. Passive utility sheets get no scrim. |
| D9 | Tabs: `variant="line"` is the default and the list owns its horizontal scroller. 19 strips migrate to Users style (icon + label); 17 two-option segmented switches keep pills with an explicit `variant="default"`. |
| D10 | DataGrid on a phone: horizontal scroll container, right-edge fade. No per-list column choices. **Revised 2026-08-30:** the identifier column is NOT pinned. S1 pinned it; the user tried it and found a column that refuses to move with the rest weirder than losing sight of the name. Explicit `columnPinning` for a list that asks for it is untouched. |
| D11 | Wayfinding: one `PageHeader`; crumbs derived from `MENU_SIDEBAR` with an override prop; "Home" becomes "Dashboards"; sidebar keeps GRN / SPO, page titles expand them. |
| D12 | Typeface stays Inter, wired through `--font-sans` with a type scale that bakes tracking and leading per step. Dark tokens are defined; no dark toggle in this run. |
| D13 | Mobile nav drawer and bottom sheets move to `vaul`; desktop side sheets stay Radix. |
| D14 | Undo toasts only where no confirmation exists today; nothing that confirms today stops confirming until D7 replaces it. |
| D15 | One action set per entity, shown in two places: the list row's "..." menu and the record page's gear. Same items, same order, same permissions (Impersonate on a user is the first case: list-only today). The 79 icon-button action columns become a "..." menu. Primary (Edit/open) stays a button on the record page and is the row click on the list; there is no Edit item in the row menu (confirmed 29 Aug). Items that need the fetched record (workflow overrides, escalate, mark responded or resolved, a credential link the list payload omits) are outside the declared set and appear on the record only; everything else is identical on both surfaces (30 Aug). |
| D16 | Grace windows are configurable in System Settings > General (two fields: destructive seconds, reversible seconds), defaults 10 / 5. |

---

## S1 Primitives (components/ui only) [FE]

- **S1-01** Given any `<Dialog>` without an explicit `modal` prop, when it opens, then focus is trapped inside, the page behind is `aria-hidden` and does not scroll, Escape closes it, focus returns to the trigger on close. [FE][T]
- **S1-02** Given a dialog, alert dialog or sheet is open, then the overlay is `bg-black/50 backdrop-blur-md` and the blur fades in with the overlay. Under `prefers-reduced-transparency` the blur is off and the scrim is 72% black. [FE][T]
- **S1-03** Given an AlertDialog or a Sheet taller than the viewport at 375x812, then its body scrolls and its footer buttons are reachable. [FE][E2E]
- **S1-04** Given a `<TabsList>` with no `variant`, then it renders the `line` variant. Given more triggers than fit the width, then the list scrolls horizontally with no visible scrollbar and the page does not scroll sideways. [FE][T]
- **S1-05** Given a DataGrid whose columns exceed the container, then the grid scrolls horizontally inside its own container and a fade marks the right edge. The page body never scrolls sideways. Nothing is pinned automatically: at 375 the whole row scrolls as one (revised 2026-08-30, see D10). [FE][E2E]
- **S1-06** Given a DataGrid with `rowHref`, then every row is an anchor target: click, middle-click and Enter/Space open the href, and the href carries the grid's current page, limit, sort, filters and search via `buildDetailSearch`. Given neither `rowHref` nor `onRowClick`, then rows have no pointer cursor. [FE][T]
- **S1-07** Given any DataGrid, then `columnResizeMode` is `onChange`, the header is sticky by default, numerals are tabular, and the resize handle uses pointer capture. [FE][T]
- **S1-08** Given a `<Badge>`, then its shape is `rounded-full`, height 24px (`md`), tinted fill + matching text. Given `<Badge status>`, then a 6px dot precedes the label and colour comes from `getStatusBadgeVariant`. The `ghost` appearance no longer exists. Count badges (`shape="circle"`) render unchanged. [FE][T]
- **S1-09** Given any button, checkbox, switch, radio, toggle, tab trigger or slider thumb, when the pointer goes down, then a pressed state is visible before release (scale 0.97 or tint), and it is suppressed under `prefers-reduced-motion`. [FE][T]
- **S1-10** Given a coarse pointer, then every button, checkbox, switch and radio has a hit area of at least 44x44 CSS px without changing its rendered size. [FE][T]
- **S1-11** Given the list toolbar at 375, then its controls wrap and none is cut off past the viewport edge. [FE][E2E]
- **S1-12** Given the sonner Toaster, then every toast has a close button. [FE]

## S2 Tokens and CSS [FE]

- **S2-01** `--mono`, `--mono-foreground`, `--success`, `--info`, `--warning` (and their foregrounds) are defined in `:root` and `.dark`; `text-mono` renders darker than body text; toast success and error ink is coloured. [FE][T]
- **S2-02** In `.dark`, `--background`, `--card` and `--popover` are three distinct lightness steps, and the active tab is lighter than its track. [FE][T]
- **S2-03** `@theme` defines the type scale with per-step letter-spacing and line-height (2xl -0.02em/1.15, xl -0.015em/1.2, lg -0.01em/1.3, base 0/1.5, xs +0.01em, 2xs +0.02em), `--font-sans` resolves to Inter, `body` has `font-optical-sizing: auto`. `CardTitle` and both dialog titles use `leading-tight tracking-normal`. [FE][T]
- **S2-04** `css/styles.css` carries `prefers-reduced-motion` (overlay slides and zooms become 150ms fades, pulse and bounce stop, spinners keep spinning), `prefers-reduced-transparency` and `prefers-contrast: more` blocks. [FE][T]
- **S2-05** Material tokens (`--material-thin/regular/thick`, `--scrim`, `--elev-1/3`) and a named z-scale exist; header and sidebar use them; the impersonation banner offsets the header instead of covering it; no ad-hoc `z-[N]` remains in the shell. [FE]
- **S2-06** Motion tokens (`--ease-standard`, `--duration-fast/base/slow`) exist and every `components/ui` transition uses them; sheet open and close durations are equal. [FE]
- **S2-07** Card shadow tint renders (`shadow-black/5`). [FE]

## S3 Detail header and page-scoped pager [FE][BE]

- **S3-01** Given any detail page, then the toolbar row shows title + breadcrumb left and exactly one "Back to [list]" button right, and the Back href carries the list query string the page arrived with. [FE][E2E]
- **S3-02** Given a detail page's record card, then its actions read left to right: pager, gear, primary. The gear lists the secondary actions, then a separator, then Delete in destructive red, last. At 375 the group wraps under the identity. The five pages that placed the pager in the toolbar (users, contacts, integration-logs, LoadingPlanView, SeriesDetailClient) match. [FE][E2E]
- **S3-03** Given a detail opened from a list page, then the pager counter reads "n / pageSize" where n is the row's position on that page, computed from the list's cached query (same query key), with no additional request. [FE][T]
- **S3-04** Given the last row of the page and Next, then the following page is fetched once and the pager continues at "1 / pageSize" of it; Previous on the first row of page 2 loads page 1 and lands on its last row. On page 1 row 1, Previous is disabled; on the last page's last row, Next is disabled. [FE][T]
- **S3-05** Given a deep link or a refresh, then the pager fetches the page named in the URL; if the record is not on that page the pager hides and Back still works. [FE][T]
- **S3-07** Given an entity with a `recordActions` definition, then its list rows show a "..." menu and its record page shows a gear with the same items in the same order, each item hidden when the user lacks its permission; the Users entity lists Impersonate, Send invitation link, Delete in both places. The 79 icon-button action columns are replaced by the "..." menu. [FE][T]
- **S3-06** All 39 detail pages use the shared `DetailActions` + `useListPager`; the 20 `*Navigation.tsx` files, `useRecordNeighbours`, the 14 `useXxxNeighbours` wrappers, the 14 backend `/neighbours` routes, `compute_neighbours` and their tests are deleted; `pytest` and `vitest` are green after the deletion. [FE][BE][T]

## S4 Tabs migration, row click, mobile one-offs [FE]

- **S4-01** The 19 strips in the inventory render the Users style (line, icon + label); the **14** keepers carry `variant="default"`; no `grid grid-cols-N` TabsList remains under app/ or components/. [FE][T]
  Count corrected against the tree on 30 Aug: S1 pinned 25 strips, 11 of which are among the 19 migrated, leaving 14 keepers, not the 17 the audit estimated.
- **S4-02** Product create, Settings (10 tabs), Project detail (11 tabs), Sales Order detail and Workflow builder show every tab label in full at 375 by scrolling the strip. [FE][E2E]
- **S4-03** The lists with a detail route and no row click gain `rowHref`; lists whose record is edited in a lightbox open that lightbox on row click; log and sub-tables have no pointer cursor. [FE][E2E]
  Reconciled against the tree on 30 Aug, because the audit's counts predated S3: S3 wired 30 lists, leaving **Campaigns** and **Units of Measure** as the only top-level lists with a detail route and no row click (both now `rowHref`). The lightbox set is **Brands** and **Contact Access Agents** (both tables). UOM was listed as a lightbox list in the audit and is not one: it has no edit dialog, it has `units-of-measure/[id]`, so D3's first clause applies. **SPO Allocations** was already openable - it hand-rolls its table body and its `<tr>` carries the click, so it passes neither prop and is correct as it stands.
- **S4-04** At 375: Product Categories shows the full Name and keeps it pinned while the rest scrolls; Product Specifications' out-of-date banner wraps normally; Ticket numbers do not break mid-string; Product detail Pricing Summary values never touch; the **28** unwrapped raw tables scroll inside their own container; the login card is centred at 1280; the dashboard has a page title; task cards wrap instead of truncating the identifier; the two floating buttons on Ticket detail do not overlap; the AI Usage and Product Specifications toolbars wrap so neither page scrolls sideways. [FE][E2E]
  Count corrected against the tree on 30 Aug: 28, not the audit's 35. The first scan's regex missed a `<table` whose attributes Prettier had broken onto the next line, so three of the 28 were found late. Two of the 28 needed the OPPOSITE of a wrapper: ProductPerspectiveGrid's totals row must share the grid's scroller (`DataGridTable belowTable`) because `table.getTotalSize()` sizes it, and CategoryTree's scroller is its caller's. Three more had to have the scroller I gave them REMOVED: nested inside an existing vertical scroller, it broke their sticky headers.

## S5 Wayfinding [FE]

- **S5-01** `PageHeader` renders every page title at one size from one component; the 102 hand-rolled `<h1>` are gone. [FE][T]
  Count corrected against the tree on 30 Aug: the sweep covers `app/(protected)` and `components`, and those two roots held **66** hand-rolled `<h1>` across 65 files, not the audit's 102 - that figure counted the whole `app/` tree, most of which is not ours to sweep. All 66 are gone. Three `<h1>` remain inside the scanned roots and are exempt in `PageHeader.inventory.test.ts`, each with its reason in the file: `PageHeader` itself, the headless print catalogue (`CatalogueRenderer`), and the i18n scratch page.
  Deliberately excluded, and unchanged by this slice: **`app/(auth)` and `app/(public)`** (22 `<h1>` across 15 files - the login card, the portal and the token-scoped views render outside the sidebar's world, so there is no menu chain to derive a trail from); the **10 Metronic demo layout toolbars** under `app/components/layouts/demo1..10` plus `app/components/partials/common/toolbar.tsx` (vendor shell code no page of ours renders); **`app/components/common/AccessDenied.tsx`** (the permission guard's refusal, rendered INSTEAD of a page, so it has no trail to sit under - `app/components/common` was added to the scan's roots on 30 Aug and this file exempted with that reason, rather than being invisible to it); and the **52 Metronic demo pages under `(protected)`** (`account/*`, `auth/*`, `network/*`, `store-admin/*`, `store-client/*`) which still render `<ToolbarPageTitle />`. The test bans `<ToolbarTitle>`, which is gone from all 196 of our own files that carried it.
- **S5-02** Breadcrumbs are derived from `MENU_SIDEBAR` (override prop for nested details); the last crumb is the only `aria-current="page"`; the first crumb reads "Dashboards"; crumb wording equals sidebar wording. Desktop shows the trail; on mobile crumbs are links. [FE][T]
  Count verified against the tree on 30 Aug: 244 is right, and all 244 were inside the swept roots, so none survives.
  What the count did not say: **42 routes under `app/(protected)` prefix-match no `MENU_SIDEBAR` entry**, so a derived trail collapses to "Dashboards > title" and the parent link the sweep deleted does not come back on its own. The 18 that are records or forms BELOW a list now pass `crumbs` explicitly - the eleven screens under `/project-sales/[projectId]` through one shared `projectCrumbs` helper, plus workflow submissions, tickets, contacts and attachments. The rest are either redirects and demo pages, or top-level lists the sidebar genuinely does not name (Attachments, Tickets, Internal Users, Workflow submissions, Smart Linkage), which stay a two-crumb trail because there is no parent to link to.
  A page whose `title` is a node rather than a string names its own crumb with **`crumbTitle`**; without it the trail ended on the sidebar entry above the page, which then read as `aria-current="page"` and stopped being a link.
- **S5-03** GRN and SPO pages show the expansion in the title with the abbreviation as eyebrow; the sidebar is unchanged. [FE]
- **S5-04** Primary buttons in forms and dialogs read verb + noun ("Save SLA config", "Submit request"); no bare "Submit" / "OK" remains. [FE]
- **S5-05** No UUID fragment renders as a title or inside a confirmation. [FE][T]
- **S5-06** DataGrid empty state carries an `emptyAction`; lists with an Add button show it there. [FE]
  Exception recorded on 30 Aug: **9 listings keep a toolbar `primaryAction` and no `emptyAction`**, because what their toolbar offers is not a next step an empty list can repeat. Six wrap the trigger in a `Dialog` or a `DropdownMenu` whose menu is the offer, not the button (Workflow Definitions, Workflow Submissions, SCM Sales Orders, Project Order Inquiries, and the two attachment browsers' Upload); `ProformaInvoicesView` passes a render function that the toolbar calls with its own `openExport`, which the empty row has nothing to pass; `chat-history`'s primary is Export, which an empty list cannot do; and `PlanLinesGrid`'s primary is the plan-wide Confirm, which is not an Add. Wiring any of them would mean re-hosting a trigger outside the component that owns its state, for a button that opens the same dialog one row higher up.

## S6 Deferred actions (grace window) [BE][FE]

- **S6-01** `POST /api/v1/pending-actions` with `{action_key, entity_type, entity_id, payload}` returns `202 {id, commit_at, window_seconds}` and applies nothing; a second POST for the same entity + action while one is pending returns the existing one. [BE][T]
- **S6-02** `POST /api/v1/pending-actions/{id}/cancel` by the requester before `commit_at` deletes the pending row and returns 200; after commit it returns 409. [BE][T]
- **S6-03** The sweeper commits pending rows past `commit_at` by calling the registered handler for `action_key`; a handler failure marks the row `failed` with `error_text` and leaves the entity untouched. [BE][T]
- **S6-04** Windows: 10s for `*.delete`, 5s for everything else, both read from system settings with those defaults; System Settings > General shows the two fields, saving them changes the next pending action's window, and both reach the FE through both manual dict builders. [BE][FE][T]
- **S6-05** `GET /api/v1/pending-actions/current?entity_type&entity_id` returns the pending action for a record so a second browser shows the same countdown. [BE][T]
- **S6-06** Given a record page's Delete (in the gear), when clicked, then the primary area shows "Deleting in 10s" with a draining bar and a Cancel; Cancel restores the button; when the window lapses the record is gone and the page returns to the list with a toast. No dialog opens. [FE][E2E]
- **S6-07** Given a list row action (delete, archive, unlink), then a toast shows the countdown with Cancel and the row stays visible, dimmed, until commit. [FE][E2E]
- **S6-08** Escape does not cancel a pending action. Closing the tab during the window still commits (verified by API state). [FE][BE][T]
- **S6-09** Users, Products and Orders (record and list) run on the deferred model; `ConfirmDeleteDialog` is not imported by them; the 9 native `confirm()` calls are gone. [FE][E2E]
- **S6-10** (S6b) Every remaining `ConfirmDeleteDialog` and destructive `AlertDialog` importer is migrated; `ConfirmDeleteDialog` is deleted. [FE][T]
  Reconciled against the tree on 30 Aug, after the sweep. **41 of the 69 importers are migrated and 28 remain**, in four groups, and `ConfirmDeleteDialog` therefore still exists. Each group has a reason recorded in the file that keeps it, and the first group is the only one that is a scope split rather than a judgement:
  - **22 project-sales files: a separate slice, not a judgement.** Every per-project route authorises by RECORD, not by a slug: `assert_can_edit_project(db, project, user_id, slugs)` behind `_editable_project` / `_project_for_edit` / `_version_for_edit` / `assert_can_edit_lead`. A `FormAction` declares ONE static slug and `/pending-actions` enforces exactly that slug at the click, so parking a project-sales delete would either check the wrong grant or push the record-level refusal to commit time - ten seconds later, with no button left to report it on. Migrating the module needs `FormAction` to be able to declare an authorisation callback the POST runs, which is a change to the S6 engine rather than a line-each addition. **That is the named trigger for the follow-up slice.** The module's six config surfaces (project types, project templates, checklist items, series, price floors, quotation templates) DO use a static slug and could move now; they are held back with the rest so a reader does not meet a dialog on one project-sales screen and a countdown on the next.
  - **3 bulk / selection dialogs KEPT** (`ProductBulkDeleteDialog`, `OrderBulkDeleteDialog`, the certificates and tickets bulk deletes, SCM's Reset planning). `/pending-actions` holds one pending action per record and the countdown is a countdown for ONE record: it names what is going, it dims that row, and Cancel withdraws that action. A selection of forty has none of those. Select-then-Delete-selected is also already the deliberate two-step gesture the grace window exists to give a one-click action, and Reset planning additionally collects an answer ("also rewind the book") that a countdown has nowhere to put.
  - **`PeopleGrid` KEPT.** Its only removal surface is the TOKEN-SCOPED intake screen under `app/(auth)/onboarding`, where there is no authenticated principal for `/pending-actions` to check a slug against or attribute the action to. Same reason the portal ticket-draft `confirm()` is out of scope.
  - **`ReportViewsMenu` KEPT.** A view's grant is computed from the REPORT KEY at request time (`_authorised(db, user, key)`); a `FormAction` declares one static slug, so parking it would enforce the wrong grant or none. A saved view is also the reader's own and is one click to re-create from the config already on screen.
  Beyond the dialogs, three surfaces were found to be DRAFT state rather than server state and now ask nothing at all, because there is nothing parked to take back until Save: a product set's members, the page editor's blocks and section artwork, and a packing list's lines.
  Of the nine native `confirm()` calls, **eight are gone**; the ninth is the token-scoped portal ticket draft, excluded for the same reason as `PeopleGrid`. A notification's own delete is now immediate rather than deferred: it sits beside a Clear that has never prompted, so a countdown would be the heaviest gesture in the panel guarding its lightest action.

Added 2026-08-30 from the user's run on the built S6 (the window works; what happens around it did not):

- **S6-11** Given an action started from any surface, when the user navigates away before the window lapses, then the commit is still followed through: the tab asks `current` once at `commit_at` plus a grace with nothing mounted, refetches the action's lists and un-dims the row, so a list revisited later never serves a record that has already been deleted. A tab that was asleep does the same reconciliation when it next comes forward. [FE][T]
- **S6-12** An outcome is announced only while it still answers a click: a success within 10s of `ended_at`, a failure within 60s, and each outcome id at most once however many surfaces observe it. A record page opened minutes after its own commit shows the fresh record and says nothing. [FE][T]
- **S6-13** Given a link to a record this tab watched a delete commit on, when it is opened and the read 404s, then the page returns to its list with one quiet "Already deleted" and no error toast from any of the record's reads. A URL that was simply wrong keeps today's not-found page. [FE][T]

## S7 Feedback [FE]

- **S7-01** A shared `useEntityMutation` factory gives optimistic updates with rollback to boolean and status toggles in expanded rows; the toggle flips before the request resolves. [FE][T]
- **S7-02** Search inputs use one `useDebouncedSearch` (200ms) and show a settling indicator; the four mock-latency constants and the `lookupSetService` sleep are gone. [FE][T]
- **S7-03** Forms validate `onTouched`; the eight `setTimeout(form.reset)` are replaced by `defaultValues` / `values`. [FE][T]
- **S7-04** The ten busiest list routes have `loading.tsx` skeletons; `LayoutLoadingFallback` keeps the shell and skeletons only the content pane. [FE][E2E]
- **S7-05** Copy-to-clipboard actions show the inline checkmark only, no toast. [FE]

## S8 Motion [FE]

- **S8-01** Dialog, Sheet, Popover and DropdownMenu animate with the shared critically damped spring from `lib/motion.ts`; re-opening mid-close continues from the current value (no jump). [FE][T]
- **S8-02** Popover, dropdown and tooltip scale from the trigger (`origin-(--radix-popper-content-transform-origin)`). [FE]
- **S8-03** ~~The sidebar collapse animates `transform` only; wrapper and header do not transition layout properties~~ - dropped 31 Aug 2026: the `scaleX` + counter-scaled `.sidebar-rail` trick distorted both end states (squished icons, content overlapping the page past the collapsed rail) once its clip had to move off `.sidebar` for the toggle-button fix, and a second element (the toggle itself) needed position tracking without shape distortion, which the same transform could not give both at once. The collapse animates `width` again (wrapper/header transition `padding-inline-start`/`inset-inline-start` in lockstep, as before S8); `layout-initialized` is kept, set on the next frame via `requestAnimationFrame` rather than the old 1s timeout. [FE]
- **S8-04** The mobile nav drawer is a `vaul` drawer: it tracks the finger, dismisses on swipe with velocity, and is inert to input during no phase. [FE][E2E]
- **S8-05** The AI bubble panel materialises (scale + blur + opacity) from the bottom-right and resizes with pointer capture, touch included. [FE]
- **S8-06** Row drag-and-drop has an activation distance and a drop animation. [FE]

## S9 Guardrails [FE]

- **S9-01** ESLint warns on `jsx-a11y/click-events-have-key-events`, `no-static-element-interactions`, `control-has-associated-label`, and errors on `text-[Npx]` in className strings (demo layouts exempt). [FE][T]
- **S9-02** The 306 unlabelled icon buttons have an `aria-label`; `role="content"` is gone and a skip link reaches `#main`; `IssuedKeyDialog` no longer traps the keyboard; the 73 `outline-none` sites without a ring have one. [FE][T]
- **S9-03** `PR-CHECKLIST.md` lists: pill via `Badge status`, rows via `rowHref`, no confirm dialogs, PageHeader, line tabs, icon-button label. [FE]

---

## Definition of Done (per slice)

1. Every AC in the slice verified: `[T]` by a test asserting the AC id, `[E2E]` by a recorded agent-browser run at 375 AND 1280 navigating from `/` by sidebar clicks.
2. No new Playwright spec. `pytest` (Postgres) and `vitest` green.
3. `/code-review` findings resolved; PR body links this file and the plan and names any AC deliberately left out and why.
