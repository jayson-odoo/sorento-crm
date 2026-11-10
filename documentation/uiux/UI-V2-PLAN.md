# UI v2: the whole design plan

Status: proposed, awaiting owner approval. Planning lane UI-V2-PLAN (10 Nov 2026), docs and
static mocks only, no app code. Build lanes start after the owner approves this plan and answers
the five decisions in section 12.

- **Inputs:** the gap audit `documentation/uiux/playbook-uiux-audit.md` (branch
  `crew/uiux-playbook-audit`, PR #2322, cited below as `AUDIT`), the owner rules from crew memory
  (section 1), and the repo's own contract (`PRINCIPLES.md`, `documentation/reference/DESIGN-LANGUAGE.md`,
  `documentation/reference/ADR-PRODUCT-STANDARDS.md`). The private playbook repo was not readable from
  this sandbox. Every playbook reference comes through `AUDIT`, which cites it as `PB:<line>`.
- **Mocks:** `documentation/uiux/ui-v2-mocks/index.html`. It is one self-contained file with
  Before / After / Both views of the OI list, OI detail, quotation editor, System Settings and the
  phone list. A "Component map" toggle labels every v2 element with its component and repo path, and
  a "v2 dark" toggle shows the dark tokens. The same mapping is written out in a legend table under
  each screen.
- **Mock data:** the sandbox may not touch the shared dev DB (crew rule). Values therefore follow
  dev-data formats as they appear in the frontend test fixtures: OI numbers `OI-YYMM-NNNN`, SO numbers
  `SO41xxxx`, product codes `SRT382-6` / `SRTWC8613-RL` / `CB6633`, suppliers `FOSHAN WORKS` /
  `DAFUYUAN` / `CHAOSHENG`, quotation number `SRT/Q/2026/0141`. Every person and company name is
  masked (`R***** Kitchen Sdn Bhd`).
- **Paths:** paths are relative to `sorento_crm_frontend/` unless they start with `documentation/` or
  `sorento_crm_backend/`. File counts are non-test files and were measured on `main` at `6e6657e2`;
  each row says how it was counted.

## 1. What v2 is, in one paragraph

v2 is not a redesign. The repo already has a strong contract: deferred delete, one CTA, line
tabs, DataGrid everywhere, motion presets, never-stuck states. What it lacks is **one visual
system applied evenly**. Today the same idea has two to five implementations (section 6). The
brand colour is Tailwind blue rather than Sorento's own. Several owner rules live only in crew
memory, so a reviewer cannot enforce them. v2 does three things:

1. It writes the owner rules into the contract.
2. It swaps the tokens to a Sorento palette and a denser type scale.
3. It moves each page archetype onto one set of shared components, in waves, behind a "UI v2"
   switch that defaults to OFF.

### Owner rules (binding, they win over the playbook and over this plan)

| # | Rule | Where v2 lands it |
| --- | --- | --- |
| R1 | Every date dd/mm/yyyy, through one formatter | `lib/format/date.ts` (section 6.1) |
| R2 | Standard DataGrid, one line per row | List archetype (5.1); `data-grid-table.tsx` forbids multi-line cells |
| R3 | Every column sortable server-side | List archetype; backend sort keys where missing (OI Reserve, `AUDIT` H:491) |
| R4 | Every dropdown filter multi-select | `FilterChip` wraps `SearchableMultiSelect` only (5.1) |
| R5 | Grid select like Odoo: shift/drag, "Select all N" | Exists (`components/ui/data-grid-range-select.ts:8-21`); v2 adds "Select all N" (5.1) |
| R6 | Right-click row menus, not row icons | NEW `DataGridRowMenu` (5.1, 7.2) |
| R7 | Minimal UI; dialog or lightbox over side panels; no bloat | Interaction rules (7); Sheet retired for content (6.11) |
| R8 | Detail header like OI: number and badge inline, one subtitle, actions right | `RecordHeader` (5.2) |
| R9 | CRM forms = portal forms (same component) | Form archetype (5.3) |
| R10 | History is a standard tab on every record | NEW `HistoryTab` (5.2) |
| R11 | One image pipeline | Section 7.7 |
| R12 | Sorento brand colour | Tokens (3.1); decision D1 |

## 2. Principles

1. **One way per idea.** For each UI concept (date, header, status pill, empty state, upload,
   preview, filter, row menu) there is one component, and a second implementation is a review
   defect. Section 6 lists today's duplicates and which one survives.
2. **Data first, chrome last.** The first record row should sit high on the screen. The shell gets
   thinner (48 px topbar, 224 px sidebar) and summary tiles become 28 px chips. Toolbars take one
   row.
3. **One primary per screen.** It sits top right, filled, in brand colour. Everything else is
   outline, ghost, gear menu or row menu.
4. **Quiet surfaces.** No hover lifts, no glow, no motion beyond `lib/motion.ts`. Colour carries
   meaning (status, primary, danger) and never decoration.
5. **Tokens or nothing.** Feature code uses semantic tokens (`bg-primary`, `text-muted-foreground`,
   `Badge status`). A raw palette class or raw hex outside `components/ui` is a defect. Canvas and
   print artwork are exempt (section 6.15).
6. **Same everywhere.** List, detail, form and settings each have one layout. A user who learns one
   order inquiry knows every record.
7. **Simplest thing that works** (`PRINCIPLES.md` first section). v2 adds no theme panel, no font
   picker and no layout builder. Every new component in section 6 replaces at least two existing
   implementations.

## 3. Tokens

