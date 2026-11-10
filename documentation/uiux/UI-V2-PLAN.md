# UI v2: the program

Status: revision 2 (with discovery findings), proposed, awaiting owner review (lane UI-V2-PLAN, research and design only, no app code).

| Rev | Date | Change |
| --- | --- | --- |
| 1 | 10 Nov 2026 | First plan |
| 2 | 11 Nov 2026 | Reworked after the owner's D1-D5 answers (about 00:00) and the discovery round (`UI-V2-DISCOVERY.md`, owner about 00:10) |

**Companion files:**
- `UI-V2-DISCOVERY.md`: findings, evidence, journeys, references.
- `UI-V2-SCREEN-INVENTORY.md`: all 469 protected pages by archetype and area.
- `ui-v2-mocks/index.html`: before/after mocks, theme picker, phone.

The playbook gap audit is `documentation/uiux/playbook-uiux-audit.md` (PR #2322, cited `AUDIT`).

**Paths:** frontend paths are relative to `sorento_crm_frontend/` unless they start with `documentation/` or
`sorento_crm_backend/`.

## 0. The owner's answers this revision is built on

| # | Owner (11 Nov, gist) | What it means for v2 |
| --- | --- | --- |
| D1 | "keep today's blue, Sorento blue. The theme or the brand should be customizable and selectable, pickable." | Blue stays the default. v2 gets a theme system: selectable presets, a custom brand colour, light and dark, all driven by tokens (section 5) |
| D2 | Dark mode now, and "check properly in each phase, because this UI I want to do it properly" | Every phase's exit criteria include a dark-mode pass on every screen it touches (section 11) |
| D3 | "row height, what's the issue? Isn't it now quite good?" | Density unchanged: 44 px rows, 14 px text, 40 px header (measured, `UI-V2-DISCOVERY.md` 2.2). No density option |
| D4 | "for the phone, we should follow the playbook" | The phone follows the Foundryx playbook: bottom bar, floating main action, bottom selection and filter bars, and its list layout. Desktop keeps one line per row (section 8) |
| D5 | "a new version rollout. The user can go back ... previous version and new version. But I need it to be very good before I even release to live. So this one should be a very long and detailed thing." | v2 is a complete parallel version behind a per-user version switch (section 6). Nothing reaches staff until every phase has passed its exit criteria and the owner has used v2 as their daily UI (sections 10, 12) |
| - | Discovery round: "need more thinking, more exploring, more investigating before we make the coding" | The program starts with evidence (telemetry, fixtures, capture tooling) and owner-only use, and is long by design |

## 1. Goals, non-goals, release bar

**Goals**
1. **One coherent UI.** Every screen is one of six archetypes, built from one set of components, so a user who knows
   one record knows them all.
2. **Less to read and fewer clicks.** Remove what the journeys show is in the way: two primaries at hand-offs, next
   steps hidden in gears, 10-tab records, stacked dialogs, queue-then-collect exports (`UI-V2-DISCOVERY.md` section 4).
3. **The owner's rules enforced by code and review,** not by memory.
4. **A brand-able theme,** light and dark, that stays accessible whatever colour is picked.
5. **A phone experience that follows the playbook.**
6. **A zero-risk path:** v1 untouched and one click away until v1 is retired.

**Non-goals**
- No backend redesign. v2 reuses the same hooks, services and endpoints; backend work is limited to:
  - sort keys where a column cannot sort
  - "select all N" bulk endpoints
  - the version and theme fields
  - page-view telemetry
- No new features hidden inside the redesign. A screen does what it does today; journey fixes change layout and
  wording, never business rules. A business-rule change goes through its own lane.
- No density change, no new fonts, no hover effects or decorative motion (`AUDIT` Q4 stands).

**Release bar** (all of these, before any non-owner user sees v2):
- Every non-demo screen has a v2 implementation (387 pages = 469 minus 82 demo; `UI-V2-SCREEN-INVENTORY.md`).
- Every screen has passed its archetype checklist (section 7) in light AND dark, at 1280 AND 375.
- The visual, accessibility and performance gates (section 11) are green.
- The owner has used v2 as their daily UI for at least two weeks with no open "v2 worse than v1" item.

## 2. Owner rules (binding; win over the playbook and this plan)

| # | Rule | Source | Enforced by (phase 0) |
| --- | --- | --- | --- |
| R1 | Every date dd/mm/yyyy through one formatter | `PLAN-date-format-unify-04nov.md:6` | `lib/format/date.ts`; ESLint ban on date-fns `format` and `toLocale*String` in feature code |
| R2 | Desktop: standard DataGrid, one line per row (+N pill for overflow) | `sales-targets-opportunities-26sep-acceptance-criteria.md:68` | `DataGridTable` renders cells `truncate` with no wrap; inventory test for multi-line cells |
| R3 | Every column sortable server-side | `PLAN-portal-p4-requests-28oct.md:61` | Inventory test: `enableSorting: false` allowlist that only shrinks (521 today) |
| R4 | Every dropdown filter multi-select | same | `FilterChip` accepts only multi; inventory test for single-select in list toolbars (34 files today) |
| R5 | Grid selection like Odoo: shift/drag ranges, "Select all N" | `PLAN-grid-drag-select.md:7-8` | `data-grid-range-select.ts` (exists) + select-all-N (v2) |
| R6 | Right-click row menus, no row icons | crew memory, owner | `DataGridRowMenu`; replaces D15's "..." column (`DESIGN-LANGUAGE.md:186`) |
| R7 | Minimal UI; dialog or lightbox over side panels; no bloat | `CARD-project-party-roles-10nov.md:178`, commit `03be747b` | Inventory test for `SheetContent` (44 files); exact scope is open question Q2 |
| R8 | Record header like OI: number + badge inline, one subtitle, actions right | owner | `RecordHeader` (v2) |
| R9 | CRM forms = portal forms (same component) | owner | `components/v2/forms/` shared by portal and CRM |
| R10 | History is a standard tab on every record | `PLAN-standard-history-10nov.md:11-12` | `HistoryTab`; checklist item D-8 |
| R11 | One image pipeline | owner | `AttachmentImage` + `AttachmentPreviewModal`; inventory test for raw attachment `<img>` |
| R12 | Brand colour selectable; Sorento blue default (D1) | owner 11 Nov | Theme system (section 5) |
| R13 | Reuse the same component; no second implementation | `PLAN-standard-history-10nov.md:5-6` | Section 9 replacement map; reviewer checklist |
| R14 | Plain words for errors; nothing stuck | `NEVER-STUCK-UI.md:4`, `PLAN-po-schedule-redesign-24sep.md:108` | `StateView`; never-stuck smoke |

Phase 0 writes R1-R14 into `documentation/reference/DESIGN-LANGUAGE.md` and `PR-CHECKLIST.md`, so a reviewer can
hold a PR to them. Today 9 of them are not written anywhere a reviewer reads (`UI-V2-DISCOVERY.md` 3.2).

## 3. Principles

1. **Subtract first.** The owner's recurring complaint is complexity (about 23 recorded sources). A v2 screen shows
   fewer elements than its v1 screen unless it adds a missing state.
2. **One way per idea.** One component per concept (section 9). A second implementation is a review defect.
3. **The next step is the primary.** The step the record's state is waiting on is the one filled button. If the
   viewer cannot take it, a status line says who it waits on, with no button.
4. **Data first.** The first record row sits as high as the shell allows; summaries are chips, not tiles.
5. **Tokens or nothing.** Feature code never names a palette colour or hex (canvas and print artwork exempt).
6. **Same layout everywhere.** View and edit share tabs and order. A list behaves the same on every screen.
7. **Evidence before ordering.** Waves are ordered by measured use (section 4.3), not by guesses.
8. **Simplest thing that works** (`PRINCIPLES.md`). Every mechanism in this plan names the problem it solves today.

## 4. Scope: the screens

### 4.1 Inventory

The full list is in `UI-V2-SCREEN-INVENTORY.md`. Summary (first-pass archetype, corrected as screens are opened):

| Archetype | Pages | Share |
| --- | --- | --- |
| List | 177 | 46% of non-demo |
| Detail (+ 23 sub-pages under a record) | 109 | 28% |
| Form (create/edit pages; most creates are dialogs and are not pages) | 55 | 14% |
| Settings | 17 | 4% |
| Dashboard | 14 | 4% |
| Wizard | 9 | 2% |
| Redirect | 6 | - |
| Metronic demo (retire, not migrate) | 82 | - |
| **To build in v2** | **387** | |

| Area | Pages | Area | Pages |
| --- | --- | --- | --- |
| project-sales | 54 (4 redirect) | user-management | 43 (14 settings) |
| system-management | 49 | procurement-management | 40 |
| master-data-management | 36 | dealer-kit | 20 |
| scm | 18 (2 redirect) | order-management | 15 |
| sales | 15 | sla-management | 14 |
| inventory-management | 13 | my-requests | 13 |
| marketing-management | 10 | complaint-management | 8 |
| resource-management | 7 | workflow-forms-management | 7 |
| forms-management, ideas, integration-management | 5 each | auth, ticket-management | 3 each |
| finance | 2 | home, town | 1 each |

The portal (`app/(auth)/portal`) is in scope for forms only (R9: the CRM and the portal share one form component).
Its own shell is out of scope for v2 and gets its own plan after phase 7.

### 4.2 Waves by area

Each area wave migrates every page in the area at once, so a user never meets v1 and v2 screens side by side
inside one module. The order below is provisional and is re-ordered on telemetry at the end of phase 0 (4.3).

| Wave | Areas | Pages | Why this order |
| --- | --- | --- | --- |
| A | project-sales (OI, projects, quotations, SO, stock debt) | 50 | Most commits in the last 120 days (332 + 316); four of nine journeys (J1-J5) |
| B | scm + procurement-management | 56 | Reorder (209 commits), PO/SPO/GRN, J7-J8 |
| C | dealer-kit + marketing-management + portal forms | 30 | Price tags (J6), CRM = portal forms |
| D | master-data-management + inventory-management | 49 | Product master (212 commits), J9 |
| E | order-management, sales, my-requests, complaint, sla, ticket | 68 | Remaining staff modules |
| F | system-management, user-management, integration, workflow, forms, resources, ideas, finance, home, town, auth | 134 | Admin and low-traffic screens |

### 4.3 Evidence before ordering

Today the app records no page views (`UI-V2-DISCOVERY.md` 3.3). Phase 0 adds one minimal record:
- **Table:** `ui_page_views`, with columns `user_id`, `route` (pattern, ids replaced), `ui_version`,
  `viewport` (phone/tablet/desktop), `ms_to_first_data`, `created_at`.
- **Sending:** one beacon per route change, batched.
- **Retention:** 90 days.

It answers three questions:
- Which screens to do first.
- How many staff use a phone (the D4 effort question).
- Whether v2 is faster than v1 (the performance gate).

The audit log and session user-agent data that exist today cover only writes and devices (3.3), so they are used
alongside it, not instead of it.

## 5. Theme system (D1)

### 5.1 What exists

- Tokens alias the Tailwind palette in `css/config.reui.css` (`--primary: var(--color-blue-500)` at `:11`, dark at `:126-133`).
- Light/dark/system comes from `next-themes`, stored only in the browser's localStorage (`providers/theme-provider.tsx`,
  `storageKey="nextjs-theme"`), so a user's choice does not follow them to another device.
