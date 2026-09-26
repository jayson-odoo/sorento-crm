# UAC: retail sales reports, one query layer for the screens and the chatbot (#1267)

Plan: `PLAN-retail-sales-reports-26sep.md`. Track: full (S1 to S5); S0 is a measurement.
Status: draft, pre-grill (26 Sep 2026). Recommendations in the plan's section 9 are written in as
the expected behaviour and are marked `(G<n>)`; each changes if the owner rules otherwise.
Mockups: `documentation/plans/sales/mockups/retail-sales-reports.html`.
Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` browser via agent-browser, `[T]` has a named test.

## Journey

Actor: the owner or a sales manager with "sales reports: view"; on WhatsApp, a staff contact
holding the Sales report grant.

- **J1.** Opens Sales > Reports > Yearly comparison from the sidebar. The page opens on today as
  the as-at date and the default basis, with nothing to fill in.
- **J2.** Reads the DEALER block: 2024, 2025 and 2026 by month with TOTALS, the variance row, and
  the chart beneath; then the PROJECT TEAM block the same way.
- **J3.** Changes the as-at date or the basis; the tables and charts redraw.
- **J4.** Presses Export to Excel and gets a workbook laid out like the PDF.
- **J5.** Opens Sorento by account: the Monthly tab lists one table per month, agents by account,
  HANLIM apart, TOTAL SALES; Year to date and Dealer vs HANLIM tabs follow.
- **J6.** Opens Mocha by account (once Mocha's feed is live): by account per month, by debtor type,
  by month, project debtors, by quarter with the "without Dilooma and Pintar" row.
- **J7.** On WhatsApp asks "compare dealer sales 2025 vs 2026 by month" and gets the months with
  both years and the difference, the basis and the count in the header.
- **J8.** Asks "Sean's sales this month by brand" and gets Sean's accounts, all of Sean's codes
  counted, and the total.
- **J9.** Asks "Mocha Q2 by agent without Dilooma" and gets every agent, the excluded customer
  named in the header, and the total.

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
- **AC-S1-7 [BE][T]** Given `n=3` on a grid of 14 agent rows, when the route runs, then 3 rows come
  back ranked by total desc then label asc, and `total_count` is 14 and the totals are the whole
  set's. No `page`, `page_size` or `has_more` key exists in the response.
- **AC-S1-8 [BE][T]** Access: no token 401; a user without `order_management.sales_reports.view`
  403; the API key acting for a contact without the `sales_orders.sales_report` reveal key 403.

### The report

- **AC-S1-9 [BE][T]** Given `as_at` = 26/09/2026, when `yearly-comparison` runs, then each block
  has rows 2024, 2025, 2026 and columns JAN to DEC plus TOTALS; 2026 cells for October to December
  are blank (not 0).
- **AC-S1-10 [BE][T]** The variance row is 2026 minus 2025 per month, and its total is 2026 year to
  date minus 2025 over the same months (G5); a negative prints in brackets.
- **AC-S1-11 [BE][T]** The two blocks are titled `SORENTO SDN BHD - DEALER` and `SORENTO SDN BHD -
  PROJECT TEAM` from `companies.name` and the channel (G4), and each carries one chart series per
  year row.
- **AC-S1-12 [FE][E2E]** From `/`, Sales > Reports > Yearly comparison opens the page (sidebar
  click, never a deep URL). A user without the slug does not see the menu item.
- **AC-S1-13 [FE][T]** The page shows the PageHeader with the title, the as-at date and basis in
  the filter row, the basis line "Basis: Delivered (transferred to DO), sales orders, not
  invoices" (G1), both blocks with their tables and a line chart under each (months on x, one line
  per year, legend by year).
- **AC-S1-14 [FE][T]** Changing the as-at date or basis refetches once and redraws both blocks.
- **AC-S1-15 [FE][T]** A block with no sales renders its table with blanks and "No sales in this
  period", never a missing section.
- **AC-S1-16 [FE][E2E]** At 375 each table scrolls sideways inside its card with the year column
  sticky; the chart fits the width; nothing is clipped. At 1280 the table fits without scrolling.
- **AC-S1-17 [BE][T]** Export: the `.xlsx` has one sheet with the title block (company, report
  title, "As at 26/09/2026", basis), the two blocks in the PDF's order, the variance row, a native
  line chart under each block, number format `#,##0.00;(#,##0.00)`, and totals as values, never
  formulas. A text cell starting with `=`, `+`, `-` or `@` is escaped.
