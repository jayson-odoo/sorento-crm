# UI v2: discovery

Status: complete for review (lane UI-V2-PLAN, research round asked for by the owner on 11 Nov 2026, about 00:10:
"just need more thinking, more exploring, more investigating before we make the coding"). Research and design
only, no app code. Feeds the revision of `documentation/uiux/UI-V2-PLAN.md`.

- **Sources:**
  - the code on `main` at `6e6657e2`
  - the plans, UACs and reference docs under `documentation/`
  - the commit history (this clone is shallow: 58 commits, 9-11 Nov 2026)
  - a live walk of the app in this sandbox on seeded data (section 2)
  - desk research on four reference products (section 5)
  - the playbook gap audit `documentation/uiux/playbook-uiux-audit.md` (PR #2322, cited as `AUDIT`).
- **Paths:** frontend paths are relative to `sorento_crm_frontend/` unless they start with `documentation/` or
  `sorento_crm_backend/`. A count says how it was counted. "(inferred)" marks a claim read from labels or
  permission names rather than proven by running it.

## 0. Top 10 findings

1. **Every record looks different.** The walk found four record-header layouts:
   - **OI:** a generic page title ("Order Inquiry") above a header card holding the number, badge and actions.
   - **Product:** a generic title ("Product") above a large product name, with actions outside any card.
   - **Project:** the number small above the name.
   - **Quotation editor:** a `PageHeader` followed by a `RecordHeaderCard`.

   Each also carries a "Back to ..." button next to a 4-5 level breadcrumb. The owner's rule ("header like OI") exists
   only as one implementation out of four (`discovery-shots/oi-detail-1280.jpg`, `product-detail-1280.jpg`,
   `project-detail-1280.jpg`).
2. **The owner's grid rules are broken in bulk.**
   - 521 columns in 152 files switch server sort off (`enableSorting: false`).
   - 34 of the 144 list toolbars offer a single-select filter (the OI record's own "State" filter is one).
   - The rules live only in plans and crew memory: `DESIGN-LANGUAGE.md` carries none of them (section 3.2).
3. **dd/mm/yyyy is broken wherever a native date input is used.**
   - 60 files use `<input type="date">`, which draws the date in the BROWSER's locale.
   - On the walk, the quotation editor's Date field showed "11/10/2026" (month first) for 10 Nov
     (`discovery-shots/quotation-new-1280.jpg`).
   - Displayed dates are otherwise consistent: 68 walked pages show dd/mm/yyyy, and 2 admin pages show "d Mon yyyy".
4. **More than one filled button on 37 of 250 walked pages; the same CTA twice on 17.**
   - **Empty states:** they add a second copy of the CTA plus a feature explanation ("No bundles yet ... A bundle sells
     several products together ...", `discovery-shots/bundles-empty-1280.jpg`). That breaks two written rules: one
     CTA, and no explanations in the UI.
   - **Selected toggles:** a selected segment uses the same primary fill as a button (the TOGGLE-SELECTED rule,
     `DESIGN-LANGUAGE.md` section 4). So the OI list shows two filled blue controls ("Documents", "Outstanding") and
     no CTA at all.
5. **The hand-off between roles is where the screens fail** (section 4.10):
   - two primaries on OI, quotation and reorder at exactly the hand-off point
   - the next step hidden in an 11-item gear menu (`OrderInquiryDetail.tsx:824-957`)
   - a disabled reason a phone cannot show (`:892-902`).
6. **Records are wide and view/edit disagree.**
   - Tabs: the project has 10, the product 11 on view against a different 6 on edit, and a quotation spans 8 sub-routes.
   - System Settings puts 14 tabs on each of its 14 pages, and the General page is one card titled "Social Settings"
     (`discovery-shots/settings-general-1280.jpg`).
7. **History as a standard tab is true on 8 records out of about 63.** Five keep history in a sheet or drawer.
8. **The phone spends half its screen before the first row.** At 375 px:
   - **OI list:** the first data row starts at 458 px of an 812 px screen.
   - **Products and customers:** 374 px.
   - **OI record:** the first line row sits about 690 px down (`discovery-shots/oi-detail-375.jpg`).

   On desktop (1280) the OI list starts at 318 px and shows 13 rows.
9. **Plain words break at the edges.**
   - `handle_not_found` puts the model class name into user messages ("LookupSet not found. Someone might have
     deleted it already.", seen live on the project page). It does this for 17 call sites with CamelCase names such
     as `TeamMember`, `RespondContact`, `LookupSet` (`sorento_crm_backend/app/services/error_handler.py:36-42`).
   - Empty lists show "No data available" with a "1 - 0 of 0" pager on some screens and a proper "No X yet" on others.
   - 130 of 240 page titles are Title Case and 46 are sentence case; form labels split 144 / 63.
10. **We cannot rank screens by use, and two "owner rules" were not the owner's words.**
    - **No usage data.** The app records no page views, clicks or searches, and `api_call_log` excludes staff UI
      traffic by design (section 3.3).
    - **"No cards on the phone"** (AUDIT Q2) was decided by crew (commit `a0df2e6f`), and the owner's D4 answer now
      overrides it.
    - **"Side panel" vs "lightbox":** the owner has used the two words interchangeably ("i just need this as side
      panel (lightbox)", `documentation/plans/scm/PLAN-planning-why-12oct.md:76`).

## 1. Method

| Step | How | Limits |
| --- | --- | --- |
| Screen inventory | Every `app/(protected)/**/page.tsx` classified by route shape and source (`UI-V2-SCREEN-INVENTORY.md`, 469 pages) | First-pass archetype, corrected where a page was opened |
| Pattern counts | `rg -l` over `app components lib hooks` excluding tests; each count names its pattern | A file count, not a screen count; a shared component counts once |
| Live walk | The stack booted in this sandbox (`scripts/cloud-env-setup.sh`), bootstrapped schema plus a scratch seed (34 OIs, customers, projects, products; masked names), admin sign-in from `scripts/seed_never_stuck_smoke.py`; screenshots at 1280 and 375, light theme | No prod-copy data (crew rule): screens whose data the seed does not reach show their empty state, which is itself a finding |
| Journeys | Traced from code: route, button label with `file:line`, what opens, async waits (RQ queue + task), role | Click counts are estimates; roles are (inferred) from permission names |
| Pain evidence | Owner quotes in plans, UACs, reference docs, code comments citing owner hand tests, commit messages | Counts are upper bounds (a file mentioning the term and "owner") |
| Usage data | Backend models and middleware read for what is recorded | Nothing was queried: the sandbox has no real rows |
| References | Web search; vendor sites not reachable from the sandbox | Search-result level; (unverified) where it rests on product knowledge |

## 2. Screen walk

**How it was run.** 251 routes, every non-demo static route (240) plus 11 seeded records, at 1280 x 900 and
375 x 812, light theme, signed in as an admin with every module enabled. Every page was measured in the browser:
- title text, size and case
- filled buttons in the primary colour
- breadcrumb
- tab count
- grid header, first-row height and cell text size
- date formats in the page text
- page-level sideways scroll
- console errors.

**Evidence:**
- **Measurements:** all 501 page measurements are in `documentation/uiux/discovery-walk.csv`.
- **Screenshots:** 18 representative ones are in `documentation/uiux/discovery-shots/` (`<screen>-1280.jpg` / `<screen>-375.jpg`).
- **Limits:**
  - Data comes from the scratch seed only, so most lists show their empty state.
  - The first row of an empty grid measures 69 px: the empty-state row, not a data row.
  - The filled-button count also catches selected toggles and switches, so it is read together with the labels.

### 2.0 What the walk measured

| Measure | Result (desktop, 250 pages) |
| --- | --- |
| Page title size | 20 px on all 240 pages that have one; 9 pages have no `h1` (e.g. `/my-requests`, `/sla-management/kpi-dashboard`, `/system-management/mcp-tools`) |
| Title case | Title Case 130, sentence case 46, single word 64 ("Root Causes", "Create Complaint" vs "Stock position", "Register a project") |
| Breadcrumb | Always starts at "Dashboards"; depth 3 on 93 pages, 4 on 122, 5 on 13; the last crumb differs from the title on 22 pages ("Goods Receipt Notes" vs "GRN", "Products" vs "All Products", "Supply Chain" vs "Dashboard"); OI sits under "Procurement > Supply Chain" |
| Filled primary-colour controls | 0 on 69 pages, 1 on 131, 2+ on 37 (of which the same CTA twice on 17: header + empty state) |
| Grid | 152 pages: header 40 px on 146, cell text 14 px on all 152; data rows 44 px (OI list) |
| Tabs | 14 tabs on all 14 System Settings pages; 11 product; 10 project; 8 SCM policies |
| Dates in page text | dd/mm/yyyy on 68 pages; "d Mon yyyy" on 2 admin pages; native date inputs draw month-first in an en-US browser |
| Phone sideways page scroll | 2 pages (`/procurement-management/grn/new`, `/system-management/activity`) |
| Phone first row (375 x 812) | OI list 458 px, products / customers 374 px, complaints 334 px; OI record about 690 px |
| Console errors | 404 on 16 pages, 403 on 6, 400 on 4, 500 on 3, 503 on 2 (empty-DB conditions included) |

### 2.0.1 Inconsistencies seen on screen

| # | What | Where (screenshot / code) |
| --- | --- | --- |
| W1 | Four record-header layouts (section 0, item 1) | `oi-detail`, `product-detail`, `project-detail`, `quotation-new`; `components/common/RecordHeaderCard.tsx`, `master-data-management/products/[id]/components/ProductDetail.tsx`, `PS/[projectId]/components/ProjectDetailClient.tsx`, `quotation-documents/components/QuotationFormClient.tsx:895,999` |
| W2 | A generic page title ("Order Inquiry", "Product", "Project") above the record's own identity: two headings per record | same screenshots |
| W3 | "Back to ..." button next to a 4-5 level breadcrumb: two ways back, both on screen | OI, product, project, brand create |
| W4 | CTA placement varies: in the `PageHeader` (OI), inside the grid card's toolbar (complaints "Create", bundles "New bundle"), repeated in the empty state (bundles, flyers, tile designs, teams, opportunities) | `complaints-list-1280.jpg`, `bundles-empty-1280.jpg` |
| W5 | Rows per page: 25 on OI, 50 on complaints | `oi-list-1280.jpg`, `complaints-list-1280.jpg` |
| W6 | Empty grid: "No data available" + "1 - 0 of 0" vs "No bundles yet" + hint + button | `complaints-list`, `bundles-empty` |
| W7 | Record "Quick Info" side card repeats the Overview tab and disagrees with it (category "Sanitaryware" vs the code "UIV2-SAN"); price as "MYR 1,120.00" where the rest of the app writes "RM" | `product-detail-1280.jpg` |
| W8 | Create as a full page with a card that repeats the page title ("Create Brand" twice), help text under fields, and two different switch styles on one form | `brand-create-1280.jpg` |
| W9 | Native date input renders "11/10/2026" for 10 Nov | `quotation-new-1280.jpg`; 60 files with `type="date"` |
| W10 | Technical 404 text in a toast ("LookupSet not found ...") | `project-detail-1280.jpg`; `error_handler.py:36-42` |
| W11 | Settings: 14 tabs, a "Social Settings" card holding General, explanatory field help ("Toggle the switch to enable or disable the store's active status.") | `settings-general-1280.jpg` |
| W12 | Phone list toolbars collapse to unlabelled icon buttons (filter, columns, export, refresh) | `complaints-list-375.jpg` |
| W13 | Phone record: breadcrumb wraps to two lines, then the back button, the header card, the tabs and a search box before the first line | `oi-detail-375.jpg` |
| W14 | Floating elements at the bottom right: the AI assistant tab on every page, plus a second floating button on the project page | `project-detail-1280.jpg` |
| W15 | IDs in a different font from the rest of the row (the OI number is monospace on the list and the record) | `oi-list-1280.jpg`, `oi-detail-1280.jpg` |

### 2.1 Pattern counts today (static)

| Pattern | Variants today | Count |
| --- | --- | --- |
| List container | `DataGrid` / `PanelDataGrid` / `ui/table` / raw `<table>` | 271 / 50 / 35 / 79 files |
| List toolbar | `DataGridListToolbar` / per-page hand-built / dead `ListPageToolbar` | 144 / rest / 0 |
| List filter | single-select vs multi-select inside a list toolbar file | 34 vs 73 files |
| Sort off | `enableSorting: false` | 521 columns in 152 files |
| Page title | `PageHeader` / Metronic `Toolbar` / raw `<h1>` / bespoke headers | 322 / 84 (52 demo) / 14 pages / 3 |
| h1 size | `text-lg` / `text-xl` / `text-2xl` on a raw `<h1>` | 15 / 17 / 15 |
| Record header | `DetailActions` / `RecordHeaderCard` / `RecordNavigation` | 63 / 3 / 19 files |
| History | tab / sheet-drawer-panel | 8 / 5 files |
| Status pill | `Badge` / `STATUS_PILL_BASE` / bespoke `*Status*Badge` components | 563 / 56 / 15 |
| Confirm | `DeferredActionButton` / `ConfirmDeleteDialog` (retired) / `alert-dialog` hand-rolled / "Are you sure" | 7 / 26 / 96 / 29 files |
| Side panel vs dialog | `ui/sheet` / `ui/dialog` / vaul `ui/drawer` | 44 / 353 / 4 files |
| Form plumbing | `react-hook-form` `useForm` / `ui/form` `FormField` / `FormSection` / `FormDialogScaffold` | 87 / 64 / 4 / 7 files |
| Form label case | Title Case (`<FormLabel>Shop Name`) vs sentence case (`<FormLabel>Default supplier`) | 144 vs 63 labels |
| Dates | 11 helpers in `lib/helpers.ts` + 34 local formatters + 17 files on date-fns `format` + 75 on `toLocale*String` | see plan section 6.1 |
| Upload | `FileDropzone` / portal `AttachmentDropzone` / `ResponseAttachmentDropzone` / raw `type="file"` | 38 / 3 / 2 / 15 files |
| Image | `AttachmentImage` / raw `<img>` / `next/image` | 3 / 203 files (350 tags) / 0 |
| Charts | recharts / apexcharts | 4 / 8 (5 demo) files |
| Tooltip | `ui/tooltip` / native `title=` on elements | 35 files / about 1,446 elements |
| Tabs per record (max) | product view 11, product form 6, project 10, SO 6 | `<TabsTrigger` per file |

### 2.2 Grid density today (measured from code)

- Body rows: a 44 px minimum (`h-11`), padding `px-4 py-2` (`components/ui/data-grid-table.tsx:130-141`).
- Header: 40 px (`h-10`, `:343`).
- Text: 14 px (`text-sm`, `:199`).
- Only 4 lists opt into `dense` (32 px header, `px-2.5 py-2`).

The owner's D3 answer ("isn't it now quite good?") keeps this. The first plan's 36 px / 13 px proposal is
withdrawn, and the mocks are redrawn at today's values.

## 3. Evidence of pain

### 3.1 What the owner has already said (verbatim, with source)

| Theme | Sources | Strongest quotes |
| --- | --- | --- |
| Too complicated, bloated | about 23 files | "too complicated", "very bloated" (`documentation/plans/project-sales/CARD-project-party-roles-10nov.md:178`); "the mockups are way too complicated, it is very taxing for the users, please simplify that" (`documentation/plans/projects/PLAN-po-schedule-redesign-24sep.md:102`); "OI history why so complicated geh ... i want to reuse same component though" (`documentation/plans/audit/PLAN-standard-history-10nov.md:5-6`); "I want to keep the first page lean" (`documentation/plans/projects/CARD-project-name-10nov.md:21-23`); "too many information" (`documentation/plans/sales/sales-targets-opportunities-26sep-acceptance-criteria.md:67`) |
| One line per row, +N pills | many (noisy) | "i want to keep each row as 1 line, if got more need to use +x pill, the details can be viewed if we go inside" (`sales-targets-opportunities-26sep-acceptance-criteria.md:68`); "I want all rows to have 1 line only, then I can click on the PO and SPO to view the lightbox popup" (`documentation/plans/scm/PLAN-scm-oi-sheet-pairing-repair.md:279-281`) |
| Grid behaviour | several | "server sort for every column ..., multi-select filters" (`documentation/plans/portal/PLAN-portal-p4-requests-28oct.md:61`); "flexible group by and multiple layers of group by la, Odoo style" (`documentation/plans/inventory/PLAN-stock-groupby-18oct.md:10-11`); ticking rows "means clicking every checkbox one by one" (`documentation/plans/design-system/PLAN-grid-drag-select.md:7-8`); "use our existing multi select component, not a bloated picker" (`documentation/plans/scm/PLAN-order-sheet-oi-reports-22sep.md:199`) |
| Dialog vs page vs panel | several | "i don't need this page, i just need this as side panel (lightbox)" (`PLAN-planning-why-12oct.md:76`); "1 tab just like SO or PO ... Not a gear drawer" (`PLAN-standard-history-10nov.md:11-12`); TownPanel Sheet became TownLightbox (commit `03be747b`) |
| Navigation | 6 | stay on the same tab across prev/next (`hooks/useUrlTab.ts:6`); "2 breadcrumbs confusing" (`documentation/plans/PLAN-audit-traversal-todo.md:268`); Back to list restores the exact row (`DESIGN-LANGUAGE.md:218`) |
| Dates | about 100 | "all the dates need to use dd/mm/yyyy format like a standardized format across the system" (`documentation/plans/design-system/PLAN-date-format-unify-04nov.md:6`) |
| Stuck, slow, technical | several | "I don't want anything stuck in the system" (`documentation/reference/NEVER-STUCK-UI.md:4`); Confirm "sits on the Review split skeleton for a very long time", 36-46 s (`documentation/plans/fulfilment/PLAN-confirm-dialog-speed-3nov.md:7-9`); "if 404 just show properly don't show too technical message" (`PLAN-po-schedule-redesign-24sep.md:108`); "The worklist page is slow on prod" (`documentation/plans/scm/oi-worklist-one-header-acceptance-criteria.md:41`) |
| Phone | 0 verbatim complaints found | "375" appears in about 517 files, almost all test or evidence references |

**Reading.**
- The owner's taste is consistent: lean, one line, one component reused, a popup for detail, nothing stuck, plain
  error words.
- None of the recorded complaints is about colour, fonts or decoration. That is why v2's visual changes are kept
  small (theme system, same density) and its structural changes (fewer tabs, one primary, one history, one
  filter model) carry the weight.

### 3.2 Owner rules: written vs not written

- **Written into the contract:**
  - One CTA, no subtitle, no button in an empty state (`DESIGN-LANGUAGE.md:203`, type-enforced in
    `components/common/PageHeader.tsx:60` and `components/ui/data-grid.tsx:130`).
  - Every list a DataGrid (`DESIGN-LANGUAGE.md:156`).
  - Back to list restores the row (`:218`).
  - Tab kept across prev/next (`hooks/useUrlTab.ts:6`).
  - Never stuck (`NEVER-STUCK-UI.md`).
  - Deferred delete (`PRINCIPLES.md:255-265`).
  - Every dropdown searchable (`PRINCIPLES.md:336-338`).
- **Written only in plans or crew memory:**
  - dd/mm/yyyy (only in `PLAN-date-format-unify-04nov.md`)
  - one line per row
  - server sort on every column
  - multi-select filters
  - right-click row menus
  - dialog over side panel
  - header like OI
  - CRM form = portal form
  - one image pipeline
- **One live contradiction:** `DESIGN-LANGUAGE.md:186` (D15) describes a row "..." menu, while the owner asked for
  right-click menus and no row icons. The plan resolves it: right-click/long-press replaces "...". The D15 text
  changes with phase 0.

### 3.3 Usage data: what exists

| Source | Model | Tells us | Does not tell us |
| --- | --- | --- | --- |
| `audit_logs` | `sorento_crm_backend/app/models/audit.py:32-104` (`source`, `event`, `user_id`, `changed_at`) | Which records and actions staff WRITE most, per channel (`ui`, `portal`, `chatbot`, `mcp`) | Reads, page views |
| `user_sessions` | `app/models/user_session.py:27-56` (`user_agent`, `last_seen_at`) | Phone vs desktop share of active users | Per-page phone use |
| `user_list_column_configs`, `saved_views` | `app/models/user.py:868-887`, `app/models/saved_view.py:36-52` | Which lists people bothered to tailor | How often they open them |
| `client_error_report` | `app/models/client_error_report.py:18-42` (30-day retention) | Which pages crash | - |
| `user_downloads` | `app/models/download.py:26-73` (`created_at`, `ready_at`) | Export volume and the real wait | - |
| `ai_assistant_usage_logs`, `unanswered_queries`, `wishlist_clusters` | `app/models/ai_assistant.py:144-276` | What staff ask the assistant and where it fails them | - |
| stdout request log | `app/middleware/logging_middleware.py:73-77` | Hottest endpoints and their duration (Docker log retention only) | User, page |
| `api_call_log` | `app/models/api_call_log.py:22-61` | MCP and n8n traffic only | **Staff UI traffic (excluded on purpose)** |
| Frontend analytics | none (no posthog, gtag, sentry, web-vitals, `track(`) | - | Everything |

**Consequence for the program.** Phase 0 adds a minimal page-view record before any wave is ordered by use: route,
user, viewport class, timestamp, and the time to first data. The waves are then sequenced on data, not on guesses.
Until it has two weeks of data, the order falls back to the journey ranking in section 4.

## 4. Staff journeys

Ranked by evidence:
- frontend commits per folder in the last 120 days: project sales 332 + 316, product master 212, reorder 209, price
  tags 142 + 129, OI 87, stock debt 49
- plans per domain: scm 1486, dealer-kit 758, project sales 577
- the sidebar.

`PS` = `app/(protected)/project-sales`.

| # | Journey | Roles | Page hops | Dialogs | Clicks (happy path, est.) | Async waits |
| --- | --- | --- | --- | --- | --- | --- |
| J1 | Project register -> approve -> move stage | sales, approver (inferred) | 3-4 | 0-2 | 10-14 | - |
| J2 | Proposal / quotation create -> approve -> send -> export | sales, approver | 3 | 1-3 | 8-12 + lines | PDF/XLSX on RQ `imports` |
| J3 | Build SO -> publish (raises the OI) | project sales | 2 | 3 | about 7 | import file for AutoCount |
| J4 | OI confirm -> request reserve -> reserve | purchasing -> sales -> CS | 1 | 2 + one per line | 6 + 2 per line | reserve email; Excel on RQ |
| J5 | Stock debt snapshot -> decide | planner (inferred) | 1-2 | 2-3 stacked | 6-10 per product | Excel on RQ |
| J6 | Price tag request -> design -> approve (portal) -> print -> collect | sales -> marketing -> sales (portal) -> office | 3-4 | 2-4 | 15+ | Respond.io notify; tag sheet PDF on `catalogue_render` |
| J7 | Reorder plan -> decide -> confirm to draft POs | buyer | 1-2 | 2 + 1 sheet | 3 + 2 per row + 3 | `run_reorder_job` on RQ, polled |
| J8 | GRN import -> review | procurement (inferred) | 2-3 | 2 | about 10 | RQ `imports`, result in Import jobs |
| J9 | Product master edit | master data (inferred) | 2-3 | per sub-entity | about 6 + fields | - |

### 4.1 J1 Project registration

**Path:**
1. Projects (`PS/pipeline/.../PipelineClient.tsx:390,397`, "Start" then "Register a project").
2. `/project-sales/new` wizard (`PS/_shared/components/ProjectForm.tsx`: "Check" `:1097`, "Next" `:1085`, "Register project" `:1134`).
3. Project page (`PS/[projectId]/components/ProjectDetailClient.tsx`).
4. The approver's Approve (`:723`).
5. The single stage button (`ProjectStatusAction.tsx:135`).

**Stalls:**
- 10 tabs (`ProjectDetailClient.tsx:102-113`).
- The duplicate check runs twice: at Check, and again at Approve with "Already registered as ..." (`:452-466`).
- Moving to Sample Submission or Sponsorship throws the user into another module's create page (`:124-125`).
- Edit, Reassign, Mark won and Lost all sit in the gear (`:374-424`).

### 4.2 J2 Quotation

**Path:**
1. Proposals tab, "Add a proposal" (`QuotationsPanel.tsx:319-330`).
2. Editor (`quotation-documents/components/QuotationFormClient.tsx`, 1,510 lines, autosave `:902`, "Save quotation" `:961`).
3. Document view (`QuotationDocumentClient.tsx`): "Send for approval" `:590`, then Reject + Approve `:602,610`, then
   "Send to Customer R{n}" with Email / WhatsApp `:621-638`.

**Stalls:**
- 8 view sub-routes (`[documentId]/(view)/*`).
- Two equal-weight approval buttons.
- Revise asks twice: a dialog before the form, plus a gear duplicate (`:352-355,380-414`).
- Download is queue-then-collect, and only after sending (`actions.tsx:168`, `QuotationDocumentClient.tsx:552-562`).
- A second tab on the same draft goes read-only with a "Reload" button (`QuotationFormClient.tsx:969-978`).

### 4.3 J3 Sales order publish

**Path:**
1. SO tab, "Build drafts" (`SalesOrdersPanel.tsx:469-471`), then the build dialog (`SalesOrderBuildDialog.tsx:89,189`).
2. Draft, "Publish" (`SalesOrderDetailClient.tsx:569-572`).
3. "Publish {ref}?" (`SalesOrderPublishDialog.tsx:225`).
4. Result dialog with "Download the import file" (`:193-203`).

**Stalls:**
- The AutoCount import is a manual hand-off outside the CRM (inferred).
- A lost import file means "Reload the sales order" (`:205-207`).

### 4.4 J4 Order inquiry

**Path:**
1. List (`order-inquiries/components/OrderInquiriesClient.tsx`, 2,484 lines, about 15 URL filters `:410-518`).
2. Detail tabs Lines / General / Related PO / Related SPO / History (`OrderInquiryDetail.tsx:1001-1022`).
3. Purchasing "Confirm (n)" (`:655,969`).
4. Sales, gear, "Request CS to reserve" (`:889`), then `RequestReserveDialog` "Send request" / "Park request"
   (`PS/_shared/components/RequestReserveDialog.tsx:363,420`).
5. CS, pencil per line, `ReserveLineForm` dialog (`orderInquiryHeaderLinesColumns.tsx:439-441`).
6. "Reserve (n)", then `ReserveConfirmDialog` (`:287-290`).

**Stalls:**
- Two primaries (`:963-984`).
- The request sits in an 11-item gear (`:824-957`).
- The disabled reason is hover-only (`:892-902`).
- One dialog per line before the batch Reserve.
- The same OI appears in a second list with different columns and actions ("Mark actioned", "Cancel rows", "Reopen",
  `PS/[projectId]/order-inquiries/components/OrderInquiryClient.tsx:399-414`).

### 4.5 J5 Stock debt

**Path:**
1. Board (`PS/stock-debt/.../StockDebtClient.tsx`, "Snapshots", "Save snapshot" `:714-720`).
2. Snapshot dialog (`SaveSnapshotDialog.tsx:99`).
3. Snapshot page, then either the per-row "Decide" popover (`SnapshotDecisionPopover.tsx:101-190`) or the drill dialog
   "Decide (n)" with Request CS to reserve / Link to PO / Unlink / Move PO (`SnapshotDrillDialog.tsx:306-320`).

**Stalls:**
- Dialogs stack.
- There are two different decide UIs.
- The user must snapshot before deciding.
- Stock and PO columns hide behind a toggle (`StockDebtClient.tsx:705`).

### 4.6 J6 Price tag request

**Path:**
1. Raise in the portal form rendered inside the CRM (`dealer-kit/price-tag-requests/new/page.tsx`,
   `app/(auth)/portal/components/PriceTagRequestForm.tsx`, 2,675 lines; footer "Save Draft" / "Escalate to marketing" /
   "Approve" `:2509,2519,2531`).
2. Marketing detail: "Claim", "Design tags", designer route `[id]/design`, "Mark design ready (n open)"
   (`priceTagRequestActions.ts:71,73,90-93`).
3. Salesperson reviews in the PORTAL via a Respond.io link (`PriceTagRequestForm.tsx:1847-1855`).
4. "Export PDF" on `catalogue_render` (`sorento_crm_backend/app/services/dealer_kit/tag_sheet_export_service.py:324-329`).
5. "Mark ready for collection", then "Mark collected".

**Stalls:**
- Approval lives in a different app.
- Each tag's "Design" leaves the page (`PriceTagRequestDetail.tsx:1337-1345`).
- A tab labelled "Sales Order" holds attachments (`:930-933`).
- The printing choice is only in the gear's "Edit request" dialog, and the office hand-off button waits on it
  (`:848-857`, `priceTagRequestActions.ts:97-105`).
- Three equal-looking footer buttons.

### 4.7 J7 Reorder plan

**Path:**
1. "Start Plan" (`scm/reorder/.../ReorderRunsGrid.tsx:329`), then `RunPlanningModal`.
2. The plan page polls "Building the plan" (`ReorderPlanView.tsx:254-272`; `run_reorder_job`,
   `sorento_crm_backend/app/services/scm/reorder_run_service.py:222`).
3. Each row expands to `PlanRowPanel` (`PlanLinesGrid.tsx:607`).
4. "Save (n)", then "Confirm (n)" (`PlanLinesSection.tsx:237-258`).

**Stalls:**
- A spinner with no progress detail.
- Unsaved decisions depend on a leave-page guard (`ReorderPlanView.tsx:64,111-119`).
- Two primaries.
- The next step (PO worklist) is in the Actions menu.
- The low stock report leaves the plan (`:140-170`).
- Exceptions review in a side Sheet (`PlanExceptionReviewSheet.tsx`).

### 4.8 J8 GRN

**Path:**
1. List menu "Upload GRN", then separately "Upload GRN Lines" (`procurement-management/grn/.../GRNList.tsx:276,283`).
2. Dialog "Test" then "Upload" (`GRNImportDialog.tsx:162-172`).
3. Toast "View job", which goes to `/system-management/import-jobs/{id}` (`:60-64`).
4. GRN detail "Edit" (`GRNDetail.tsx:186-187`).

**Stalls:**
- Header and lines are two uploads.
- The result lives in another module.
- An empty GRN only says "Import lines or edit the GRN" (`GRNDetail.tsx:287`).

### 4.9 J9 Product master

**Path:**
1. List (`master-data-management/products/.../ProductsList.tsx`, 1,334 lines).
2. Detail with 11 tabs (`ProductDetail.tsx:319-362`).
3. "Edit" (`:197-205`) goes to a separate page with 6 different tabs (`ProductForm.tsx:325-351`).
4. "Update Product" (`:1100-1108`).

**Stalls:**
- View and edit tab sets differ.
- Combos, accessories and variants are edited only from view tabs through their own dialogs (`[id]/components/AddComboModal.tsx`).
- The form's default after save goes to the list, not the record (`ProductForm.tsx:274`, overridden at `[id]/edit/page.tsx:71`).

### 4.10 What the journeys share

1. **Hand-offs between roles have no shared inbox.** OI goes purchasing -> sales -> CS. Price tag goes sales ->
   marketing -> portal -> office. Each role finds the record through a list filter, an email or a Respond.io link.
   The point of hand-off is exactly where two primaries appear.
2. **Exports are queue-then-collect** everywhere. v2 needs one "your file is ready" pattern with a link in the toast,
   not a separate drawer hunt.
3. **The gear holds next steps, not just secondary actions.** v2's rule: the step the record's state is waiting on is
   the primary. When a role cannot do it, the primary is replaced by a status line saying who it waits on, with no
   button.
4. **Tabs are used as a filing cabinet.** 10-11 tabs on a record means the user hunts. v2 caps tabs (section 6 of the
   plan) and moves the rest into the record's sections or a lightbox.
5. **Long waits** (reorder build, Confirm review split at 36-46 s, PDF renders) show spinners, not progress. The
   never-stuck rule bounds them, but v2 should show what is happening.

## 5. Reference products

(Desk research; vendor sites were not reachable from this sandbox, so claims come from search results with the
source named; (unverified) marks product knowledge without a source.)

| | AutoCount (desktop, Cloud) | Odoo 17/18 | Linear | Attio |
| --- | --- | --- | --- | --- |
| Why it matters | The tool users already know | The reference the owner cites ("Odoo style") | The bar for speed and selection | A modern CRM record |
| Grid | Header-menu sort, drag-to-group bar, Column Chooser (autocountsoft.com helpfile `column_functions.htm`) | Tick rows, then Actions; "Select all N" (unverified); shift ranges only via an OCA add-on (PyPI `web_listview_range_select`) | Shift / Cmd ranges, X from the keyboard, right-click on the selection, bottom bulk bar (linear.app docs `select-issues`) | Header checkbox selects the view; stacked filters saved as views; arrow-key cells (attio.com help) |
| Record | Full-window tabbed entry, header above a line grid (helpfile `introduction.htm`) | Status bar top right; chatter merges tracked changes, notes, messages (cybrosys blog, Odoo 17) | Properties column, activity under description (unverified) | Fixed tabs, Activity timeline filterable by event type (attio.com help) |
| Theming | Not documented | Dark since 17, persistence buggy in 18 (odoo forum 283904); brand colours via third-party module | Presets + custom; themes generated in LCH from base, accent, contrast (linear.app `custom-themes`, "How we redesigned the Linear UI") | Not documented |
| Phone | Fewer features than web (AC Payroll notes) | Lists become cards (unverified); pickers in bottom sheets (19 release notes) | Bottom toolbar, Create on every screen, customisable (changelog 2025-10-16, 2026-01-22) | Create/update, Activity tab (changelog 2026) |
| Big UI change | Cloud shipped as a separate product (2021) | Hard version upgrades, no switch-back (unverified) | Forced switch in 2024; old colours could be re-applied (changelog 2024-03-20) | - |

### 5.1 What to borrow, what to avoid

| Product | Borrow | Avoid | Reason (owner rule) |
| --- | --- | --- | --- |
| AutoCount | Column Chooser with a saved layout (we already save server-side); header above a line grid for documents | Drag-to-group bar as a default control; many windows at once; new version as a separate product | Minimal UI; one app with a per-user switch |
| Odoo | Explicit "Select all N records" banner with server-side bulk; one search bar holding filter chips; History merging tracked changes "old -> new" with notes; status in the header | Bulk actions only behind a hidden Actions menu; chatter as a permanent side panel; theme in a cookie | Odoo-like selection; dialog over side panel; per-user theme on the server |
| Linear | Right-click acting on the selection plus a bottom bulk bar; theme generated from ONE brand colour in a perceptual space (safe light and dark); presets + custom in settings; phone bottom toolbar with a fixed create | Very low-contrast chrome; shortcut-only actions; forced switch with no way back | Right-click menus; customisable brand (D1); per-user version switch (D5) |
| Attio | History tab filterable by event type; fixed tab set on every record; saved views; Cmd+K acting on the current selection | Admin-configurable record tabs; inline cell editing in lists; ambiguous header checkbox | History on every record; one line per row; modal edit |
| Salesforce, Jira, GitHub (rollout) | Per-user switch stored on the server, admin can grant or withdraw, an in-page "switch back", a published end date for the old UI only after the new one has been default for a while | A forced cut-over | Owner D5: "the user can go back to each version" |

### 5.2 The Foundryx playbook

**Source:** through `AUDIT` only. The private repo is not readable from this sandbox, and the phone sections were
asked for (PR #2323 crew-ask).

**What it adds that the four products do not:** plain-words states (blocked reason, no-access naming who can grant
it), dialog wording, per-file upload rows, and a phone layout (condensing top bar, floating main action, stacked
cards, selection bar).

**Phone:** per the owner's D4, the phone follows the playbook, so its phone rules replace AUDIT Q2 on the phone.
Desktop keeps one line per row.

## 6. What this changes in the plan

See `UI-V2-PLAN.md` (revision 2) for the full program. In short:

1. **Theme system, not a recolour** (D1): blue stays the default ("Sorento blue"), and the brand palette and mode
   are selectable (presets + custom colour) from tokens generated from one colour.
   - **Found on the way:** today's filled primary `blue-500` with white text is 3.7:1, below WCAG AA for 14 px text.
     The generator has to fix that (decision Q1).
2. **Density unchanged** (D3): 44 px rows, 14 px text, 40 px header.
3. **Dark mode QA in every wave** (D2).
4. **Phone per the playbook** (D4): cards where the playbook says cards, plus a bottom bar, a floating main action
   and a bottom selection/filter bar. Desktop stays one line per row.
5. **A complete parallel v2 behind a per-user version switch** (D5), owner first, with nothing released to staff
   until every archetype passes its exit criteria.
6. **New from discovery:**
   - **Page-view telemetry** first (phase 0).
   - **A "waiting on" pattern** for multi-role hand-offs.
   - **A tab budget per record.**
   - **One export pattern** ("ready" toast with the file).
   - **Stacked-dialog ban.**
   - **The owner rules into `DESIGN-LANGUAGE.md`** with lint/inventory guards for sort-off and single-select filters.
7. **New from the screen walk:**
   - **One record header.** The record's own identity is the page heading: no generic "Order Inquiry" / "Product"
     title above it, and no "Back to ..." button beside a breadcrumb (W1-W3).
   - **Breadcrumb = sidebar path.** It no longer starts at "Dashboards" and its last crumb is the page title (22
     mismatches today).
   - **Empty states carry no button and no explanation.** The checker counts filled controls per page (W4, W6).
   - **The native date input is banned.** A lint rule replaces it with `DatePicker` (60 files, W9).
   - **`handle_not_found` takes a human label,** never a class name (W10). It is one backend line plus 17 call sites,
     and can ship before v2 as a small-fix lane.
   - **Selected toggles drop the primary fill** (Q4).
   - **Sentence case everywhere** (130 Title Case titles, 144 Title Case labels), done screen by screen in the waves.
   - **The phone record and list put data first:** the condensed top bar holds the identity, and filters and search
     sit in one bar (W12, W13).

## 7. Open questions

| # | Question | Why it matters | Recommendation |
| --- | --- | --- | --- |
| Q1 | Default blue: keep `blue-500` exactly for filled buttons, or the AA-safe step the generator picks (`#246bdd`, 5.0:1)? | `blue-500` with white text is 3.7:1, below AA for 14 px text | AA-safe step: same hue, readable |
| Q2 | R7 "dialog / lightbox over side panels": retire every right-side Sheet on desktop (44 files), with bottom sheets only on the phone? | The owner once called a lightbox a "side panel (lightbox)" | Yes: dialogs and lightboxes on desktop, bottom sheets on the phone |
| Q3 | Phone list cards: one generic card layout derived from each list's columns (ID + status, then the next two columns), for every list? | 177 lists; per-list design would be the largest single cost | Generic for all, hand-tuned for the journey lists |
| Q4 | Selected toggles: keep the primary fill (TOGGLE-SELECTED rule) or use the soft tint with primary text? | The primary fill makes 2-3 filled controls per page and hides the one CTA (W4, 37 pages) | Soft tint |
| Q5 | May phase 0 add a page-view record (route pattern, user, viewport class, time to first data; 90-day retention)? | Without it the waves are ordered by guesswork; it is also the performance gate | Yes |
| Q6 | Theme ownership: company brand set by an admin plus each user's light/dark, or a per-user brand too? | Storage and settings screens | Company brand + user mode; no per-user brand until asked |
| Q7 | Default rows per page: 25 (OI) or 50 (complaints)? | Today both exist | 25 everywhere, user can change, remembered per list |