- There is no brand setting.
- **AA failure found:** the filled primary `blue-500` (`#3b82f6`) with white text measures 3.7:1, below WCAG AA (4.5:1)
  for 14 px text.

### 5.2 Token model

There are three layers, and only the last is used by components:

1. **Brand input:** one colour, plus a mode (light, dark, system).
2. **Generated ramp:** `--brand-50 ... --brand-950`, 11 steps, generated in OKLCH from the input's hue and chroma.
   The steps use fixed lightness targets per mode, as Linear does in LCH (`UI-V2-DISCOVERY.md` 5).
3. **Semantic tokens** (what components use):
   - `--primary`, `--primary-hover`, `--primary-foreground`, `--primary-soft`
   - `--ring`, `--link`, `--selection`, `--nav-active`, `--chart-1`.

**Fixed tokens** (neutrals, success, warning, info, danger, borders, materials) do not move with the brand, so status
colours mean the same thing under every theme.

| Semantic | Light picks | Dark picks |
| --- | --- | --- |
| `--primary` (filled button, link, sort arrow, focus ring) | the first step from 600 down whose contrast with white is >= 4.5:1 | the first step from 400 up whose contrast with `--background` is >= 4.5:1, with `--primary-foreground` = brand-950 |
| `--primary-hover` | one step darker | one step lighter |
| `--primary-soft` (selected row, active nav, active chip) | brand-50 | brand-950 at 60% |
| `--ring` | `--primary` | `--primary` |

