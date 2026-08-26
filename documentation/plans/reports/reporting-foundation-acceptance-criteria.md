# UAC - Reporting foundation (Sponsorship report as report #1)

Status: grilled 2026-08-26, decisions Q1-Q7 taken. Pre-code.
Related: PLAN-reporting-foundation.md

## End goal (one paragraph)

A project-sales manager opens Procurement > Sponsorship Forms > Report (or presses Report on
the Sponsorship Forms listing), picks a year, and sees the sponsorship register as a table
and as a salesman-by-month summary with totals, exactly the two shapes of the workbook they
keep by hand today. They can add or hide columns, drag them into order, change what the
summary groups by, save that as a view, share it, and export the current view to an Excel
workbook that lands in My Downloads. The next report the company asks for is built by a
developer adding one dataset and one definition, and appears with the same page, the same
filters, the same views and the same export without new frontend or Excel code.

## Journey

Sales manager -> sidebar Procurement -> Sponsorship Forms -> Report. Filter bar shows View
(Management default, shared), Date basis (Approved), Period (2026), Sales agent (All), Status
(Approved, Processed). Tab "Sponsorships (21)" is the detail DataGrid; tab "Summary by
salesman" is the pivot. Columns opens the DataGrid panel (tick "Approver", drag it after
"Sales agent"). Configure summary opens a dialog with Rows / Columns / Measures selects.
Save view asks for a name. Export to Excel queues a workbook; the My Downloads badge lights
up; the file has a SUMMARY sheet and one sheet per month of the chosen period.

## Acceptance criteria

### A. Kernel (generic, proven on a synthetic dataset)

- **AC-A1.** A report is registered with a key, title, permission slug, dataset, params,
  default layouts and a workbook spec. `GET /api/v1/reports` lists only reports whose
  permission the caller holds; `GET /api/v1/reports/{key}` returns 403 without it and 404
  for an unknown key.
- **AC-A2.** A dataset declares a column catalog; every column is tagged dimension, measure,
  date or text, with a label and a type (text, money, integer, date, bool). Registering a
  dataset without an explicit scope declaration (`company` or `none`) raises at import.
- **AC-A3.** `POST /run` accepts `{params, view?}`. Params are validated against the
  definition: an unknown param or an unknown date-basis column is a 422 naming the field.
- **AC-A4.** Period binds to the chosen date basis: rows are included when
  `<date_basis> >= start AND < end` of the period (year, month range, custom range).
- **AC-A5.** Detail layout returns the requested columns in the requested order plus totals
  for every measure among them. Money is a decimal string with two places.
- **AC-A6.** Pivot layout groups in SQL by the chosen row and column dimensions, and returns
  a sparse cell map, row totals, column totals and a grand total per measure. A missing cell
  is absent, not zero. Column values are ordered naturally (months chronological).
- **AC-A7.** A detail run over the sync cap (5,000 rows) or a pivot over 5,000 cells answers
  422 with `capped: true` and a message to export instead; the export path has no cap.
- **AC-A8.** `POST /export` creates a download row (kind `report_xlsx`, filename
  `<title>-<period>.xlsx`), enqueues the task on the `imports` queue, and the file appears
  in My Downloads when ready; the drawer resolves it through the existing `/downloads`
  routes unchanged.
- **AC-A9.** pytest registers a synthetic dataset over a scratch table (CI has no data),
  runs both layouts through the engine and asserts A4-A7. The sponsorship report never
  appears in these tests.

### B. Sponsorship dataset and definition

- **AC-B1.** Catalog columns and sources are those in the PLAN mapping table. `sales_agent`
  resolves from `requested_by_contact` and falls back to `requested_by`; `project_title`
  prefers the linked project's title.
