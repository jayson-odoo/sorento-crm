# UAC: retail sales reports, one query layer for the screens and the chatbot (#1267)

Plan: `PLAN-retail-sales-reports-26sep.md`. Track: full (S1 to S4); S5 small fix track (round 2); S0 is a measurement.
Status: draft, round 2 (26 Sep 2026). The owner's Lavish review of the mockup (26 Sep 06:27Z, 10
notes) is applied: each note has an "Owner ruling 26 Sep 06:27 (Lavish) <n>" line in the section
"Round 2" below, and every criterion it changes keeps its text and gains a "Round 2:" note. No
criterion is deleted. G1 to G10 are still unanswered: their recommendations are written in as the
expected behaviour and are marked `(G<n>)`; each changes if the owner rules otherwise. The round
2 questions Q1 to Q5 (plan 9.1) are written in the same way and marked `(Q<n>)`.
Mockups: `documentation/plans/sales/mockups/retail-sales-reports.html`.
Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` browser via agent-browser, `[T]` has a named test.

## Journey

Actor: the owner or a sales manager with "sales reports: view"; on WhatsApp, a staff contact
holding the Sales report grant.

- **J1.** Opens Sales > Reports > Yearly comparison from the sidebar. The page opens on today as
  the as-at date and the default basis, with nothing to fill in.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 2: the item is Sales > Yearly comparison in the Sales group (plan 0.2); the page is the kernel's `ReportPage` (note 1).
- **J2.** Reads the DEALER block: 2024, 2025 and 2026 by month with TOTALS, the variance row, and
  the chart beneath; then the PROJECT TEAM block the same way.
- **J3.** Changes the as-at date or the basis; the tables and charts redraw.
- **J4.** Presses Export to Excel and gets a workbook laid out like the PDF.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 5: the workbook is queued and lands in My Downloads; the user downloads it from the drawer (plan 0.4).
- **J5.** Opens Sorento by account: the Monthly tab lists one table per month, agents by account,
  HANLIM apart, TOTAL SALES; Year to date and Dealer vs HANLIM tabs follow.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 4: "Sorento by account" is now **Sales report** with Company = Sorento; the sections are shared views in the Views menu, not tabs (Q4).
- **J6.** Opens Mocha by account (once Mocha's feed is live): by account per month, by debtor type,
  by month, project debtors, by quarter with the "without Dilooma and Pintar" row.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 4: the same Sales report with Company = Mocha; before S4 it shows the empty state, not a hidden item.
- **J7.** On WhatsApp asks "compare dealer sales 2025 vs 2026 by month" and gets the months with
  both years and the difference, the basis and the count in the header.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 6: the answer is a short text header plus the Excel file, like the low stock report (plan 0.6).
- **J8.** Asks "Sean's sales this month by brand" and gets Sean's accounts, all of Sean's codes
  counted, and the total.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 7 and 9: text; all of Sean's codes are counted with no "which code" question.
- **J9.** Asks "Mocha Q2 by agent without Dilooma" and gets every agent, the excluded customer
  named in the header, and the total.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 8: text.

Decisions asked of the user: the as-at date and basis (both pre-filled), the company on report A,
and on WhatsApp only what the message leaves ambiguous (company, period per G6, basis, axis, which
code).

## Measured (S0, prod copy, to be pasted before the grill closes)

- Sales orders and `SUM(line_total)` per month per company, Jan 2023 to Sep 2026: _pending_.
- Three owner-chosen months: dealer and project totals, both bases, both date rules, against the
  PDF totals, gap in RM and percent: _pending_.
- Raw `Debtor.DebtorType` values on the customers masters push, with counts and the number
  dropped as `segment_unknown`: _pending_.
- `sales_agents` per company, `person_label` fill (expected 0 of 80): _pending_.
- HANLIM ledger ids (6 expected); Mocha SO count (expected 0) and `so_feed_live`: _pending_.
- `EXPLAIN ANALYZE` of a three-year year by month grid: _pending_.

## S1. Report A and the query layer

### The grid

- **AC-S1-1 [BE][T]** Given SO lines in one company and window, when `sales_grid` runs with
  `rows=year, cols=month, basis=ordered`, then every cell is the SUM of the per-line `ordered_value`
  of `_per_line_exprs` and the grand total equals `sales_report`'s ordered value for the same
  lines and window to the cent. Same for `basis=delivered` against the confirmed value.
- **AC-S1-2 [BE][T]** Given a cancelled SO and a cancelled line, when the grid runs, then neither
  is in any cell or total.
- **AC-S1-3 [BE][T]** Given a line with `required_date` in March on an SO dated February, when the
  grid runs, then it is counted in February (`sales_orders.order_date`, G1).
- **AC-S1-4 [BE][T]** Given an SO with `demand_class` null, when the grid runs with
  `rows=channel`, then it appears in a `(blank)` row sorted last and in the grand total; it is never
  dropped.
- **AC-S1-5 [BE][T]** Given two companies each with sales, when a user granted only Sorento runs the
  grid with Sorento, then no Mocha line is in it; with `company_id` = Mocha the route is 403.
- **AC-S1-6 [BE][T]** Given `rows == cols`, an unknown axis, `date_from > date_to`, no basis, or a
  list over 50 ids, when `GET /sales-analysis` is called, then it is 422 with a named error.
  - Round 2: the route is `GET /api/v1/sales/analysis` (plan 5.5); the 422 table is unchanged.
- **AC-S1-7 [BE][T]** Given `n=3` on a grid of 14 agent rows, when the route runs, then 3 rows come
  back ranked by total desc then label asc, and `total_count` is 14 and the totals are the whole
  set's. No `page`, `page_size` or `has_more` key exists in the response.
- **AC-S1-8 [BE][T]** Access: no token 401; a user without `order_management.sales_reports.view`
  403; the API key acting for a contact without the `sales_orders.sales_report` reveal key 403.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 2: the slug is `sales.reports.view` under the `sales` module (plan 0.2, Q5).

### The report

- **AC-S1-9 [BE][T]** Given `as_at` = 26/09/2026, when `yearly-comparison` runs, then each block
  has rows 2024, 2025, 2026 and columns JAN to DEC plus TOTALS; 2026 cells for October to December
  are blank (not 0).
- **AC-S1-10 [BE][T]** The variance row is 2026 minus 2025 per month, and its total is 2026 year to
  date minus 2025 over the same months (G5); a negative prints in brackets.
- **AC-S1-11 [BE][T]** The two blocks are titled `SORENTO SDN BHD - DEALER` and `SORENTO SDN BHD -
  PROJECT TEAM` from `companies.name` and the channel (G4), and each carries one chart series per
  year row.
  - Round 2: the two blocks are the Channel filter on one kernel pivot; both blocks in one Excel file is Q1 (recommended: one block per ticked channel, one under the other).
- **AC-S1-12 [FE][E2E]** From `/`, Sales > Reports > Yearly comparison opens the page (sidebar
  click, never a deep URL). A user without the slug does not see the menu item.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 2: the path is Sales > Yearly comparison (SALES heading, Sales group).
- **AC-S1-13 [FE][T]** The page shows the PageHeader with the title, the as-at date and basis in
  the filter row, the basis line "Basis: Delivered (transferred to DO), sales orders, not
  invoices" (G1), both blocks with their tables and a line chart under each (months on x, one line
  per year, legend by year).
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 1: the page is `ReportPage` with key `sales_yearly`; the table is the Summary tab's `ReportPivotTable`, the chart is `ReportPivotChart`; the filter row is `ReportFilterBar` (Company, Channel, Basis, Period).
- **AC-S1-14 [FE][T]** Changing the as-at date or basis refetches once and redraws both blocks.
- **AC-S1-15 [FE][T]** A block with no sales renders its table with blanks and "No sales in this
  period", never a missing section.
- **AC-S1-16 [FE][E2E]** Screens print whole ringgit (the export keeps cents). At 375, and at 1280
  whenever twelve months do not fit, each table scrolls sideways inside its card with the YEAR
  column sticky and no cell cut; the chart fits the width; the page itself never scrolls sideways.
- **AC-S1-17 [BE][T]** Export: the `.xlsx` has one sheet with the title block (company, report
  title, "As at 26/09/2026", basis), the two blocks in the PDF's order, the variance row, a native
  line chart under each block, number format `#,##0.00;(#,##0.00)`, and totals as values, never
  formulas. A text cell starting with `=`, `+`, `-` or `@` is escaped.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 5: the workbook is written by the kernel's `generate_report_xlsx` worker job, with `month_sheets` off for this report.
