# UI v2: discovery

Status: in progress (lane UI-V2-PLAN, research round asked for by the owner on 11 Nov 2026, about 00:10:
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

1. **The owner's grid rules are broken in bulk, not at the edges.**
   - 521 columns in 152 files switch server sort off (`enableSorting: false`), against "every column sortable".
   - 34 of the 144 list toolbars still offer a single-select filter (`SearchableSelect` next to `DataGridListToolbar`)
     against "every dropdown filter multi-select".
   - The rules exist only in plans and crew memory. `DESIGN-LANGUAGE.md` carries none of them, so no reviewer
     can hold a PR to them (section 3.2).
2. **"History as a standard tab" is true on 8 records out of about 63 detail pages.**
   - 8 files have a `value="history"` tab, while `DetailActions` (the record header) is used by 63.
   - Five records keep history in a sheet or drawer instead (`*History(Sheet|Drawer|Panel)`, 5 files).
3. **Every journey that passes between roles breaks the one-primary rule exactly where the hand-off happens**
   (section 4.10):
   - OI detail shows Confirm and Reserve both filled (`project-sales/order-inquiries/[id]/components/OrderInquiryDetail.tsx:963-984`).
   - The quotation shows Reject and Approve side by side (`.../[documentId]/components/QuotationDocumentClient.tsx:595-611`).
   - The reorder plan shows Save and Confirm (`scm/reorder/.../PlanLinesSection.tsx:237-258`).
4. **The most important action is often buried in the gear menu.**
   - On an OI, "Request CS to reserve" is one item in an 11-item gear (`OrderInquiryDetail.tsx:824-957`). Its
     disabled reason is a hover tooltip, which a phone cannot show (`:892-902`).
   - On a reorder plan, the PO worklist (the next step) sits in an Actions menu.
5. **Records are too wide, and view and edit disagree.**
   - A project has 10 tabs (`PS/[projectId]/components/ProjectDetailClient.tsx:102-113`).
   - A product has 11 on view and a DIFFERENT 6 on edit (`master-data-management/products/[id]/components/ProductDetail.tsx:319-362`
     vs `ProductForm.tsx:325-351`). That breaks the ADR's "view and edit are the same layout".
   - A quotation document is spread over 8 sub-routes (`[documentId]/(view)/*`).
6. **Every export is a two-step wait.** "Download PDF" queues an RQ job ("Prepared in My Downloads",
   `quotation-documents/actions.tsx:168`), and the file is collected from a separate chip or drawer. The same holds
   for OI Excel, stock debt Excel, tag sheets and the reorder report (section 4). Nothing downloads at the click.
7. **Dialogs stack and patterns fork.**
   - Stock debt opens a reserve or PO-link dialog ON TOP of the drill dialog (`PS/stock-debt/.../SnapshotDrillDialog.tsx:306-320`).
   - The same decision has two different UIs: a popover vs the drill menu (`SnapshotDecisionPopover.tsx:101-190`).
   - 96 files import `alert-dialog`, and 26 still use the retired `ConfirmDeleteDialog`.
   - "Are you sure" appears in 29 files.
8. **The owner's recurring complaint is complexity, not looks.** About 23 plan files record the owner calling
   something "too complicated", "very bloated" or "too many information" (section 3.1). The fixes they asked for are
   all subtraction: fewer fields, one line per row, a popup instead of a page, reuse the same component. v2 has to be
   judged on that, not on new visual effects.
9. **We cannot rank screens by use today.**
   - The app records no page views, no clicks and no search queries, and has no frontend analytics.
   - `api_call_log` excludes staff UI traffic by design (`sorento_crm_backend/app/middleware/api_call_log_middleware.py:30,55-62`).
   - What exists measures writes (`audit_logs.source='ui'`), sessions (`user_sessions.user_agent`, giving phone share)
     and tailored lists (`user_list_column_configs`) (section 3.3).
   - The plan's earlier "top 10 lists by `api_call_logs`" was wrong and is withdrawn.
10. **Two "owner rules" in the first plan were not the owner's words.**
    - "No cards on the phone" (AUDIT Q2) was decided by crew with the owner informed after (commit `a0df2e6f`). The
      owner's D4 answer ("follow the playbook") now overrides it.
    - The owner uses "side panel" and "lightbox" interchangeably at least once: "i just need this as side panel (lightbox)"
      (`documentation/plans/scm/PLAN-planning-why-12oct.md:76`). So R7 needs a precise reading before v2 retires every
      Sheet (decision Q2 in section 7).

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

(Filled in from the live walk; see section 2.4 for the measured shell and grid.)

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

## 7. Open questions

| # | Question | Why it matters |
| --- | --- | --- |
| Q1 | Default blue: keep `blue-500` exactly, or the nearest AA-safe step (`blue-600`, 5.2:1) for filled buttons? | `blue-500` with white text fails AA (3.7:1) |
| Q2 | R7 "dialog / lightbox over side panels": does it retire every right-side Sheet, or only full-page side panels? | The owner once called a lightbox a "side panel (lightbox)" |
| Q3 | Who picks the theme: the company (admin sets brand) with users picking only light/dark, or each user picks a preset too? | Decides storage and the settings screens |
| Q4 | Phone list: playbook cards for every list on the phone, or cards only for the top journeys and the grid for the rest? | Effort scales with the number of lists (177) |
| Q5 | May phase 0 add a minimal page-view record (route, user, viewport class, time to data)? | Without it the waves are ordered by guesswork |