- **AC-S1-18 [FE][E2E]** Export to Excel is the page's one primary action and downloads the file
  named `Yearly sales comparison as at 2026-09-26.xlsx`.

### The chatbot

- **AC-S1-19 [BE][T]** `crm_sales_analysis` is in the MCP catalogue, in `PRESENTER_TOOLS`, in
  `CHATBOT_READ_ONLY_TOOLS`, mapped to the order domain, and in the order domain seed as an
  allow-list member; one migration updates the live `chatbot_domains` row; single alembic head.
- **AC-S1-20 [BE][T]** "compare dealer sales 2025 vs 2026 by month" fetches `rows=month,
  cols=year, channel=dealer, compare_years=[2025, 2026]` and prints the golden
  `sales-analysis-compare.txt`: header (company, channel, basis, period, "Months: 12"), one line
  per month with both years and the difference, a total line. No "more", "next" or "lagi".
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
- **AC-S2-5 [FE][T]** Report B page: line tabs Monthly, Year to date, Dealer vs HANLIM; the HANLIM
  set is chosen with a `SearchableMultiSelect` of customers and saved as the report's shared view;
  agents are listed in the owner's order (G7), a gap row before HANLIM, TOTAL SALES bold.
- **AC-S2-6 [FE][E2E]** At 375 the tab strip scrolls and never wraps; every table scrolls sideways
  with the agent column sticky.
- **AC-S2-7 [BE][T]** Export: one sheet, sections in the PDF's order, titled "Weekly Sales by
  Debtor Type by Sales Agent", period "01/01/2026 to 26/09/2026".
- **AC-S2-8 [BE][T]** Chatbot "Sean's sales this month" resolves SEAN to every code with that label
  and prints the golden `sales-analysis-agent.txt` (the codes named in the header).
- **AC-S2-9 [BE][T]** "Sean" with no labels and two codes starting SEAN gets `SEAN I or SEAN III?`
  and nothing is fetched.
- **AC-S2-10 [BE][T]** "sales by agent this year" with more rows than one message holds and no N
  gets the header with the full count and `That list is too long for one message. How many agents
  do you want to see?`; "top 5 agents this year" gets 5 rows under a header stating the full count.
- **AC-S2-11 [T]** DoD: every active Sorento code has a `person_label`; the count is pasted in the
  PR.

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

## S5. Report C

- **AC-S5-1 [BE][T]** `rows=agent, cols=quarter` files Jan to Mar in Q1 through Oct to Dec in Q4.
- **AC-S5-2 [BE][T]** `exclude_customer_ids` = DILOOMA and PINTAR removes their lines from every
  cell and total; the response names the excluded customers.
- **AC-S5-3 [BE][T]** `mocha-by-account` returns, in order: agent by debtor type per month (with a
  Grand Total row); agent by month per debtor type; agent by month; debtor type by month; the named
  project debtors by month; agent by quarter with a closing row "Total sales without Dilooma and
  Pintar (project)". Every section's grand total for the same window agrees.
- **AC-S5-4 [FE][T]** Report C page with line tabs By account, By debtor type, By month, Project
  debtors, By quarter; the named debtors set in the report's shared view.
- **AC-S5-5 [BE][T]** Chatbot "Mocha Q2 by agent without Dilooma" prints the golden
  `sales-analysis-exclude.txt`: header with `Company: Mocha`, `Excluded: DILOOMA ...`, `Agents with
  sales: 8`, one line per agent, the total.
- **AC-S5-6 [FE][E2E]** At 375 and 1280, report C is usable and not clipped; export matches the
  PDF's section order.

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
labels, targets and commissions (#1260).