- **AC-S1-18 [FE][E2E]** Export to Excel is the page's one primary action and downloads the file
  named `Yearly sales comparison as at 2026-09-26.xlsx`.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 5: superseded by AC-R2-8. The click queues the file and toasts "... is being prepared in My Downloads"; the file name is the kernel's `<title>-<period>.xlsx`.

### The chatbot

- **AC-S1-19 [BE][T]** `crm_sales_analysis` is in the MCP catalogue, in `PRESENTER_TOOLS`, in
  `CHATBOT_READ_ONLY_TOOLS`, mapped to the order domain, and in the order domain seed as an
  allow-list member; one migration updates the live `chatbot_domains` row; single alembic head.
- **AC-S1-20 [BE][T]** "compare dealer sales 2025 vs 2026 by month" fetches `rows=month,
  cols=year, channel=dealer, compare_years=[2025, 2026]` and prints the golden
  `sales-analysis-compare.txt`: header (company, channel, basis, period, "Months: 12"), one line
  per month with both years and the difference, a total line. No "more", "next" or "lagi".
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 6: the golden is now the text header plus an attachment (AC-R2-13, AC-R2-14); the header and total lines stay; the month lines move into the file.
- **AC-S1-21 [BE][T]** A contact granted both companies who names none gets `Sorento or Mocha?`
  and nothing is fetched.