The generator **guarantees AA**: if no step clears 4.5:1 with white (a very light brand such as yellow), the
foreground flips to brand-950 ink. The theme panel shows the measured ratio either way, so a custom colour can never
produce an unreadable button. `css/design-tokens.test.ts` asserts every preset in both modes.

### 5.3 Presets

| Preset | Input | Note |
| --- | --- | --- |
| **Sorento Blue (default)** | hue of `#3b82f6` | Same hue as today; the filled button uses the AA step (`#2563eb`-equivalent, 5.2:1). Exact `#3b82f6` kept only if the owner rejects that (open question Q1) |
| Sorento Red | `#b44d2e` | The dealer-kit brand swatch (`components/common/ColorPicker.tsx:30`) |
| Teal | `#0f766e` | |
| Graphite | `#3f3f46` | Monochrome; the generator picks the AA grey |
| Indigo | `#4f46e5` | |
| Custom | any hex, or picked | Generated and guarded as above |

Presets are data (a list in `lib/theme/presets.ts`). A sixth preset is one line, not a release.

### 5.4 Who picks, and where it is stored

Proposed, pending decision Q3:
- **Company brand:** an admin picks it in Settings > Appearance. It is stored as `system_settings.theme`
  (`{ preset, custom_hex }`) and applies to every user of that company.
- **User:** each user picks light/dark/system in the avatar menu. It is stored as `users.theme_mode` and follows them
  to any device, replacing the localStorage-only `next-themes` key.
- **Not in scope:** a per-user brand override. That stays out until someone asks (simplest thing).
- **Applying it:** `GET /me` returns `theme_mode` and the company theme. The protected layout already waits for the
  session before drawing the shell (`app/(protected)/layout.tsx`, `ScreenLoader`), so the CSS variables are set on
  `<html>` before the first v2 paint. There is no flash.
- **Before sign-in:** the sign-in page uses the default preset.
- **Picker UI:**
  - A Settings > Appearance page with preset swatches, a custom colour input with a live contrast readout, and a
    preview card (a mock row, a badge, a button in both modes).
  - "Reset to Sorento Blue".
  - The mocks include a working demo (`ui-v2-mocks/index.html`, "Theme" panel).

### 5.5 What the theme does not touch

- Status tones.
- Danger.
- Neutrals.
- Chart status colours (only `--chart-1` follows the brand).
- Print and PDF artwork (catalogues, tag sheets, quotation PDFs): those carry their own document theme
  (`email_theme`, dealer-kit templates) and are out of scope.

## 6. Version switch (D5)

### 6.1 What the user sees

- The avatar menu shows "Switch to the new version" (v1) or "Switch to the previous version" (v2).
- One click switches immediately on the same route, keeping the URL and its list state.
- The choice is remembered on the server (every device), defaults to v1, and can be changed any time, as often as
  wanted.
- Every v2 page also carries "Previous version" in the avatar menu, the one place users look (Salesforce, Jira and
  GitHub all keep an in-page way back, `UI-V2-DISCOVERY.md` 5.1).

### 6.2 Who can switch

- **Phases 0-6:** only users holding the permission `ui.v2.preview`. At first that is the owner and crew test
  accounts; nobody else sees the menu item. The permission system exists (`UserPermissionService`), so this needs no
  new column.
- **Phase 7 (pilot):** the permission is granted to a pilot role.
- **Phase 8 (release):** v2 becomes available to everyone and then the default for new sign-ins. Users can still go
  back.
- **Phase 9 (sunset):** v1 is removed after a published date, only once v2 has been the default for a full cycle with
  no open regression.

### 6.3 Storage

- `users.ui_version` (`'v1' | 'v2'`, default `'v1'`), returned by `GET /me` and the `get_user` builder (both manual dict
  builders, `LESSONS-LEARNT.md`).
- Written by `PUT /me/ui-version`.
- **Kill switch:** `system_settings.ui_v2_enabled` (default true once phase 0 ships). When false, every user gets v1
  regardless. It is one boolean, justified by release safety: a bad v2 deploy is reverted for everyone without a
  rollback.

### 6.4 How the code is organised

Same routes, same data layer, two presentation layers:

```
app/(protected)/<area>/<route>/page.tsx      -> <Versioned v1={V1Client} v2={V2Client} />
app/(protected)/<area>/<route>/components/   -> v1 (untouched until sunset)
app/(protected)/<area>/<route>/_v2/          -> v2 screen client(s)
components/v2/                               -> v2 archetype components (shell, grid chrome, RecordHeader, forms, StateView...)
components/ui/                               -> primitives shared by both (Radix wrappers); v2 styling via tokens under [data-ui="v2"]
hooks/, services/, lib/api-client            -> shared, unchanged (UI -> hooks -> services layering, PRINCIPLES.md)
```

- `<Versioned>` reads the version from the session context and renders one side.
- The shell (`Demo1Layout` vs `components/v2/shell`) switches the same way, in `app/(protected)/layout.tsx`.
- `<html data-ui="v2">` scopes the v2 token values, so a v1 screen keeps v1 tokens.
- URL contracts (`page`, `limit`, `sort`, `dir`, filters, `from=`) are identical, so a link from v1 opens the same
  record in v2 and back.

### 6.5 Safe fallback

| Failure | What happens |
| --- | --- |
| `/me` fails or returns no version | v1 |
| Kill switch off | v1 for everyone |
| A route has no v2 client yet (phases 1-6) | The v1 page renders inside the v2 shell with v1 tokens scoped to the content area, plus a small "previous-version screen" chip visible only to preview users, so gaps are visible to the owner and never to staff |
| A v2 screen throws | The v2 error boundary shows the error state ("This screen hit a problem. Open it in the previous version." + button) and reports to `client_error_report` with `ui_version='v2'` |
| A v2 screen is slower than its v1 budget (section 11.4) | The telemetry gate fails the wave; the screen is fixed before release |

### 6.6 Cost of running two versions

**Hooks and services are shared,** so a business fix lands once. Only presentation is duplicated, and only until
sunset.

**Rule while both exist:**
- A bug fix in a screen's behaviour is made in the shared hook or service.
- A fix that must touch v1 presentation also touches v2 in the same PR, once that screen's v2 exists.

**Reviewer check:** a PR touching `components/` of a migrated route without its `_v2/` sibling needs a reason.

## 7. Archetype specs and acceptance checklists

**Every checklist item applies four times:** light 1280, dark 1280, light 375, dark 375. A screen passes when all
four pass.

**IDs:** L = list, D = detail, F = form, S = settings, B = dashboard, W = wizard, X = applies to all.

### 7.0 Every screen (X)