All tokens live in `css/config.reui.css`. Today `:root` maps them to the Tailwind palette
(`--primary: var(--color-blue-500)` at `:11`, dark `.dark` at `:126`). v2 defines its values under
`:root[data-ui="v2"]` and `.dark[data-ui="v2"]`. The switch (section 10) sets that attribute, so
every component already on tokens flips with no code change.

### 3.1 Colour

**Brand ramp: Sorento Red.** The repo already names it: `{ label: 'Sorento Red', value: '#b44d2e' }`
(`components/common/ColorPicker.tsx:30`, the dealer-kit brand swatches). The logo SVGs still carry
the Metronic pink `#F8285A` (`public/media/app/default-logo.svg`) and need the real Sorento mark
(decision D1).

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--brand-50` | `#fbf1ed` | `#2a1a14` | Selected row, active nav, active filter chip |
| `--brand-100` | `#f6ddd3` | `#3a2219` | Hover on brand-tinted items |
| `--brand-500` = `--primary` | `#b44d2e` | `#d9734f` | Primary button, links, focus ring, sort arrow |
| `--brand-600` = `--primary-hover` | `#9a3f24` | `#e58a68` | Primary hover/pressed |
| `--primary-foreground` | `#ffffff` | `#1a0d08` | Ink on a filled primary |

Contrast was computed with the WCAG formula. White on `#b44d2e` is 5.2:1 and `#d9734f` on the dark
background `#111113` is 5.9:1, so both pass AA for text. `css/design-tokens.test.ts` already asserts
pairs and gets the v2 set added.

**Neutrals.** Zinc stays. In light mode: `--background #fff`, `--canvas #f7f7f8` (page behind
cards), `--border #ececee`, `--input #dcdce0`, `--muted-foreground #71717a`. In dark mode:
`#111113` / `#0d0d0f` / `#26262b` / `#3a3a41` / `#a1a1aa`.

**Status.** Every status is one `Badge` tone, with tinted background and ink of the same hue. Each
pair passes 4.5:1.

| Tone | Light bg / ink | Dark bg / ink | Meaning |
| --- | --- | --- | --- |
| success | `#ecfdf3` / `#067647` | `#0b2a1c` / `#47cd89` | Done, reserved, approved |
| warning | `#fffaeb` / `#b54708` | `#2d1f06` / `#fdb022` | Waiting on someone, outstanding |
| info | `#eff4ff` / `#3538cd` | `#1a1f3d` / `#a4bcfd` | In progress, needs a next step |
| neutral | `#f4f4f5` / `#52525b` | `#26262b` / `#d4d4d8` | Draft, completed with nothing owed, parked |
| danger | `#fef3f2` / `#b42318` | `#3a1210` / `#f97066` | Failed, rejected, overdue |

`info` moves from violet (`--info: var(--color-violet-600)`) to indigo, because blue is no longer
the primary.

**Danger vs brand.** Both are warm reds. v2 keeps them apart by **use**, not hue alone. Danger is
never a filled button: destructive actions are the deferred countdown (`DeferredActionButton`),
drawn as danger text or an outline. Danger always comes with its word ("Delete", "Failed").
Decision D1 asks the owner to accept this.

### 3.2 Type

Inter stays (`--font-sans`, `DESIGN-LANGUAGE.md` D12). The scale gets one step denser for data
screens. Body is 13 px, where Metronic's `text-sm` gives 14 today.

| Token | Size / line | Weight | Use |
| --- | --- | --- | --- |
| `--text-2xs` | 11 / 14 | 550 | Badge, count chip |
| `--text-xs` | 12 / 16 | 500-550 | Column header, field label, caption, crumbs |
| `--text-2sm` (body) | 13 / 19 | 400 | Table cell, input, menu item, body copy |
| `--text-sm` | 14 / 20 | 600 | Section heading, dialog body emphasis |
| `--text-base` | 16 / 24 | 650 | Dialog title |
| `--text-xl` | 20 / 28 | 650, -0.015em | Page and record title |
| `--text-2xl` | 24 / 32 | 650 | Dashboard figures only |

Numbers in tables, totals, IDs and money use `tabular-nums`. Headings get `text-wrap: balance`,
which is missing today (`AUDIT` "Headings balanced").

### 3.3 Spacing, radius, density

- **Spacing:** a 4 px grid: 4, 8, 12, 16, 20, 24, 32. Page padding is 20 px at 1280 and 12 px at 375.
  The gap between cards is 12 px.
- **Radius:** `--radius` moves from 0.5rem to 0.375rem. Controls get 6 px, menus and toasts 8 px,
  cards and dialogs 12 px, and badges and chips 999 px.
- **Control height:** 32 px default, 28 px small, 36 px large. A coarse pointer gets the invisible
  44 px hit area that already exists (`COARSE_HIT_TARGET_CLASS`, `components/ui/primitive-classes.ts`).
- **Density:** one token, `--row-h`. It is 36 px on desktop ("Comfortable") and 44 px under
  `(pointer: coarse)`. Column header height is 34 px. Decision D3 asks whether a user-selectable
  Compact (32 px) is wanted. The recommendation is no, until someone asks for it.
- **Elevation:** three steps only. Cards are flat (border, no shadow). Menus and popovers get
  `0 12px 32px rgb(0 0 0/.14)`. Dialogs get the same plus the existing scrim. Materials stay as
  defined (`--material-*`, `DESIGN-LANGUAGE.md` section 2).

### 3.4 Light and dark

Both modes ship as tokens from wave 0, because the cost is the same token file. Dark mode keeps its
current entry point (user menu, `app/components/partials/topbar/user-dropdown-menu.tsx:63`). Decision
D2 asks whether dark gets its own visual QA pass in every wave or only at the end.

## 4. Layout shell