- **AC-S1-22 [BE][T]** No period in the message = the current calendar year, printed in the
  header (G6). An ambiguous period ("last quarter" in January) gets `Which period: last quarter of
  2025, or Q1 2026?`.
- **AC-S1-23 [BE][T]** A contact linked to a customer gets `Sorry, I can only share sales figures
  for your own account.` and nothing is fetched.

## S2. Sales by agent as a person

- **AC-S2-1 [BE][T]** Given codes `SEAN I` and `SEAN III` both labelled SEAN, when the grid runs
  with `rows=agent`, then one SEAN row holds both codes' sales.
- **AC-S2-2 [BE][T]** Given a code with no `person_label`, then its row is labelled with the code;
  an SO with no agent is in `(blank)` and in the total.
- **AC-S2-3 [BE][T]** Given `set_apart_customer_ids` = the HANLIM ledgers, then HANLIM's lines are
  in no agent row, appear once in a row labelled `HANLIM`, below the agent rows, and the grand total
  is unchanged.
- **AC-S2-4 [BE][T]** `sorento-by-account` returns one section per month from January to the as-at
  month (agent rows, HANLIM row, TOTAL SALES), a "Sales for year" section, and a DEALER - SALESMAN
  vs HANLIM vs TOTAL section for JAN to DEC. The monthly sections sum to the year section to the
  cent.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 4: there is no `sorento-by-account` key. The sections are shared views of the `sales` definition (AC-R2-10); the monthly tables are the workbook's month sheets.
- **AC-S2-5 [FE][T]** Report B page: line tabs Monthly, Year to date, Dealer vs HANLIM; the HANLIM
  set is chosen with a `SearchableMultiSelect` of customers and saved as the report's shared view;
  agents are listed in the owner's order (G7), a gap row before HANLIM, TOTAL SALES bold.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 1 and 4: no line tabs; the sections are shared views in `ReportViewsMenu`. Agents are listed alphabetically by the kernel (the owner's own order is a named trigger, plan section 7), set-apart rows last.