| ID | Check |
| --- | --- |
| X-1 | Built only from `components/v2/*` and `components/ui/*`; no raw palette class, raw hex, raw `<h1>`, native `title` on an icon button, `confirm()`, `toLocale*String` |
| X-2 | One filled primary, top right (desktop) or the floating action (phone); verb + object label; a blocked primary shows its reason underneath (`BlockedReason`) |
| X-3 | Every async surface ends in a `StateView` state (empty, no-match, error, no-access) or data within the never-stuck bound; loading shows the shape (skeleton) |
| X-4 | Dates dd/mm/yyyy via `lib/format/date.ts`; money with "RM" in the heading (grids) or inside the field (inputs); numbers `tabular-nums` |
| X-5 | No page-level sideways scroll at 375; nothing clipped at 1280 |
| X-6 | Keyboard: every action reachable; focus visible (2 px ring); Esc closes the top surface only |
| X-7 | axe-core: 0 serious/critical; text contrast >= 4.5:1 and UI boundaries >= 3:1 under every preset |
| X-8 | No dialog opens on top of another dialog |
| X-9 | Sentence case for labels, buttons, tabs, menu items; no UUIDs; no feature explanations |
| X-10 | Visual baseline captured and approved (section 11.1) |
| X-11 | Performance within budget (section 11.4) |
| X-12 | Breadcrumb = the sidebar path (not rooted at "Dashboards"); its last crumb equals the page title; no "Back to ..." button beside it (discovery W3: 22 mismatches) |
| X-13 | No native `type="date"` / `datetime-local` input (60 files today draw the browser's locale, discovery W9) |
| X-14 | Empty state = heading + hint, no button, no feature explanation (discovery W4, W6) |
| X-15 | Selected toggles and segments use the soft tint, never the primary fill, so the one filled control is the CTA (pending Q4) |

### 7.1 List (L)

**Desktop layout:**
1. `PageHeader`: crumbs; title; right side holds one CTA (if the list has create) and a `ViewToggle` (List | Schedule
   | Board) if the screen has views.
2. Optional `FacetChips`: count chips that toggle a filter (replaces KPI tiles above lists).
3. The grid card:
   - Toolbar row: `ListSearchInput`, one `FilterChip` per filter (multi-select), "+ Filter" for unset ones, "Clear
     filters", saved views, then Columns on the right.
   - Selection mode replaces the toolbar with a selection bar: "N selected · Select all {total} · bulk actions ·
     Clear".
   - Rows: 44 px, 14 px, one line, `truncate` + `title`, +N pill for overflow; status via `Badge`.
   - Pager: "1 - 25 of 312", page numbers, rows per page.

**Rows:**
- Click opens the record; Cmd/Ctrl+click opens a new tab.
- Right-click opens `DataGridRowMenu` (Open, Open in new tab, Copy {id}, then the entity's actions). It acts on the
  selection when the row is part of it.
- Shift+F10 opens the same menu from the keyboard.

**Phone (playbook, section 8):**
- The list layout the playbook prescribes for phones.
- The floating action for the CTA.
- A bottom selection bar while selecting.
- A filter bar that opens a bottom sheet.
- A long press opens the row menu as a sheet.

| ID | Check |
| --- | --- |
| L-1 | Every column sorts server-side, or the list's plan names why one cannot (allowlist entry) |
| L-2 | Every dropdown filter is a multi-select `FilterChip`; the applied values read inline |
| L-3 | One line per row on desktop; overflow uses a +N pill |
| L-4 | Shift-click, drag and Shift+Arrow ranges; "Select all {total}" appears once a page is fully ticked; bulk actions apply to the whole result set |
| L-5 | Right-click and Shift+F10 open the row menu; long press on touch; menu items = the record's gear items (D15) |
| L-6 | Column show/hide/order/width saved per user (`user_list_column_configs`) |
| L-7 | Page, sort, filters, search in the URL; Back from a record restores the exact row (M5-07) |
| L-8 | Empty, no-match, error, no-access states via `StateView` |
| L-9 | Phone layout per section 8, verified on a 375 capture |

### 7.2 Detail / record (D)

**Desktop layout:**
1. Crumbs.
2. `RecordHeader`:
   - Number + status `Badge` (+ at most one more badge) inline.
   - ONE subtitle line (parent document link, "Raised by X on dd/mm/yyyy").
   - On the right: `RecordNavigation` ("3 / 25 ‹ ›"), gear, ONE primary.
3. If the record waits on another role: a `WaitingOn` line under the header ("Waiting on CS to reserve 2 lines ·
   requested by J***** on 10/11/2026").
4. `RecordMeta` strip: at most 6 read-only key facts.
5. Line tabs, **at most 6 including History**, with counts on list tabs. History is always last.
6. Tab bodies: DataGrids for lines, `FormSection` cards for field groups, explicit empty states.

**Phone (playbook):**
- The header condenses as the page scrolls.
- The primary becomes the floating action.
- Tabs scroll sideways.
- The gear opens as a bottom sheet.

| ID | Check |
| --- | --- |
| D-1 | Header: number and badge inline, one subtitle, actions right, no card frame; the record's identity IS the page heading (no generic "Order Inquiry" / "Product" title above it, discovery W1-W2) |
| D-2 | Exactly one filled primary = the step the state waits on; other steps in the gear; when the viewer cannot act, `WaitingOn` instead of a disabled button |
| D-3 | Gear: secondary actions, separator, Delete (deferred countdown) last |
| D-4 | Prev/next pager keeps the current tab (`hooks/useUrlTab.ts`) |
| D-5 | Read-only metadata under the header, never inside a tab body |
| D-6 | At most 6 tabs; view and edit share the same tabs and order (ADR) |
| D-7 | Every section renders, with a heading + hint empty state |
| D-8 | History tab, last, using `HistoryTab` (tracked changes "old -> new" merged with notes and events, filterable by event type) |
| D-9 | Exports end in a "ready" toast carrying the file link (section 9.4), not a separate drawer hunt |

### 7.3 Form (F)

- **Create** is a dialog by default; a page only for complex, multi-tab or file-centric flows (ADR).
- **Edit** is in place on the record (same layout as view), or the record's editor route for document builders
  (quotation).
- Fields come from `components/v2/forms` (shared with the portal, R9): labels above inputs, sentence case, required
  `*`, help text only where the portal shows one, 3 / 2 / 1 columns at 1280 / 768 / 375.
- Errors sit inline. Submit scrolls to the first error and opens its section.
- Autosaving forms show `AutosaveIndicator`. Dirty forms warn on leave with `ConfirmDialog` ("Leave without saving?",
  "Keep editing" / "Leave").

| ID | Check |
| --- | --- |
| F-1 | Same component in CRM and portal for the same form (R9) |
| F-2 | Every select is `SearchableSelect` / `SearchableMultiSelect`, optional ones clearable |
| F-3 | Dates use `DatePicker` (typed or picked, dd/mm/yyyy); no native `type="date"` |
| F-4 | Money inputs show "RM" inside, right-aligned, tidy on blur; no browser number arrows; wheel never changes a value |
| F-5 | Uploads use `FileDropzone` with per-file rows, progress and Try again; images through the one pipeline (R11) |
| F-6 | A blocked Save says why underneath |
| F-7 | The phone keyboard matches the field (`inputMode`) and the primary stays reachable above it |

### 7.4 Settings (S)

**Layout:**
- `PageHeader`, then two columns: `SettingsNav` (grouped) | page.
- The page is `SettingsSection` cards of `SettingsRow`s: label + one-line description left, control right; rows stack
  on the phone.
- `UnsavedChangesBar` appears only when dirty. Switches that save at once show a toast instead.

**Phone:** `SettingsNav` becomes its own list page.

| ID | Check |
| --- | --- |
| S-1 | No more than one level of grouping; every page reachable in two taps on the phone |
| S-2 | Every row has a sentence-case label and at most one line of description |
| S-3 | Save bar counts changes; Discard restores; leaving dirty asks |
| S-4 | Settings > Appearance hosts the theme picker (section 5.4) |

### 7.5 Dashboard (B)

- At most 4 `CountTile`s, each a link to the list it filters.
- Charts via recharts only (`components/ui/chart.tsx`).
- A table view of every chart's data under it.

| ID | Check |
| --- | --- |
| B-1 | Chart colours from tokens; readable in both modes |
| B-2 | Every figure clickable to its list; every chart has a table |
| B-3 | Dashboard loads its tiles independently (one slow tile never blanks the page) |

### 7.6 Wizard (W)

- A dialog for 3 steps or fewer, a page for more.
- The step list sits in the header; Back on the left, the step primary on the right.
- The last step is a review. The done state names the result and links to it.

| ID | Check |
| --- | --- |
| W-1 | Steps keep what was entered when going Back |
| W-2 | A long step (import, render) shows progress in words and finishes in a bounded time (never stuck) |
| W-3 | The result lands in the same module (no hop to Import jobs for the outcome) |

## 8. Phone (D4: follow the playbook)

**Source and status:** this section follows the playbook's phone rules as cited in `AUDIT`.

| Playbook rule (`AUDIT` cite) | v2 phone |
| --- | --- |
| Phones show stacked cards (`PB:179`) | Lists render the playbook's card layout below the tablet breakpoint: title line (ID + status badge), one subtitle line, up to two meta lines, chevron. Desktop keeps one line per row (R2). Scope per open question Q4 |
| Selection bar: count, actions, clear (`PB:229-235`) | While selecting, a bottom bar replaces the nav: "N selected", up to 3 actions, More, Clear |
| Text filter + column filters + "Showing n of N" (`PB:237`) | A filter bar under the top bar: search + "Filters (n)"; filters open in a bottom sheet; "Showing 25 of 312" |
| Phone top bar condenses, main action floats (`PB:430-438`) | Top bar 56 px, condensing to 44 px on scroll with the title; the page primary is a floating action button bottom-right above the bottom bar |
| System banners take their own height (`PB:439-445`) | Impersonation, offline and maintenance banners push content, never cover it |
| Header actions stay together at the right (`PB:590`) | Record header: number + badge, subtitle; gear and pager in the condensed bar |
| 360 px to desktop, no sideways page scroll (`PB:588`) | Unchanged mandate (375 and 1280) |
| Bottom navigation (owner D4, "bottom bars") | A bottom bar of 4 destinations + More: Home, the user's top module (from telemetry), Search, Notifications, More (opens the full nav sheet) |

**Before phase 1 builds any phone screen,** every line above is checked against the playbook text (crew was asked
for it on PR #2323) and corrected. The mocks (`ui-v2-mocks/index.html`, screen 5) draw this reading.

## 9. Components: inventory and replacement map

Counts are non-test files, measured on `main` at `6e6657e2` (`rg -l` over `app components lib hooks`).

### 9.1 Replacement map

| Concept | Today (files) | v2 component (path) | Retired at sunset |
| --- | --- | --- | --- |
| Shell | `Demo1Layout` + `demo1/components/*` (header 187 lines, sidebar-menu 338); menu config 3,548 lines | `components/v2/shell/{AppShell,Sidebar,Topbar,BottomBar,MobileNavSheet}.tsx`; menu config reused | demo1, demo2-10 layouts |
| Page title | `PageHeader` 322; Metronic `Toolbar` 84 (52 demo); raw `<h1>` 14 pages; bespoke 3 | `components/v2/PageHeader.tsx` | Toolbar partial, bespoke headers |
| Record header | `DetailActions` 63, `RecordHeaderCard` 3, `RecordNavigation` 19 | `components/v2/record/{RecordHeader,RecordMeta,WaitingOn,RecordNavigation}.tsx` | - |
| History | tab 8, sheet/drawer/panel 5, per-entity history components | `components/v2/record/HistoryTab.tsx` over `EventTimeline` | per-entity History components |
| Status | `Badge` 563; `STATUS_PILL_BASE` 56; 15 bespoke pills; 6 tone helpers | `Badge` + `lib/status/<domain>.ts` tone maps | `STATUS_PILL_BASE`, bespoke pills |
| Grid chrome | `DataGrid` 271, `PanelDataGrid` 50, `DataGridListToolbar` 144, `ListPageToolbar` 0 | `components/v2/grid/{GridToolbar,FilterChip,FacetChips,SelectionBar,RowMenu,PhoneCardList}.tsx` over the same `components/ui/data-grid*` engine | dead `ListPageToolbar` |
| Confirm | `DeferredActionButton` 7; `ConfirmDeleteDialog` 26 (retired); `alert-dialog` 96; "Are you sure" 29 | `DeferredActionButton` (destructive) + `components/v2/ConfirmDialog.tsx` (irreversible sends) | `ConfirmDeleteDialog`, `confirm-dismiss-dialog.tsx` (0 importers) |
| States | `ListLoadFailure` 5, `LoadErrorState`/`QueryErrorState` 11/5, `AccessDenied` 4, two `EmptyState`s, 36 ad hoc, 10 hard-coded "no permission" strings | `components/v2/StateView.tsx` (`empty`, `no-match`, `error`, `no-access`) | all listed |
| Forms | `useForm` 87, `ui/form` 64, `FormSection` 4, `FormDialogScaffold` 7, `Field` 3; portal forms separate | `components/v2/forms/{Form,Field,FormSection,FormDialog,BlockedReason,AutosaveIndicator}.tsx`, used by portal and CRM | per-form scaffolds |
| Dates | 11 helpers + 34 local + date-fns `format` in 17 + `toLocale*String` in 75 | `lib/format/date.ts` | old helpers |
| Upload | `FileDropzone` 38, `AttachmentDropzone` 3, `ResponseAttachmentDropzone` 2, `FileUploadZone` 0, raw `type="file"` 15 | `FileDropzone` v2 (per-file rows, retry, paste) | the others |
| Image | `AttachmentImage` 3, raw `<img>` 203 files, `AttachmentPreviewModal` 28, `PdfViewer` 4 + dead `PDFViewer`/`FilePreviewModal` | `AttachmentImage` + `AttachmentPreviewModal` (one pipeline) | dead viewers |
| Side panel | `ui/sheet` 44, `ui/dialog` 353, `ui/drawer` 4 | `Dialog` (desktop), vaul `Drawer` (phone sheets) | content Sheets (scope per Q2) |
| Tabs / toggles | 98 `TabsList` (87 line, 10 pill, 1 button); hand-built toggles | `Tabs` line; `components/v2/ViewToggle.tsx` | hand-built toggles |
| Charts | recharts 4, apexcharts 8 (5 demo) | recharts via `components/ui/chart.tsx` | apexcharts |
| Tooltip | `ui/tooltip` 35; native `title` on about 1,446 elements | `Tooltip` (playbook style) on icon buttons | `title` on icon buttons |
| Toast | `lib/toast.ts` 493 (already one) | same, plus `toast.file(...)` for ready exports | - |
| Theme | `next-themes` (localStorage) | `components/v2/theme/{ThemeProvider,ThemePicker}.tsx`, `lib/theme/{generate,presets}.ts` | localStorage key |
| Version | none | `components/v2/Versioned.tsx`, `useUiVersion()` | at sunset |

### 9.2 Component specs (each gets a vitest suite and a capture page, phase 0-4)

| Component | Props in short | Notes |
| --- | --- | --- |
| `RecordHeader` | `id`, `badges` (max 2), `subtitle` (one node), `pager`, `gear`, `primary` (one) | Type-level: a second primary cannot be passed |
| `WaitingOn` | `who`, `what`, `since` | Replaces a disabled primary for a viewer who cannot act |
| `RecordMeta` | up to 6 `{label, value}` | Truncates with title |
| `HistoryTab` | `entityType`, `entityId`, `filters?` | One endpoint shape; merges audit changes, notes, events |
| `FilterChip` | `label`, `options` (async ok), `value[]` | Multi only; inline summary "a, b +2" |
| `SelectionBar` | `count`, `total`, `onSelectAll`, `actions` | "Select all {total}" after a full page |
| `RowMenu` | `items` from `use<Entity>Actions` | Right-click, Shift+F10, long press |
| `PhoneCardList` | `title`, `badge`, `subtitle`, `meta[]` per row | Playbook card |
| `StateView` | `kind`, `title`, `hint`, `onRetry?`, `grantedBy?` | No buttons except Try again |
| `ConfirmDialog` | `question`, `consequence`, `keepLabel`, `actionLabel` | Playbook wording |
| `BlockedReason` | `reason` | Under a disabled primary |
| `ThemePicker` | - | Presets, custom hex, live contrast, preview |

### 9.3 Interaction rules (summary; the full text moves into `DESIGN-LANGUAGE.md` in phase 0)

| Rule | Detail |
| --- | --- |
| Primary | One per screen; the state's next step; verb + object |
| Menus | Gear on records; right-click / Shift+F10 / long press on rows; no row icons, no "..." column |
| Confirm | Delete/Archive/Unlink = deferred countdown (unchanged); irreversible sends = `ConfirmDialog` with playbook wording; everything else = no confirm |
| No stacked dialogs | A dialog that needs another step replaces its content (step) instead of opening a second dialog |
| Hand-offs | `WaitingOn` line; the role that must act sees the primary |
| Toasts | Past tense, object, count ("Sent 2 lines to purchasing"); errors say what to do |
| States | `StateView` only; no technical messages |
| Uploads / images | One `FileDropzone`, one image pipeline |
| Tabs | At most 6 per record including History |

### 9.4 Exports

Today every export queues an RQ job and the file is collected elsewhere (`UI-V2-DISCOVERY.md` 4.10).

In v2:
- The button shows progress in place ("Preparing PDF...").
- When the job finishes, a toast carries the file ("Quotation SRT/Q/2026/0141 PDF is ready · Open"). The same file
  stays in My Downloads.
- If the job takes longer than the never-stuck bound, the toast says it will appear in My Downloads and stops waiting.

No backend change: the toast polls the existing download row (`user_downloads.ready_at`).

## 10. Phases and exit criteria

**Effort** is in agent-days (one coder plus reviewer per lane), indicative. **Every phase ends with:** an owner
walkthrough on the crew test copy, the gates in section 11 green for everything the phase touched (light and dark,
1280 and 375), and the plan's Status line updated.

| Phase | Scope | Exit criteria | Effort |
| --- | --- | --- | --- |
| **0 Foundations** | (a) R1-R14 + interaction rules into `DESIGN-LANGUAGE.md` / `PR-CHECKLIST.md`. (b) Page-view telemetry (4.3). (c) `users.ui_version`, `ui.v2.preview` permission, kill switch, `<Versioned>`, v2 error boundary, fallback chip. (d) Theme engine: generator, presets, AA guard, `users.theme_mode`, `system_settings.theme`, Appearance page. (e) v2 shell: sidebar, top bar, phone bottom bar + nav sheet. (f) `lib/format/date.ts`. (g) Deterministic UI fixture seed (`sorento_crm_backend/scripts/seed_ui_fixtures.py`, local `*_ci` only). (h) Capture + diff + axe tooling (11.1-11.3). (i) Inventory tests for R3, R4, R7, R11 and native date inputs (allowlists that only shrink). (j) Small-fix lane, can ship before v2: `handle_not_found` takes a human label instead of a model class name (`sorento_crm_backend/app/services/error_handler.py:36-42`, 17 call sites) | Owner can switch v1 <-> v2 on any route and back; every preset passes AA in both modes (token tests); v2 shell captured on 6 routes x 4 variants; telemetry rows arriving; kill switch tested | 15-20 |
| **1 List archetype** | `GridToolbar`, `FilterChip`, `FacetChips`, `SelectionBar` + select-all-N (backend bulk-by-filter where missing), `RowMenu`, `PhoneCardList`, `StateView`; reference screen: OI list | L-1..L-9 and X-1..X-11 on the OI list in 4 variants; component suites green; owner sign-off on the reference | 10-14 |
| **2 Detail archetype** | `RecordHeader`, `WaitingOn`, `RecordMeta`, `HistoryTab` (one backend shape), `ConfirmDialog`, status tone maps; reference screens: OI detail, quotation document view | D-1..D-9 on both references; History tab works for every entity that has audit rows | 10-14 |
| **3 Form archetype** | `components/v2/forms` shared with the portal, `BlockedReason`, `AutosaveIndicator`, `DatePicker` everywhere, `FileDropzone` v2, image pipeline; reference screens: quotation editor, price tag request (portal + CRM) | F-1..F-7 on both; the portal renders the same component | 10-14 |
| **4 Settings, dashboard, wizard** | `SettingsNav/Section/Row`, `UnsavedChangesBar`, recharts-only dashboard kit, `Wizard`; reference screens: System Settings, one dashboard, GRN import | S, B, W checklists on each reference | 8-12 |
| **5 Area waves A-F** | Every remaining page per area (4.2), built from the archetype kit; journey fixes from discovery (two primaries, gear-hidden next steps, tab budget, stacked dialogs, export toast) | Per area: every page passes its checklist in 4 variants; journeys in that area walked end to end in v2 by the owner; no "v2 worse than v1" items open | 90-120 (about 387 pages; most are thin lists and details on the kit) |
| **6 Owner daily use** | The owner (and crew test accounts) use v2 as the daily UI; polish lanes from their notes | 2+ weeks with no open regression; telemetry shows v2 time-to-data <= v1 on the top 20 routes | 8-15 (polish) |
| **7 Pilot** | `ui.v2.preview` to a pilot role (one team per main journey) | 2 weeks; switch-back rate and reasons reviewed; fixes shipped | 5-10 |
| **8 Release** | v2 available to all, default for new sign-ins; users can go back | 4 weeks; switch-back rate low and falling; no open severity-1 | 3-5 |
| **9 Sunset v1** | Announce a date; remove v1 presentation, `<Versioned>`, `users.ui_version`, the Metronic demos, dead components, apexcharts, date helper re-exports | v1 code deleted; inventory allowlists at zero or justified | 8-12 |

**Total:** about 170-240 agent-days. Phases 1-4 can overlap after phase 0 (they share no files). Area waves can run
two at a time.

## 11. Testing strategy

### 11.1 Visual regression

- **Fixtures:** `seed_ui_fixtures.py` lays a fixed dataset (masked names, fixed dates, every status present, empty
  and overfull records) on a local `*_ci` database, so a capture is the same on every run.
- **Capture:**
  - One script (`scripts/ui-capture.mjs`) signs in as the fixture admin, visits every route in a manifest generated
    from `UI-V2-SCREEN-INVENTORY.md`, and saves PNGs.
  - Variants per route: {v1, v2} x {light, dark} x {1280, 375} x {default, empty, error where reachable}.
  - It uses the pre-installed Playwright library as a script, not a test runner spec, which keeps the standing
    order "no new Playwright spec" (`CLAUDE.md`). Decision Q5 asks the owner to confirm.
- **Diff:** pixelmatch against approved baselines with a 0.1% pixel threshold per image.
  - Baselines live outside git (a release artifact store or the owner's Mac), keyed by route and variant.
  - A diff over threshold is reviewed in a generated HTML report: side by side, slider, approve.
- **When:** in the lane's sandbox for the routes a lane touched, and the full set at each phase exit.

### 11.2 Accessibility

- `axe-core` runs on every captured page in both modes: 0 serious or critical. Moderate findings are listed in the
  phase report.
- **Keyboard walk per archetype reference:** tab order, Shift+F10 row menu, Esc, focus return after dialogs.
- **Token contrast tests** for every preset in both modes (`css/design-tokens.test.ts`).
- Screen reader spot check (VoiceOver) on the five reference screens at phase 4.

### 11.3 Component tests

- Every `components/v2/*` component has a vitest suite: behaviour, a11y roles, and type-level rules (one primary,
  multi-only filter).
- The existing inventory tests are extended for R3/R4/R7/R11.

### 11.4 Performance budgets (per route, measured by telemetry and the capture run)

| Metric | Budget |
| --- | --- |
| Time to first data (route change to first row or record painted) | p75 <= v1's p75 for the same route; and <= 1.5 s on the fixture DB |
| Interaction to next paint (row menu, filter apply, tab switch) | <= 200 ms p75 |
| Layout shift | CLS <= 0.05 |
| Route JS (first load) | <= v1 + 10% |
| Theme or version switch | no unstyled frame; <= 300 ms to repaint |

### 11.5 Journey tests

The nine discovery journeys (J1-J9) are walked end to end in v2 by the tester with agent-browser at each area wave
exit, then by the owner on the crew test copy. They are recorded as evidence runs, not specs.

## 12. Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Two presentation layers drift (a v1 fix not mirrored) | High | Shared hooks and services; reviewer check (6.6); the long run is bounded by sunset |
| The program is long, and priorities change mid-way | High | Waves are independent; v1 remains complete; any wave can pause |
| Phone cards conflict with one line per row | Medium | Desktop keeps R2; phone follows the playbook (D4); scope per Q4 |
| Custom brand colours break contrast | Medium | Generator AA guard + tests (5.2) |
| Telemetry raises privacy questions | Low | Route patterns only (no ids, no query strings), staff users only, 90-day retention |
| "Sort every column" needs backend keys that do not exist | Medium | Allowlist with reasons; each list lane measures it first |
| Owner time for walkthroughs becomes the bottleneck | Medium | Phase exits batch the walkthrough; crew pre-checks with captures |
| Visual baselines churn on unrelated changes | Medium | Fixture data is fixed; per-route approval; threshold tuned in phase 0 |

## 13. Decisions for the owner

Five decisions are filed in the crew report (see `UI-V2-DISCOVERY.md` section 7 for all seven open questions).
Until answered, the plan assumes the recommendation:

| # | Decision | Assumed |
| --- | --- | --- |
| Q1 | Default blue for filled buttons | The AA-safe step of today's hue |
| Q2 | Retire right-side Sheets on desktop | Yes; dialogs and lightboxes on desktop, bottom sheets on the phone |
| Q3 | Phone list cards | One generic card from each list's columns, tuned for journey lists |
| Q4 | Selected toggles | Soft tint, not the primary fill |
| Q5 | Page-view telemetry in phase 0 | Yes |
| Q6 | Theme ownership | Company brand by an admin, light/dark per user |
| Q7 | Rows per page | 25 everywhere, user can change |