Only `Demo1Layout` is live (`app/(protected)/layout.tsx`, `app/components/layouts/demo1/layout.tsx`).
The other nine demo layouts are unreferenced.

| Part | Today | v2 |
| --- | --- | --- |
| Sidebar | `demo1/components/sidebar.tsx` (30 lines) + `sidebar-menu.tsx` (338); menu `config/menu.config.tsx` (3,548 lines: `MENU_SIDEBAR :1542`, `MENU_SIDEBAR_COMPACT :1638`, `MENU_MEGA_MOBILE :3121`); Metronic demo entries remain (Billing, Invite a friend, Privacy Settings at `:1739,2929,3286`) | 224 px; 30 px items; group labels in sentence case; active item = `--brand-50` tint plus brand ink; icon rail + hover-open kept (`css/demos/demo1.css:89-118`); demo entries removed |
| Topbar | `demo1/components/header.tsx` (187 lines), 64 px, the crumb lives here AND in `PageHeader` | 48 px: visible search field that opens the existing Cmd/Ctrl+K dialog (`app/components/partials/dialogs/search/search-dialog.tsx`), company switcher, notifications, avatar menu. Crumbs only in `PageHeader` |
| Page container | `APP_SETTINGS.container: 'fixed'` (`config/settings.config.ts`) | Fluid up to 1600 px; lists use the full width, forms cap at 960 px |
| Phone (375 px) | Vaul drawer behind `useIsMobile` (`header.tsx:85-90`); title, toggle, tiles, search and toolbar stack (about 60% of the screen before row 1, mock 5) | Page title moves INTO the 48 px bar; crumbs hidden; toolbar is one row (search, filter count, view toggle); filters in a bottom sheet |
| Mobile bottom bar | None (only a public CTA strip, `app/(public)/c/[company]/[slug]/page.tsx:143`) | **Not added** (decision D4) |
| AI bubble | Always floating (`app/components/common/AIAssistantBubble.tsx:595`) | Kept; it is the one floating element. On a phone it hides while a bottom sheet or a dialog is open |

## 5. Page archetypes

Every protected page is one of six archetypes. A page that fits none needs a reason in its plan.

### 5.1 List (mock 1, mock 5)

Order from top to bottom:

1. `PageHeader` with title and at most one CTA. A view toggle (List | Schedule | Board) sits in the
   same slot.
2. Optional `FacetChips`: count chips that are filter toggles, replacing KPI tiles above a list.
3. The DataGrid card. Its toolbar row holds `ListSearchInput`, one `FilterChip` per filter
   (multi-select, applied value inline: "Reserve: Needs reserve, Parked"), "+ Filter" chips for
   unset filters, "Clear filters", and the Columns icon at the right.
4. When any row is ticked, the selection bar replaces the toolbar: "N selected", "Select all {total}",
   bulk actions, Clear.
5. Rows: one line, `--row-h`, every column sortable, `truncate` + `title`, IDs `tabular-nums`
   semibold, status via `Badge`.
6. Pager: "1 - 25 of 312", page numbers, rows per page (25 default, kept; `AUDIT` section 6).

**Row interactions:**

- Click opens the record (`rowHref`).
- Right-click opens `DataGridRowMenu`. Its items come from the entity's `use<Entity>Actions(record)`
  (D15, `DESIGN-LANGUAGE.md` section 5), plus three built-ins: Open, Open in new tab, Copy {id}.