- **AC-S2-6 [FE][E2E]** At 375 the tab strip scrolls and never wraps; every table scrolls sideways
  with the agent column sticky.
  - Round 2: no tab strip; the tables still scroll sideways inside their card with the first column pinned.
- **AC-S2-7 [BE][T]** Export: one sheet, sections in the PDF's order, titled "Weekly Sales by
  Debtor Type by Sales Agent", period "01/01/2026 to 26/09/2026".
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 5: through My Downloads; the title block keeps "Weekly Sales by Debtor Type by Sales Agent".
- **AC-S2-8 [BE][T]** Chatbot "Sean's sales this month" resolves SEAN to every code with that label
  and prints the golden `sales-analysis-agent.txt` (the codes named in the header).
- **AC-S2-9 [BE][T]** "Sean" with no labels and two codes starting SEAN gets `SEAN I or SEAN III?`
  and nothing is fetched.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 9: superseded by AC-R2-11 and AC-R2-12. With a label, or with codes that share a name (SEAN I, SEAN III), the bot sums them and never asks.
- **AC-S2-10 [BE][T]** "sales by agent this year" with more rows than one message holds and no N
  gets the header with the full count and `That list is too long for one message. How many agents
  do you want to see?`; "top 5 agents this year" gets 5 rows under a header stating the full count.
  - Round 2: superseded in part by the owner's PR #1258 ruling (26 Sep 05:32Z, "length is not the bot's problem"): a breakdown sends every row and n8n chunks (AC-R2-16). "top 5 agents this year" is unchanged.
- **AC-S2-11 [T]** DoD: every active Sorento code has a `person_label`; the count is pasted in the
  PR.
  - Round 2: the labels are pre-filled by the name split and reviewed by the owner (Q3, AC-R2-18).

## S3. Debtor type and the account columns

- **AC-S3-1 [BE][T]** Given a customers masters push carrying `Debtor.DebtorType` = `BRAVAT`, when
  it is ingested, then `customers.debtor_type` = `BRAVAT` on insert and on update, and
  `market_segment_code` behaves exactly as before (folded or dropped with `segment_unknown`).
- **AC-S3-2 [BE][T]** `debtor_type` is in the customer response schemas and in both manual customer
  dict builders; a test asserts the field in the API response.
- **AC-S3-3 [BE][T]** The grid with `cols=debtor_type` puts a customer with no debtor type in
  `(blank)`, last, and in the total.
- **AC-S3-4 [BE][T]** Report B's columns are SORENTO, BRAVAT, CERAMIC, CABANA, PROJECT, SAMPLE, then
  any other value present, then `(blank)`, then TOTAL (G3); a column with no sales in a month still
  prints, blank.
- **AC-S3-5 [FE][T]** The customer detail header shows the debtor type read-only.
- **AC-S3-6 [BE][T]** Chatbot "Sean's sales this month by brand" prints the golden
  `sales-analysis-agent-by-account.txt` (one line per account with sales, "Accounts with sales: 3",
  a total).
- **AC-S3-7 [T]** DoD: after the full masters re-push, `debtor_type` fill per company is pasted in
  the PR; the owner reads report B beside the PDF.

## S4. Mocha sales order feed

- **AC-S4-1 [BE][T]** A sales order pushed with Mocha's company code lands under Mocha and is
  invisible to a Sorento-only user.
- **AC-S4-2 [T]** DoD: Mocha's SO count and first month pasted; `so_feed_live` is true for Mocha;
  the Mocha by account menu item appears.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 4: there is no Mocha menu item to appear; Mocha's figures appear in the Sales report and the Yearly comparison through the Company filter.

## S5. Report C

- **AC-S5-1 [BE][T]** `rows=agent, cols=quarter` files Jan to Mar in Q1 through Oct to Dec in Q4.
- **AC-S5-2 [BE][T]** `exclude_customer_ids` = DILOOMA and PINTAR removes their lines from every
  cell and total; the response names the excluded customers.
