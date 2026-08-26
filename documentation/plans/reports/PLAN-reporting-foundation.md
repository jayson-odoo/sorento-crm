# PLAN - Reporting foundation (Sponsorship report as report #1)

Status: S1 (Phase 1, frontend against mocks) BUILT and browser-verified 2026-08-26 on
branch `feat/reporting-foundation`. S2 onwards not started.
UAC: reporting-foundation-acceptance-criteria.md (governing)
Source: `Sorento/phase-2/User Requirements/Project/SPONSORSHIP REPORT JAN-Dec'25.xlsx`
Review artifact: `.lavish/reporting-foundation.html`

## Why a foundation and not a page

The workbook is 12 identical monthly detail tables plus one pivot (sales agent x month,
two measures) over the same rows. Every operational report the client will ask for next
decomposes the same way: a flat dataset, then a layout over it. Scale here means the number
of reports, not row volume (~214 sponsorship forms a year), so the design optimises the
marginal cost of report #2: one dataset function + one definition + one permission seed,
and a two-line route wrapper. No BI tool (second auth, no company scoping, cannot emit the
client's formatted workbook); no user-built designer (weeks, unasked for). Definitions are
JSON-serialisable, so moving them into a table later is a migration, not a rewrite.

## Decisions taken (user, 2026-08-26)

1. **Month bucket = `approved_at` by default**, and the date basis is a user filter
   (approved / form date `request_date` / submitted `submitted_at`).
2. **Default statuses = approved + processed_by_cs**; the status filter can widen.
3. **OTHERS column dropped** (empty in all 12 sheets).
4. **Sponsorship dataset is company-agnostic** (`scope="none"`, declared explicitly).
   `purchase_requests` has no `company_id`, and 0 of 48 forms link to a project, so scoping
   through the project (as `sponsorship_link_service` does) would blank the report.
5. **2025 workbook is loaded on the LOCAL copy only**, as a verification fixture. Never
   prod. Prod reporting starts from 2026.
6. **Navigation under the owning module**: sidebar Procurement > Sponsorship Forms >
   Report, plus a Report button on the Sponsorship Forms listing toolbar. No top-level hub
   in v1; the catalog endpoint stays so one can be added later.
7. **Saved views are personal + shared**: a holder of `reports.views.publish` can publish a
   view as shared and mark one shared view the default for everyone.
8. **Configurability is user-level, no developer**: filters, detail columns (show / hide /
   drag-reorder via the existing DataGrid column preferences), summary dims + measures from
   the dataset catalog, saved views. A column NOT in the catalog needs a developer to add it
   to the dataset select; a formula builder is out of scope.

## What the data says (local prod copy, 2026-08-26)

- 48 sponsorship forms (`request_type='sponsorship_form'`), Feb 2025 to Jun 2026; 26 have
  no `request_date` (drafts). Status: draft 16, submitted 12, approved 11,
  processed_by_cs 7, rejected 2.
- Workbook 2025 has ~214 forms (PSSF25-001..214), never in the CRM.
- `total_project_value` numeric on 1 of 22 dated rows; `total_project_value_text` carries
  the "BULK ORDER EST RM1.6MIL" style. Lines (`purchase_request_lines.total`) on ~half.
- `request_number` already follows PSSF{yy}-#### (numbering rule shared with PR/SI/CMP).
- Orphan slugs `report.view` / `report.export` exist in `user_permissions`, referenced by
  no code. Left alone; not reused (their meaning is unknown).

## Column mapping (sponsorship dataset catalog)

| Workbook column | Catalog column | Source | Tag |
|---|---|---|---|
| PS NO | `request_number` | header | dimension |
| SALES AGENT | `sales_agent` | `requested_by_contact` display name, fallback `requested_by` | dimension |
| CUSTOMER NAME | `customer_name` | header | dimension |
| PROJECT TITLE | `project_title` | `projects.title` when `project_id` set, else header text | dimension |
| SPONSER PROJECT | `sponsor_subject` | lookup label; `sponsor_subject_other` appended when `others` | dimension |
| PROJECT VALUE | `project_value` | `total_project_value` | measure (money) |
| (text value) | `project_value_text` | `total_project_value_text` | text, detail only |
| SAMPLE PRICE | `sample_price` | `SUM(lines.total)` subquery, `COALESCE(total, quantity*unit_price)` | measure (money) |
| EXPECTED YEAR OF DELIVERY | `expected_delivery_year` | `EXTRACT(year FROM expected_delivery_date)` | dimension, rendered as YearTicks group |
| (month bucket) | `month` | `date_trunc('month', <date_basis>)` | dimension (derived from the chosen date basis) |
| - | `status`, `approved_at`, `request_date`, `submitted_at`, `approver`, `purpose`, `delivery_address`, `pic` | header | extra catalog columns, hidden by default |

## Architecture

```
app/services/reports/
  registry.py        ReportDefinition, Dataset, Column, params (DateBasis, Period, Select),
                     layouts (Detail, Pivot, YearTicks), Workbook/Sheet; register(); get(); catalog()
  engine.py          run(db, definition, params, view) -> ReportResult
                     - resolves date basis, binds period + selects, applies scope
                     - detail: select visible columns, ORDER BY, cap (422 "export instead")
                     - pivot: GROUP BY row_dim, col_dim in SQL; matrix + totals in Python
  xlsx_renderer.py   ReportResult + Workbook spec -> openpyxl bytes (title block, header
                     groups via merged cells, totals as VALUES, one sheet per split_by value)
  views_service.py   report_views CRUD + publish/default rules
  datasets/sponsorship_forms.py     select + catalog + scope="none" + date columns
  definitions/sponsorship.py        REPORT (default view + workbook spec); registered on import
app/api/v1/reports/
  GET  /reports                       catalog, permission-filtered
  GET  /reports/{key}                 meta: params, catalog, default view, my + shared views
  POST /reports/{key}/run             {params, view?} -> ReportResult (sync)
  POST /reports/{key}/export          -> download row + RQ job on "imports" queue (same as PR PDF)
  GET/POST/PUT/DELETE /reports/{key}/views[/{id}]   personal; publish + set-default gated
  mounted under require_module_enabled_with_api_key("procurement") for now, module key
  "reports" deferred until a second module owns a report
app/tasks/report_export_tasks.py    generate_report_xlsx(download_id, key, params, view, user_id)
alembic: report_views table; permissions procurement.sponsorship_forms.report (granted to
  holders of procurement.sponsorship_forms.view) and reports.views.publish (granted to
  holders of procurement.sponsorship_forms.edit); idempotent raw SQL like 362.
sorento_crm_frontend/
  app/(protected)/procurement-management/sponsorship-forms/report/page.tsx  wrapper
  components/reports/ReportPage.tsx        generic: filter bar from meta, Detail (DataGrid,
                                           listing_key = procurement.sponsorship_forms.report::detail),
                                           Summary (pivot table), Configure summary, Views, Export
  components/reports/{ReportFilterBar,ReportPivotTable,ConfigureSummaryDialog,ReportViewsMenu}.tsx
  components/reports/__mocks__/sponsorshipReport.fixtures.ts   S1 ONLY, deleted in S2
  services/reportService.ts; hooks/useReports.ts (useReportMeta / useReportRun /
                                           useReportViews / useReportViewMutations / useReportExport)
  config/menu.config.tsx: Report entry under Sponsorship Forms (both menu copies)
  purchase-requests/components/PurchaseRequestsList.tsx: `reportPermission` prop adds a
                                           Report action to the listing toolbar
```

### Contract points settled while building S1 (binding on S2)

The review artifact (`.lavish/reporting-foundation.html` section 4) is a sketch; these are the
three places the screen needed more than it showed, and they are what the frontend now sends and
reads.

- **`POST /run` body is `{params, view: ReportViewConfig | null}`** - the view AS IT STANDS on
  screen, saved or not, so an unsaved change runs without being saved first. `null` = the report
  default.
- **`view.detail.columns` empty means the whole catalog.** The screen always asks for the whole
  catalog and hides client-side, so ticking a column is instant and a hidden column is still
  offerable in the Columns panel (AC-B7). The EXPORT sends exactly the visible columns in the
  visible order (AC-C5), which is where AC-A5's "requested columns in the requested order" is
  exercised.
- **`col_dim.value_labels`** (optional `{value: label}` map) is added to the pivot layout. The
  header needs `Jan'26`, and the frontend must not invent a formatting rule per dimension. The
  frontend falls back to the raw value when the map is absent.
- **`column_groups[].source`** names the catalog dimension the group was derived from, alongside
  `label` and `keys`. A saved view stores the SOURCE, because the member keys are data-dependent
  (one tick column per year present) and a view written in 2026 must still mean "show the delivery
  years" in 2027.

### Shared components touched (no-ops for every flat listing)

Column groups needed three small corrections in the shared DataGrid, each of which is a no-op on a
grid without groups: `colSpan={header.colSpan}` on the head cell; a footer-row filter so the
mirror group row does not render as an empty strip; and the drag handler skipping group and
placeholder headers so one column id is never registered twice with dnd-kit. The Columns panel now
reads `getAllLeafColumns()` instead of `getAllColumns()`, which is the same list on a flat grid but
is the only way a grouped column's members can be shown or hidden.

`report_views`: id uuid, report_key text, owner_user_id text FK users, name text, view jsonb
({params, detail:{columns,order}, pivot:{rows,cols,measures}}), is_shared bool default false,
is_default bool default false, created_at, updated_at. Unique (report_key, owner_user_id, name).
At most one `is_default` per report_key (partial unique index). Personal views are visible to
their owner only; shared views to anyone with the report permission.

## Slices

| # | Slice | Ships | Proves |
|---|---|---|---|
| S1 | FE mock (Phase 1) DONE | `ReportPage` + wrapper route against a mocked ReportResult: filter bar (date basis, period, agent, status), Detail with Columns show/hide + drag, Summary pivot, Configure summary dialog, Views menu (Mine / Shared, Save, Publish, Set default), Export button; sidebar entry + listing Report button; 375 / 1280 | The §4 contract is what the screen needs; user sees the shape before backend |
| S2 | Kernel (Phase 2, test-first) | registry, engine, xlsx renderer, views service, routes, migration (table + slugs), RQ task. pytest on a SYNTHETIC dataset registered by the test, not sponsorship | The kernel is generic; report #2 costs what §Why says |
| S3 | Sponsorship dataset + definition | dataset select + catalog; definition; seeded-chain pytest asserting Summary cell = sum of Detail rows for the same agent/month, blanks vs zero, date basis switch changes the month | Report #1 on the real page with real 2026 rows |
| S4 | Excel export | workbook = SUMMARY + one sheet per month (title block, header groups, totals as values); diff test against the committed 2025 fixture layout | Cell-for-cell match on the local copy |
| S5 | Local 2025 fixture | `scripts/dev/load_sponsorship_2025_fixture.py`: refuses non-local `DATABASE_URL`; source stamped `fixture_2025`; idempotent on `request_number`; agent names matched to `respond_contacts` by name, unresolved rows REPORTED not guessed; `tests/fixtures/sponsorship_2025.xlsx` committed (real sample) | JAN-DEC'25 regenerates locally and matches the client's sheet totals |

Order: S1 -> S2 -> S3 -> S5 -> S4 (S4's diff test needs S5's fixture). Each slice is a PR;
S2 and S3 may share a branch if S2 is small enough to review together.

## Risks

- **Fixture leaking to prod.** Loader checks the DB host is local and stamps `source`; never
  referenced by deploy.sh or any migration.
- **Kernel over-generalisation.** Two layouts, three param types. Anything a third report
  needs is added when it arrives.
- **Pivot cardinality.** Cells capped (5,000) and detail rows capped (5,000) on the sync
  path; export uncapped.
- **Formula-vs-value totals.** The workbook uses SUM formulas; the export writes values the
  engine computed, so Excel cannot disagree with the screen. Stated in UAC D4.
- **Permission drift.** `projects.reports.view` is declared in forecast.py and never seeded;
  not touched. New slugs are seeded by migration with a pytest asserting the seed.
- **Data honesty.** Most 2026 forms carry no project value; blanks, not zeros, and the page
  header shows "N of M rows have a project value".
- **Contact name churn.** `sales_agent` resolves LIVE from the contact FK, so a renamed
  contact regroups history. Accepted (same rule as `requested_by_contact_name`).