- **AC-B2.** `sample_price` is the sum of the form's lines (`COALESCE(total,
  quantity * unit_price)`); a form with no lines has an empty sample price, not zero.
- **AC-B3.** `project_value` is `total_project_value`; when it is NULL and
  `total_project_value_text` is set, the detail row shows the text in `project_value_text`
  and the measure stays empty (excluded from totals), matching the workbook's "-".
- **AC-B4.** Date basis offers `approved_at` (default), `request_date`, `submitted_at`.
  Switching it moves a form between months in both layouts.
- **AC-B5.** Status defaults to `approved` + `processed_by_cs`; the filter can widen to any
  status. Voided rows are never included.
- **AC-B6.** The dataset is company-agnostic (`scope="none"`), stated in its docstring.
- **AC-B7.** Default detail columns: PS No, Sales agent, Customer, Project title, Sponsor
  project, Project value, Sample price, Expected year of delivery (a header group with one
  tick column per year present in the result). The rest of the catalog is hidden, not
  absent. No OTHERS column.
- **AC-B8.** Default summary: rows `sales_agent`, columns `month`, measures `project_value`
  and `sample_price`, with row / column / grand totals.
- **AC-B9.** Permission `procurement.sponsorship_forms.report`, seeded by migration and
  granted to every role holding `procurement.sponsorship_forms.view`; a pytest asserts the
  seed.
- **AC-B10.** Seeded-chain pytest: three forms across two agents and two months; the Summary
  cell for (agent, month) equals the sum of the Detail rows filtered the same way; the
  agent with no form in a month has no cell; the grand total equals the detail total.

### C. Configurability and views

- **AC-C1.** Detail columns: any catalog column can be shown or hidden and dragged into
  order in the DataGrid; the choice persists per user under listing key
  `procurement.sponsorship_forms.report::detail` via the existing column-config endpoints.
- **AC-C2.** Configure summary offers every dimension for Rows and Columns and every measure
  (multi) for Measures, as SearchableSelects; Rows and Columns cannot be the same column.
- **AC-C3.** Save view stores `{params, detail columns + order, pivot config}` under a name
  unique per user per report; Views lists Mine and Shared; selecting one applies it
  atomically; Reset returns to the report default.
- **AC-C4.** Publish (requires `reports.views.publish`) marks a view shared; Set as default
  makes one shared view the report default for everyone; at most one default per report.
  Without the permission the two actions are absent, not disabled.
- **AC-C5.** Export uses the current view: the workbook's detail sheets carry the visible
  columns in the visible order and the summary sheet carries the configured pivot.
- **AC-C6.** vitest covers the generic page's loading, empty, capped and data states, the
  Configure summary dialog, and the Views menu with and without the publish permission.

### D. Excel workbook

- **AC-D1.** Sheet order: SUMMARY first, then one sheet per month in the period, named like
  the workbook (`JAN'26` ... `DEC'26`). A month with no rows still gets a sheet with the
  title block and a zero-row table.
- **AC-D2.** Every sheet starts with the title block: company name, report title, period
  label (`Jan'26 to Dec'26` on SUMMARY, the month on a monthly sheet), department.
- **AC-D3.** Header groups render as merged header cells (Expected year of delivery over
  its year columns; each month over Project value / Sample price on SUMMARY).
- **AC-D4.** Totals are written as values computed by the engine, never as formulas. Money
  cells carry a number format with thousands separators and two decimals.
- **AC-D5.** pytest renders the S5 fixture year and asserts the SUMMARY grand totals and
  each monthly GRAND TOTAL equal the client's workbook values for the same rows.

### E. Navigation and conformance

- **AC-E1.** Sidebar entry Procurement > Sponsorship Forms > Report, permission
  `procurement.sponsorship_forms.report`, in both menu copies; the Sponsorship Forms listing
  toolbar shows a Report button under the same permission.
- **AC-E2.** Usable at 375px and 1280px: the filter bar wraps, both tables scroll inside
  their container, the pivot pins its first column.
- **AC-E3.** No explanatory prose on the page; labels carry the meaning.
- **AC-E4.** Every select is clearable and searchable; no UUID is rendered.
- **AC-E5.** One agent-browser evidence run reaches the report by sidebar clicks from `/`,
  switches date basis, hides and drags a column, configures the summary, saves and publishes
  a view, exports, and opens the file from My Downloads.

### F. Local 2025 fixture (never prod)

- **AC-F1.** `scripts/dev/load_sponsorship_2025_fixture.py` refuses to run unless
  `DATABASE_URL` points at localhost / 127.0.0.1, and prints the refusal reason.
- **AC-F2.** Rows are stamped `source='fixture_2025'`, `status='approved'`,
  `approved_at = request_date = first day of the sheet's month`; sample price becomes one
  line; project value text goes to `total_project_value_text` when not numeric.
- **AC-F3.** Idempotent on `request_number`; a re-run updates, never duplicates.
- **AC-F4.** Agent names are matched to `respond_contacts` by name; unmatched names are
  listed at the end with counts, and those rows keep the name in `requested_by` only.