- **AC-S5-3 [BE][T]** `mocha-by-account` returns, in order: agent by debtor type per month (with a
  Grand Total row); agent by month per debtor type; agent by month; debtor type by month; the named
  project debtors by month; agent by quarter with a closing row "Total sales without Dilooma and
  Pintar (project)". Every section's grand total for the same window agrees.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 4: there is no `mocha-by-account` key; these sections are the Sales report's shared views for Mocha (AC-R2-10).
- **AC-S5-4 [FE][T]** Report C page with line tabs By account, By debtor type, By month, Project
  debtors, By quarter; the named debtors set in the report's shared view.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 1 and 4: shared views in the Views menu, not line tabs.
- **AC-S5-5 [BE][T]** Chatbot "Mocha Q2 by agent without Dilooma" prints the golden
  `sales-analysis-exclude.txt`: header with `Company: Mocha`, `Excluded: DILOOMA ...`, `Agents with
  sales: 8`, one line per agent, the total.
  - Round 2: Owner ruling 26 Sep 06:27 (Lavish) 8: stays text.
- **AC-S5-6 [FE][E2E]** At 375 and 1280, report C is usable and not clipped; export matches the
  PDF's section order.

## Round 2: the owner's Lavish review (26 Sep 06:27Z)

- Owner ruling 26 Sep 06:27 (Lavish) 1: reuse the reporting module's components; few new components.
- Owner ruling 26 Sep 06:27 (Lavish) 2: sales module or schema; reuse the sponsorship form's reporting function.
- Owner ruling 26 Sep 06:27 (Lavish) 3: the same as 1 and 2, on the Sorento by account screen.
- Owner ruling 26 Sep 06:27 (Lavish) 4: one "Sales report" for both companies, not "Sorento by account".
- Owner ruling 26 Sep 06:27 (Lavish) 5: downloads go to My Downloads.
- Owner ruling 26 Sep 06:27 (Lavish) 6: the dealer year comparison is sent as a file, like the low stock report.
- Owner ruling 26 Sep 06:27 (Lavish) 7: "Sales by account" for Sean can be text.
- Owner ruling 26 Sep 06:27 (Lavish) 8: "Mocha sales by agent" can be text.
- Owner ruling 26 Sep 06:27 (Lavish) 9: SEAN I and SEAN III are the same person; count both.
- Owner ruling 26 Sep 06:27 (Lavish) 10: decide file, text, or text + file.

### Reuse and module (notes 1, 2, 3)

- **AC-R2-1 [FE][T]** (S1, S2) Both screens render `ReportPage` (`components/reports/ReportPage.tsx:270`)
  with keys `sales_yearly` and `sales`; the only new frontend files are the two route wrappers and
  `components/reports/ReportPivotChart.tsx`. An inventory test lists them.
- **AC-R2-2 [BE][T]** (S1) The `sales_order_lines` dataset and the two definitions are registered;
  `GET /reports` lists them to a holder of `sales.reports.view` and not to anyone else; the
  sponsorship report's meta, run and workbook are byte-for-byte unchanged.
- **AC-R2-3 [BE][T]** (S1) The reports router checks each definition's `module_key`: with `sales`
  disabled, both sales reports are 403 and the sponsorship report still works; a definition with no
  `module_key` is 403 (fail closed).
- **AC-R2-4 [BE][T]** (S1) The kernel's company arm is fail-closed: no resolved scope = no rows; a
  Company filter value outside the caller's grant is 403; the export job runs under the
  enqueuer's company.
- **AC-R2-5 [FE][E2E]** (S1, S2) From `/`, SALES > Sales > **Sales report** and **Yearly comparison**
  open by sidebar clicks; both items carry `moduleKey: 'sales'` and `sales.reports.view`; a user
  without the slug sees neither (Q5).
- **AC-R2-6 [T]** (S1 to S5) No new table and no `sales` Postgres schema; the only schema change of
  the whole plan is `customers.debtor_type` (S3) (Q5).

### One Sales report (note 4)

- **AC-R2-7 [FE][T]** (S2) The title is "Sales report" on the menu, the page header, the crumbs,
  the workbook and the chatbot header; the string "Sorento by account" appears nowhere. The
  Company filter lists the caller's granted companies, defaults to the current one, and is
  required.