- If the right-clicked row is part of a selection, the menu acts on the selection ("Send 3 to
  purchasing").
- On touch, a 500 ms long press opens the same items in a vaul bottom sheet. That is the hold the
  range select already uses for touch drags.
- On the keyboard, Shift+F10 or the context-menu key opens it.

**Phone:** the same grid in its box (owner Q2, no cards). The identifier column is pinned on coarse
pointers, rows are 44 px, filters open in a sheet, and pagination is compact.

**Header filters per column type** (`PB:192-202`) are not adopted. Toolbar chips meet R4 and keep
one place to look.

### 5.2 Detail / record (mock 2)

Order from top to bottom:

1. Crumbs.
2. **`RecordHeader`**: the record number at 20 px with the status `Badge` (and at most one more
   badge) inline, then ONE subtitle line (linked parent document, "Raised by X on dd/mm/yyyy"). At
   the right: `RecordNavigation` ("3 / 25 ‹ ›"), the gear `DetailActionsMenu`, and ONE primary
   button. No card frame.
3. **`RecordMeta`**: a single strip of up to 6 read-only key facts, directly under the header (the
   ADR rule "read-only metadata sits directly under the page header").
4. Line `Tabs` with count chips on tabs that hold lists. **History is always the last tab**
   (`HistoryTab`).
5. Tab bodies: DataGrids for lines, `FormSection` cards for field groups. Each has an explicit
   empty state (heading + hint).

View and Edit stay the same layout, with in-place inputs (ADR). `DetailActions` takes a single
`primary` prop, so a second filled button cannot be passed. That fixes `OrderInquiryDetail.tsx:960-983`
(Confirm and Reserve both filled) at the type level. The primary is the step the record's state is
waiting for, and the other step moves to the top of the gear menu.

### 5.3 Form (mock 3)

A form is one of two kinds:

- **Create:** a modal by default (ADR). A dedicated page is used only for complex, multi-tab or
  file-centric flows.
- **Edit:** the record page itself, or the record's editor route (quotation).

Layout:

- `RecordHeader`, or the dialog title, with the primary at the right.
- If the primary is blocked, **`BlockedReason`** shows the reason under it in plain words ("Line 3
  needs a rate"). It does not pulse.
- An autosaving form shows **`AutosaveIndicator`** ("Saving... / Saved 2:14 pm / Save failed +
  Retry", moved out of `QuotationFormClient.tsx:828`).
- Fields come from `components/common/Field.tsx` inside `FormSection` (`components/common/FormSection.tsx`).
  Labels sit above inputs in sentence case, required fields carry a red asterisk, and the help line
  appears only where the portal shows one. The grid is 3 columns at 1280, 2 at 768 and 1 at 375.
- **CRM form = portal form (R9).** `Field`, `FormSection` and the field renderers move to one
  `components/forms/` module used by both `app/(auth)/portal/components/*Form.tsx` and the CRM
  dialogs.
- Errors appear next to the field. Submit scrolls to the first error and opens its section, which
  is the portal's behaviour today (`AUDIT` section 7.5) and becomes the shared default.
- Grid-shaped inputs (quotation lines) use the DataGrid with an inline cell error, plus the header's
  `BlockedReason`.

### 5.4 Dashboard

- A row of `CountTile` (`components/common/CountTile.tsx`, kept) for at most 4 figures. Each tile is
  a link to the list that the figure filters.
- Charts use **one library, recharts**, through `components/ui/chart.tsx`. Today recharts is in 4
  files and apexcharts in 8, of which 5 are Metronic demo pages. The 3 real apexcharts uses
  (`scm/reorder` PlanTrendPopover, PlanRowPanel, SLATrackingDashboard) move to recharts, and
  `css/components/apexcharts.css` (101 lines) goes away.
- Chart colours come from `--chart-1..5`, re-derived from the v2 ramp (brand, indigo, green, amber,
  zinc).
- Under each dashboard, a table view of the same data, using the same DataGrid.

### 5.5 Wizard

Used for imports, onboarding and the dealer kit:

- A dialog when it has 3 steps or fewer, a page when it has more.
- The step list sits in the header ("1 Upload · 2 Map columns · 3 Review"). Back is at the left and
  the step's primary at the right.
- The last step is a review screen. After submit, the wizard shows a done state that names the
  result, with a link to it (as `ReserveConfirmDialog` does today, `AUDIT` RCD:169,266-270).
- `ImportColumnMapper` and `ImportFeedbackSections` (`components/common/`) become steps 2 and 3 of a
  shared `Wizard` shell.

### 5.6 Settings (mock 4)

- `PageHeader`, then two columns: **`SettingsNav`** (grouped vertical list) and the page.
- The page is a stack of **`SettingsSection`** cards made of **`SettingsRow`**s: label and an
  optional one-line description on the left, the control (300 px) on the right. Rows stack at 375 px,
  and at 375 px `SettingsNav` becomes its own list page.
- Saving: **`UnsavedChangesBar`** sticks to the bottom only while something changed, says how many
  ("2 unsaved changes") and offers Discard and Save changes. Changed rows get a brand left edge.
  Settings that apply immediately (switches with server writes) say so with a toast and need no bar.
- **System Settings as the first case:**
  - Its 14 horizontal tabs (`user-management/settings/layout.tsx:321-386`) regroup into Company,
    Operations, Messaging, Chatbot and AI, and System.
  - The General form, a single card mislabelled "Social Settings" (`page.tsx:608`) holding about 30
    unrelated fields with one "Save Settings" at `:1466`, splits into Company, Regional, and
    Countdowns and defaults.
  - Labels move to sentence case ("Shop Name" becomes "Company name").
  - The hard-coded native currency list becomes a `SearchableSelect`.

## 6. Components: standardise, replace, retire

Counts come from `rg -l` over `app components lib hooks modules providers services config`,
excluding tests. "Demo" means the Metronic demo pages (`store-client`, `account`, `auth` demos,
`app/components/layouts/demo2-10`).

| # | Concept | Today (duplicates, files) | v2 keeps | v2 replaces / retires |
| --- | --- | --- | --- | --- |
| 6.1 | Date formatting | 11 helpers in `lib/helpers.ts` (`formatDateTimeInMalaysia :446` in 190 files, `formatDateInMalaysia :325` in 153, `formatDate :128` in 72, `formatDateTime :499` in 20, `formatDateSafe :187` 7, `formatDateTimeSafe :198` 4, `formatDateRange :469` 6, `formatMaybeDate :489` 5, plus 4 more); 34 local `format*Date*` definitions elsewhere (e.g. `lib/respondIoChatRender.ts:493`, `app/(auth)/view/complaint/page.tsx:64`); 17 files call date-fns `format` directly (48 calls); 75 files call `toLocale(Date)String` | NEW `lib/format/date.ts` exporting `formatDate` (dd/mm/yyyy), `formatDateTime` (dd/mm/yyyy, h:mm am), `formatDateRange`, `formatTime`; Malaysia time zone inside | Old helpers become re-exports (one lane), then call sites move per wave; ESLint `no-restricted-imports` on date-fns `format` and `toLocaleDateString` in feature code |
| 6.2 | Page / record header | `PageHeader` 322 files (259 pages); Metronic `Toolbar`/`ToolbarHeading` 84/65 files (53 pages, 52 of them demo); `RecordHeaderCard` 3; `QuotationDocumentPageHeader` 1; `TargetPageHeader` 1; 14 pages with a raw `<h1>`; quotation editor draws PageHeader AND RecordHeaderCard (`QuotationFormClient.tsx:895,999`) | `PageHeader` (lists, settings, dashboards); `RecordHeader` (= `RecordHeaderCard`, flattened) for every record | `QuotationDocumentPageHeader`, `TargetPageHeader`, raw `<h1>`, the Toolbar partial (with the demo pages) |
| 6.3 | Status pill | `Badge` 563 files; `STATUS_PILL_BASE` (`lib/status-pill.ts:103`) 56 files; 15 bespoke `*Status*Badge/Pill` components (`StatusPill`, `IdeaStatusBadge`, `TicketStatusBadge`, `BillingStatusBadge`, `OrderInquiryStatePill`, ...); 6 status-to-tone helpers (`lib/status-badge.ts:99`, `lib/complaint-status.ts:39`, `lib/price-tag-status.ts:34`, ...); price tag detail draws a custom span (`AUDIT` PTD:137) | `Badge status` + one `statusTone(domain, status)` map per domain in `lib/status/` | `STATUS_PILL_BASE`, the 15 wrappers (each becomes a one-line `Badge` call) |
| 6.4 | Confirm / destructive | `DeferredActionButton` 7 files; `ConfirmDeleteDialog` (retired, still 26 importers); `alert-dialog` imported by 97 files, 95 hand-rolled; `ConfirmActionDialog` (scm) 7; 5 more bespoke confirms; `confirm-dismiss-dialog.tsx` 0 importers (dead) | `DeferredActionButton` / `useDeferredAction` for destructive; NEW `ConfirmDialog` (one shell, playbook wording) for irreversible sends | `ConfirmDeleteDialog` (26), hand-rolled AlertDialogs, `ConfirmActionDialog`, dead `confirm-dismiss-dialog.tsx` |
| 6.5 | Empty / error / loading / no-access | `ListPageSkeleton` 174; `SectionSkeleton`; `LoadErrorState`/`QueryErrorState` 11/5; `ListLoadFailure` 5; `AccessDenied` (`app/components/common/AccessDenied.tsx:30`) 4; two different `EmptyState`s; 36 ad hoc `*Empty*`/`*ErrorState*` definitions; 10 files with hard-coded "don't have permission" | Skeletons as they are; NEW `StateView` with `kind="empty" / "no-match" / "error" / "no-access"` (heading + hint; error adds Try again; no-access names who can grant it and links back) | `LoadErrorState`, `QueryErrorState`, `ListLoadFailure`, `AccessDenied`, both `EmptyState`s and the ad hoc ones fold into `StateView`; `DataGridTableEmpty` renders `StateView` |
| 6.6 | List grid | `DataGrid` 271, `PanelDataGrid` 50, `ListPager` 9, `ListPageToolbar` 0 (dead); `ui/table` 35 files + 79 raw `<table>` (guarded by `raw-table.inventory.test.ts`) | `DataGrid` (+ `PanelDataGrid` as its in-card form) | Dead `ListPageToolbar`; raw tables shrink per wave (allowlist only shrinks) |
| 6.7 | Filters | Filter panel per list; Reserve single-select (`AUDIT` H:665); `SearchableMultiSelect` 155 files | NEW `FilterChip` (`components/ui/data-grid-filter-chip.tsx`) wrapping `SearchableMultiSelect`; NEW `FacetChips` | Per-list filter panels; KPI tiles above lists (`OrderInquiryStrip`, `SupplyKindCard`) |
| 6.8 | Row actions | No row menu in any `data-grid*` file; ad hoc ContextMenus in Drive, QuotationLinesGrid, PurchaseOrdersPanel, QuotationScopeTabs; 53 files with `use<Entity>Actions(` | NEW `DataGridRowMenu` on `components/ui/context-menu.tsx`, fed by `use<Entity>Actions` | The ad hoc ContextMenus adopt it |
| 6.9 | Upload | `FileDropzone` 38; portal `AttachmentDropzone` 3; `ResponseAttachmentDropzone` 2; `FileUploadZone` 0 (dead); `useFileUpload` 2 (demo); 15 raw `type="file"`; 11 native `onDrop` | `FileDropzone`, extended with per-file rows, progress, Try again, paste (from `AttachmentDropzone.tsx:271,318,392`) | `AttachmentDropzone`, `ResponseAttachmentDropzone`, dead `FileUploadZone` |
| 6.10 | Image / preview | `AttachmentPreviewModal` 28; `PreviewModalChrome` 2; `PdfViewer` 4 + competing dead `PDFViewer` / `FilePreviewModal`; `DesignLightbox` 4; `TownLightbox` 1; `AttachmentImage` 3; **203 files with raw `<img>` (350 tags)**, `next/image` 0 | `AttachmentImage` (thumb) and `AttachmentPreviewModal` on `PreviewModalChrome` (lightbox) | Dead `PDFViewer` + `FilePreviewModal`; raw `<img>` for attachments moves to `AttachmentImage` per wave (logos and icons may stay `<img>`) |
| 6.11 | Side panel vs dialog | `ui/sheet` 44 files, `ui/dialog` 353, vaul `ui/drawer` 4 | `Dialog` for content; vaul `Drawer` for phone sheets and the nav (D13) | Content Sheets (e.g. `QuotationHistorySheet`, price tag version history `RequestDesignSection.tsx:23,232`) become dialogs or the History tab |
| 6.12 | Tabs | 98 `TabsList`: 87 line, 10 `default` (pills), 1 `button` | Line tabs; `ViewToggle` for a non-navigation switch | Hand-built List/Schedule button pairs (`OrderInquiriesClient.tsx:1515-1545`) |
| 6.13 | Charts | recharts 4, apexcharts 8 (5 demo) | recharts via `components/ui/chart.tsx` | apexcharts + `css/components/apexcharts.css` |
| 6.14 | Tooltips | `ui/tooltip` 35 files; native `title=` on about 1,446 elements | `Tooltip` restyled to the playbook's copy-tip look (the one adoption from `AUDIT` Q4) for icon buttons; `title` stays for truncated cell text | Native `title` on icon buttons (gear `DetailActionsMenu.tsx:121-122`, prev/next `RecordNavigation.tsx:77,99`) |
| 6.15 | Raw colour | 998 raw palette classes in 194 non-demo files (amber 494, green 241, emerald 159, blue 126); 238 raw hex in 53 files, mostly canvas tag editors (`KonvaTagLayer.tsx` 33, `TagCanvasEditor.tsx` 30) | Tokens and `Badge` tones | Raw palette classes shrink per wave behind an inventory test (canvas and print artwork exempt) |
| 6.16 | Toasts | `lib/toast.ts` 493 files; `sonner` only in `components/ui/sonner.tsx` and `lib/toast.ts` | Already one; keep | - |
| 6.17 | Selects | `SearchableSelect` 323, `SearchableMultiSelect` 155; `ui/select` deleted; 2 native `<select>` | Keep | `eslint-dropdown-allowlist.mjs` (132 entries) is stale and gets re-measured |
| 6.18 | Metronic leftovers | `app/components/layouts/demo2-10` (unreferenced), demo pages (`store-client`, `account/billing`, `invite-a-friend`, ...), duplicate theme toggle `dropdown-menu-user.tsx:50`, `css/styles.css` imports `image-input.css` twice (`:25,29`) | - | Removed in phase 5 |

## 7. Interaction rules

### 7.1 Primary action

- One filled primary per screen (page, record or dialog), top right, in brand colour.
- The primary's label is a verb and its object: "Save quotation", "Reserve 2 lines", "Send to
  purchasing".
- When blocked, it shows `BlockedReason` underneath. A tooltip-only reason is not enough.
- On a phone the primary stays in the header row. There is no floating action button.

### 7.2 Menus

| Where | Menu | Contents |
| --- | --- | --- |
| Record header | Gear (`DetailActionsMenu`) | Secondary actions, separator, Delete last in danger ink (D6) |
| List row | Right-click / long press (`DataGridRowMenu`) | Open, Open in new tab, Copy {id}, then the same `use<Entity>Actions` items as the gear (D15). Never Edit, since the row click is the edit path |
| Grid line (editors) | Right-click | Insert above, Insert section above, Duplicate, Move up/down, Remove |
| Avatar | Dropdown | Profile, Theme, "Try UI v2" (section 10), Sign out |

There are no row icon buttons and no "..." column. A menu item shows its shortcut when it has one.

### 7.3 Confirm and undo

| Action kind | Pattern |
| --- | --- |
| Delete, Archive-as-delete, Unlink | Server-deferred countdown with Cancel (10 s / 5 s from System Settings). No dialog. Unchanged (`PRINCIPLES.md:255-262`) |
| Irreversible send (reserve and send, issue, submit for approval) | `ConfirmDialog`. Title is a question with its object ("Reserve 3 lines on OI-2611-0142?"). The line under the title says what happens. The safe button is named for what it keeps ("Keep editing"). The action button is a verb and its object. No "Are you sure" (29 files today) |
| Everything else (save, link, assign) | No confirm. Act and toast |

### 7.4 States

Every async surface ends in one of these within bounded time (`NEVER-STUCK-UI.md`):

| State | Component | Content |
| --- | --- | --- |
| Loading | `ListPageSkeleton` / `SectionSkeleton` | The shape of what is coming. A per-value "Calculating" for totals that recompute |
| Empty (nothing yet) | `StateView kind="empty"` | Heading + hint, never a button (one-CTA rule) |
| No match | `StateView kind="no-match"` | "No order inquiry matches these filters." Clear filters stays in the toolbar |
| Error | `StateView kind="error"` | What failed in plain words, plus Try again |
| No access | `StateView kind="no-access"` | "You need {permission label} to open this. Ask {role/admin}." plus a link back. Replaces the 10 hard-coded strings |

### 7.5 Toasts

- Use `lib/toast.ts` only.
- Write in the past tense with the object and the count: "Sent 2 lines to purchasing", not "Success!"
  or "{noun} saved".
- Errors say what to do next. Success shows for 4 s and errors for 5 s (unchanged).
- Undo stays inside the deferred countdown toast, so there is no second undo mechanism.

### 7.6 Uploads

- `FileDropzone` everywhere: drop, browse and paste.
- Each file gets a row with name, size, progress and a result. A failure names the file and offers
  Try again. One bad file does not fail the batch (today: one toast "Upload failed.",
  `AttachmentDropzone.tsx:238`).

### 7.7 One image pipeline (R11)

1. Upload: `FileDropzone`.
2. Storage: an `attachments` row through `app/services/storage_router.py` (exists).
3. Thumbnail: `AttachmentImage`.
4. Full view: `AttachmentPreviewModal` (lightbox, arrow keys, PDF via `PdfViewer`).

No feature builds its own `<img src>` for an attachment, its own lightbox or its own upload.
Quotation line photos, price tag designs, product images and complaint photos all use it.

### 7.8 Keyboard

| Shortcut | Action |
| --- | --- |
| Cmd/Ctrl+K | Search (exists) |
| Shift+F10 / context-menu key | Row menu |
| Enter | Open the focused row |
| Cmd/Ctrl+Enter | Open in a new tab |
| Shift+click / Shift+Arrow | Range select (exists) |
| Esc | Closes a menu or dialog, never a deferred countdown (D7) |

Keyboard-opened surfaces do not animate (`DESIGN-LANGUAGE.md` M2-01).

## 8. What we take from the playbook and what we keep

| Topic | Playbook (`AUDIT` cite) | v2 | Reason |
| --- | --- | --- | --- |
| Date display | "14 Nov 2026" (`PB:253`) | **Keep** dd/mm/yyyy | Owner rule R1; agreed `AUDIT` Q1 |
| Smart view, phone cards | `PB:176-179` | **Keep** one line per row, grid scrolls in its box | R2; agreed Q2. v2 makes the phone grid usable instead (pinned ID column, 44 px rows) |
| Other actions as icon buttons; row icons; RCT | `PB:114-141, 413-420` | **Keep** gear + right-click row menu | R6; agreed Q3 |
| Foundryx red CTA with lean/light; hover pop; Hold to Copy; Clipboard; Quick Tool | `PB:83-92, 218-225, 394-427, 611-624` | **Keep** minimal UI, Sorento brand | R7, R12; agreed Q4 |
| 3 s press-and-hold confirm | `PB:107-111` | **Keep** deferred countdown | Agreed Q5; no misclick and no reverse operation needed |
| Styled tooltip | `PB:428` | **Take** | Agreed Q4; icon buttons need a visible label |
| Dialog wording (question title, safe button named, verb + object) | `PB:105-106` | **Take** | Agreed Q5; one `ConfirmDialog` |
| Blocked action says why | `PB:93-102` | **Take** the reason under it, **skip** the pulse | Plain text is enough; no motion for state |
| No-access state with who can grant it | `PB:214` | **Take** | Missing today (10 ad hoc strings) |
| Upload per-file rows + retry | `PB:300-305` | **Take** | One bad file must not hide the others |
| Slim styled scrollbars | `PB:287` | **Take** (one CSS rule under `[data-ui="v2"]`) | Cheap, quieter on dense screens |
| Balanced headings | `PB:542` | **Take** | One CSS rule |
| "Showing n of N" | `PB:237` | **Take**, in the pager | Already partly there |
| Money field "RM" inside, tidy on blur | `PB:279-283` | **Take** for standalone money inputs; **keep** "(RM)" in grid headings | The playbook's own Documents rule (`PB:483`) puts the unit in the heading |
| Theme panel (palettes, font picker, size slider) | `PB:491-497` | **Skip** | No problem today that it solves (`PRINCIPLES.md` simplest thing) |
| Tabs as segmented toggles | `PB:317-324` | **Keep** line tabs | Repo rule `PR-CHECKLIST.md:52-53` |
| Phone top bar condenses, red action floats | `PB:430-438` | **Partly**: title moves into the bar; no floating action | R7 |
| 50 rows per page | `PB:203-209` | **Keep** 25 | Faster first paint; user can change |
| What the CRM does better (deferred delete, Odoo range select, server-saved columns, never-stuck, errors you can find, reduced transparency, visible autosave) | `AUDIT` section 7 | **Keep** and make them the shared defaults | Already proven here |

## 9. Accessibility

- **Contrast:** every text/background token pair is at least 4.5:1, and UI boundaries (input
  borders, focus ring) are at least 3:1. `css/design-tokens.test.ts` asserts the v2 set in both
  modes.
- **Focus:** a 2 px `--primary` ring with a 2 px offset on every focusable element, never removed.
  The selected row has both a tint and a check, never colour alone.
- **Status:** the badge text always says the state. The tone is extra information, so a colour-blind
  user loses nothing.
- **Targets:** 44 px on coarse pointers (existing `::after` hit area) and 32 px on fine pointers.
- **Labels:** every icon button has `aria-label` and the styled tooltip with the same words.
  `DataGridRowMenu` is reachable by keyboard (Shift+F10) and announced as a menu.
- **Motion and transparency:** `prefers-reduced-motion` and the reduced-transparency fallback stay
  as today (`css/styles.css:80-132`, `components/ui/primitive-classes.ts:36-39`).
- **Zoom:** pages work at 200% zoom and at 375 px with no page-level sideways scroll; only the grid
  box scrolls sideways.
- **Language:** sentence case, plain words, no UUIDs, no feature explanations in the UI (existing
  rules).

## 10. The "UI v2" switch

**What it is.** One boolean per user, `users.ui_v2` (default `false`), toggled by "Try UI v2" in the
avatar menu.

Wiring:

- The value is added to BOTH manual dict builders (`get_user` / `get_me`, see `LESSONS-LEARNT.md`).
- The protected layout sets `<html data-ui="v2">` when it is on.
- No feature-flag service and no tenant setting.

There is nothing to reuse today: the inventory found no `ui_version` or flag mechanism. The closest
per-user store is `UserListColumnConfig` (`sorento_crm_backend/app/models/user.py:868`), which is
keyed per listing and is the wrong shape. Per the simplest-thing rule, one column is enough.

**How screens move without a big bang:**

1. **Token-level changes** (colour, type, radius, spacing, scrollbars, balanced headings) live in
   CSS under `[data-ui="v2"]`. They apply to every screen that uses tokens, with no component
   branching.
2. **Structure-level changes** (`RecordHeader` without a card, `SettingsNav`, `FilterChip` row,
   `RecordMeta`) are built as the v2 version of the shared component. A component reads
   `useUiVersion()` **once, at its top**, and renders v1 or v2. The flag is never branched on inside
   feature code.
3. **Screens migrate in waves (section 11).** A screen is "v2-ready" when it uses only v2 shared
   components. With the switch OFF, users keep v1 everywhere. With it ON they get v2 tokens
   everywhere, plus v2 structure on migrated screens. Unmigrated screens still look coherent,
   because tokens carry most of the change.
4. **Rollout:**
   1. The owner and crew turn it on for themselves (wave 0 onward).
   2. A pilot group follows, by an admin bulk update.
   3. The default flips to ON for everyone once wave 3 is done.
   4. Phase 5 deletes the v1 branches, the column and the switch.

**Trigger to revisit:** if the owner wants a company-wide switch rather than per user, that is a
`system_settings` column and the same attribute. Decision D5.

## 11. Migration path

Sizes follow the crew lane sizes. Agent-days are rough and assume one coder per lane.

| Phase | Scope | Lanes | Effort |
| --- | --- | --- | --- |
| **0 Foundations** | (a) Owner rules R1-R12 and this plan's interaction rules into `DESIGN-LANGUAGE.md` + `PR-CHECKLIST.md` (docs). (b) `users.ui_v2` column, avatar-menu toggle, `data-ui` attribute, `useUiVersion()`. (c) v2 tokens under `[data-ui="v2"]` in `config.reui.css` + token contrast tests. (d) `lib/format/date.ts` with the old helpers re-exporting it. (e) Shell: sidebar, 48 px topbar, Metronic demo menu entries removed. (f) Styled `Tooltip`; tooltips on gear and prev/next | 3 (docs S; switch + tokens M; shell M) | 4-6 days |
| **1 List archetype** (first wave, decision D5) | `FilterChip`, `FacetChips`, `ViewToggle`, `DataGridRowMenu` (+ touch sheet), "Select all N", pinned ID column on coarse pointers, `--row-h`, `StateView` inside the grid. Backend: sort keys for every listed column that lacks one (start with OI Reserve). Migrate OI list first, then the 10 most-used lists (by `api_call_logs` counts) | 2 (grid components L; first 10 lists M) | 6-9 days |
| **2 Detail archetype** | `RecordHeader` v2 (flat), `RecordMeta`, single-`primary` `DetailActions`, `HistoryTab` (on `EventTimeline`), `ConfirmDialog`, `Badge` replaces `STATUS_PILL_BASE` (56 files) and the 15 wrappers. Migrate OI detail, quotation document view, price tag request, PO, SO | 2 (components M; status-pill sweep M) | 5-7 days |
| **3 Forms + uploads + images** | One `components/forms/` module shared by portal and CRM (R9); `BlockedReason`, `AutosaveIndicator`; `DatePicker` replaces native `type="date"`; `FileDropzone` per-file rows; `AttachmentDropzone` + `ResponseAttachmentDropzone` merged; attachment `<img>` to `AttachmentImage`; quotation editor single header + History tab | 2-3 (forms L; uploads/images M) | 7-10 days |
| **4 Settings, dashboards, wizards** | `SettingsNav`, `SettingsSection`, `SettingsRow`, `UnsavedChangesBar`; System Settings regroup; recharts-only (3 apex uses); `Wizard` shell for imports | 2 (settings M; charts + wizard M) | 4-6 days |
| **5 Flip and clean** | Default ON, then delete v1 branches and `users.ui_v2`. Delete dead code (`confirm-dismiss-dialog.tsx`, `ListPageToolbar`, `FilePreviewModal`, `PDFViewer`, `FileUploadZone`), `ConfirmDeleteDialog` importers, Metronic demo layouts and pages, the Toolbar partial, apexcharts, stale `eslint-dropdown-allowlist.mjs`. Raw palette inventory test turns into an error. Date helper re-exports deleted | 2 (cleanup M; sweep M) | 4-6 days |

**Total:** about 12-14 lanes and 30-44 agent-days, spread over waves the owner can pause between.

**Per-lane gates:** each wave's lanes run the normal `/feature` pipeline (`PRINCIPLES.md`). The
browser pass covers 375 px and 1280 px with the switch ON and OFF.

**Phases that can overlap:** 1 and 2 share no files after phase 0, so they can run in parallel
lanes. 3 depends on 2 (`RecordHeader`). 4 depends only on 0.

**Risks:**

| Risk | Mitigation |
| --- | --- |
| Two looks for the same user during the waves | Tokens flip globally with the switch, so unmigrated screens differ only in structure, not in palette |
| `useUiVersion()` branches linger | The phase 5 grep is the gate; a branch older than phase 5 is a defect |
| Brand red reads as "error" | Danger is never a filled button (3.1); decision D1 |
| Sorting every column needs backend keys that do not exist (UNVERIFIED for every list) | Each phase 1 list lane measures it first and adds the key or states why not |

## 12. Decisions for the owner

The five questions are filed in the crew report. Each has a recommendation.

| # | Question | Options | Recommendation |
| --- | --- | --- | --- |
| D1 | Brand colour for the primary | (a) Sorento Red `#b44d2e` as `--primary`, danger kept apart by use; (b) keep today's blue and use Sorento Red only for the logo and active nav | **(a)**: it is the owner rule (R12), it passes AA, and the countdown pattern means danger is never a filled red button. Needs the real Sorento logo file |
| D2 | Dark mode | (a) Tokens now, dark visual QA only in phase 5; (b) dark QA in every wave; (c) drop dark | **(a)**: tokens cost nothing extra, and a per-wave dark pass doubles browser time for a mode few users pick |
| D3 | Density default | (a) Comfortable 36 px rows, 13 px text, no user option; (b) Compact 32 px; (c) a per-user choice | **(a)**: the mocks show 36 px still fits 20+ rows at 1280. Add a choice only when a user asks |
| D4 | Mobile bottom bar | (a) No bar; title in the 48 px top bar, drawer nav; (b) 4-tab bottom bar (Home, OIs, Search, Notifications) | **(a)**: a one-line grid needs every vertical pixel, and the drawer already gives navigation. Revisit if phone sessions pass about 20% of staff traffic |
| D5 | First wave and switch scope | (a) List archetype first, switch per user; (b) Detail first; (c) company-wide switch | **(a)**: `DataGrid` is in 271 files, so one wave changes the most screens, and a per-user switch lets the owner try v2 alone before anyone else sees it |