- **AC-F5.** The workbook is committed as `tests/fixtures/sponsorship_2025.xlsx` (real
  sample, per the e2e-real-samples rule) and is the input of AC-D5.

### G. Workbook fidelity (S6)

The report, on its DEFAULT configuration, reads as close to the client's own workbook as
the CRM allows, on screen and in Excel. Every item below is configuration on the
definition, the dataset or the shared renderer, so report #2 inherits the mechanism and
nothing sponsorship-specific enters the kernel. The export keeps following the columns on
screen (AC-C5 stands).

- **AC-G1 [FE].** Given the Period is a year, when the report renders, then a chip row
  reads All, Jan .. Dec under the Period control; clicking a month shows that month's rows
  and total (the client's monthly sheet) by setting a `month_range` period with
  `from_month == to_month`, and the chip row reflects the current period. Exporting a
  single month yields SUMMARY (one month column) plus that one monthly sheet.
- **AC-G2 [FE].** The detail grid shows every row of the period at once (no pagination
  control; the page size IS the row count), rows are compact, and the seven default
  columns plus the four year columns fit at 1280 with no horizontal scroll. Long text
  still truncates with a `title`.
- **AC-G3 [BE/FE].** Expected year of delivery is a FIXED group of four columns, the
  period's year .. year + 3, whatever the data holds. The column ids are stable
  (`expected_delivery_year_1` .. `_4`) and the labels are the actual years, so switching
  the period never leaves a stale id in the column preferences and the console error
  "Column with id 'expected_delivery_year__2026' does not exist" cannot recur. A row whose
  expected delivery year matches a column shows a check mark; every other cell is blank.
- **AC-G4 [FE].** A single-level header cell spans BOTH header rows (rowSpan) in the
  shared DataGrid, so the group row exists only over the grouped columns, as the
  workbook's merged header does. A flat listing has one header row and is unchanged.
- **AC-G5 [FE].** A money cell that is zero or missing renders "-". The Sponsor project
  cell shows the free text ALONE when the subject is "others" (no "Others: " prefix); every
  other subject reads its lookup label. This supersedes the S3 contract point.
- **AC-G6 [BE].** The catalog carries the sheet's OTHERS column (the form's `purpose` free
  text), labelled Others and hidden by default, so a user can show it and export it.
- **AC-G7 [BE].** Every exported sheet opens with the client's title block: row 2 the
  company legal name (the DEFINITION's `company_name`; `system_settings.name` only when the
  definition names none, which is where report #2 gets a letterhead from),
  row 3 the report title, row 4 a real date cell formatted `mmm-yy` on a monthly sheet or
  the period label on SUMMARY, row 5 `DEPARTMENT:` and the department. Rows 2-4 are merged
  across the table, centred and bold.
- **AC-G8 [BE].** Header labels are the definition's, uppercase (PS NO:, SALES AGENT,
  CUSTOMER NAME, PROJECT TITLE, SPONSHER PROJECT, PROJECT VALUE, SAMPLE PRICE, EXPECTED
  YEAR OF DELIVERY over the four years, OTHERS when shown). A single-level header is
  merged vertically over rows 6-7, a group header horizontally over its members, both
  bold and bordered, and column widths come from the definition.
- **AC-G9 [BE].** A money cell carries the accounting format `"RM"#,##0.00`, so zero
  prints RM - ; a missing money cell prints "-" as the client's sheet does. The detail
  GRAND TOTAL row is labelled in the column immediately before the first measure, bold,
  and its values are still what the engine computed (AC-D4).
- **AC-G10 [BE].** SUMMARY mirrors the client's: uppercase headers, month headers JAN'25 ..
  merged over their measures, a `TOTAL VALUE (BY SALESMAN)` group last, a `TOTAL SALES`
  row of column totals, then one labelled row per measure -
  `GRAND TOTAL PROJECT VALUE JAN-DEC'25` and `GRAND TOTAL SAMPLE PRICE JAN-DEC'25` -
  carrying the year totals. Agent names print as stored, never uppercased.
- **AC-G11 [T].** `tests/test_report_workbook_2025.py` asserts CELL POSITIONS as well as
  numbers: for JAN'25 the GRAND TOTAL money sits in the same columns as the client's F25 /
  G25 given the header layout, the title-block cells hold the expected strings, and the
  twelve monthly totals plus the SUMMARY year totals still match the client's workbook to
  the cent.