- **AC-R2-8 [FE][E2E]** (S1, S2) Export to Excel queues the file: the toast reads "`<file>` is being
  prepared in My Downloads", the My Downloads badge moves, and the file downloads from the drawer
  row. No new file imports `saveBlobAs` (note 5).
- **AC-R2-9 [FE][E2E]** (S1, S2) With Company = Mocha and no Mocha sales orders, both reports show
  the kernel's empty state; no menu item is hidden or added.
- **AC-R2-10 [BE][T]** (S2, S5) Six shared views per company exist and are published: By account,
  By month, Debtor type by month, Dealer vs set apart, By quarter, Set apart customers by month
  (plan 0.3). Sorento's carry Set apart = the HANLIM ledgers; Mocha's "By quarter" carries
  Exclude = DILOOMA, PINTAR (Q4).
- **AC-R2-17 [FE][T]** (S1) The yearly comparison's Summary tab shows the VARIANCE row under the
  year rows (muted row, brackets for negatives, blank after the as-at month) and the line chart
  under the table, one line per year, the current year in the primary colour.

### The agent is a person (note 9)

- **AC-R2-11 [BE][T]** (S2) Given SEAN I and SEAN III labelled SEAN, "Sean's sales this month" sums
  both, the header reads "Sales agent: SEAN (SEAN I, SEAN III)", and no question is asked.
- **AC-R2-12 [BE][T]** (S2) Given no labels, SEAN I and SEAN III are grouped by the name split and
  summed, named in the header; a typed name that matches two different names (TAN KH, TAN WL)
  gets `Which Tan: TAN KH or TAN WL?` and nothing is fetched.
- **AC-R2-18 [BE][T]** (S2) The pre-fill migration sets `person_label` from the name split on every
  code with a roman suffix and a null label, never overwrites a typed label, and is idempotent
  (Q3).

### Chatbot file or text (notes 6, 7, 8, 10)

- **AC-R2-13 [BE][T]** (S1, S2) The presenter picks the format by shape (Q2): one value column =
  text (3 rows and 300 rows alike); two or more value columns and at most 12 value cells = text
  (`label: a | b | c`); more than 12 value cells = text header plus the Excel file. Goldens:
  "compare dealer sales 2025 vs 2026 by month" (36 cells, file), "Sean's sales this month by
  brand" (3 x 1, text), "Mocha Q2 by agent without Dilooma" (8 x 1, text), "HANLIM this year vs
  last year" (1 x 3, text).
- **AC-R2-14 [BE][T]** (S1) A file answer creates a `report_xlsx` My Downloads row owned by the CRM
  user linked to the contact, queues `generate_report_xlsx`, and when ready within the sync window
  returns `attachments` so the engine adds `send_attachments` after `send_message`; otherwise the
  reply is `Preparing the Excel, it will be sent here when ready.` and the worker pushes the file
  once (one-shot claim, as the low stock push).
- **AC-R2-15 [BE][T]** (S1) "in Excel", "as a file" or "send the report" forces the file for any
  answer; "as text" forces text for any answer.
- **AC-R2-16 [BE][T]** (S2) No one-message setting exists; "sales by agent this year" with 61 agents
  sends every row (n8n chunks); "best agents this year" with no N states the count and asks how
  many (the top X rule).

## Every slice

- **AC-X-1 [FE]** No UUID in any screen, export or reply; agents, customers and companies are
  names or codes.
- **AC-X-2 [FE]** Every dropdown is `SearchableSelect` / `SearchableMultiSelect`, optional ones
  clearable.
- **AC-X-3 [T]** Tests run on Postgres (`tests/_pg_fixture.py`), seeding their own SO chain; CI
  holds no data.
- **AC-X-4 [T]** No em-dash or en-dash in code, goldens, docs or commits.

## Out of scope (from the plan)

Invoice feed, quantity measure, scheduled weekly send (G9), footnote storage (G8), dated person
labels, targets and commissions (#1260), text + file on every chatbot answer (Q2).
