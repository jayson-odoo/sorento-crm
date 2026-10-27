# UAC: Sales unified (one sales definition + AutoCount-matching reports)

Plan: `PLAN-sales-unified-27oct.md`. Track: full. Status: draft, waiting on the owner's OK of the
card and mock. `(Q<n>)` marks a recommendation written in until the owner rules.
Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` browser, `[T]` has a named test.

## Journey

Actor: the owner or a sales manager with "sales reports: view".

- **J1.** Opens Sales > Sales by debtor type for Sorento, January 2026: agents in Dealer, Project
  team, Set apart and Ungrouped blocks, debtor types across, Report total equal to the AutoCount
  PDF's all-channels figure, ALL SALES equal to every invoiced sale of the month.
- **J2.** Switches Company to Mocha: ACCOUNT I to IV across, agents taken from the customers.
- **J3.** Opens Yearly comparison: Invoiced by default, Dealer / Project team blocks by report group.
- **J4.** Opens Top selling items: items ranked by RM, credit notes netted.
- **J5.** Opens Sales > Report groups, moves an agent from Project team to Dealer from July; the
  reports re-group July onwards at once.
- **J6.** Asks the chatbot "top selling items this month" and gets the same figures as J4.

## S1. Schema and ingest

- **AC-1 [BE][T]** A customers push with `market_segment_code` = ` bravat ` stores
  `autocount_debtor_type` = `BRAVAT`, whether or not a market segment matches; an unknown value
  still warns `segment_unknown` and still stores the debtor type.
- **AC-2 [BE][T]** A push without `market_segment_code` leaves `autocount_debtor_type` untouched.
- **AC-3 [BE][T]** `customers.debtor_type` (the CRM concept) is never written by AC-1.
- **AC-4 [BE][T]** `companies.sales_agent_source` defaults to `document` and rejects any value but
  `document` / `customer`; the Companies update route saves it.
- **AC-5 [BE][T]** The migration is additive, upgrades and downgrades cleanly, single alembic head.
- **AC-6 [FE][T]** Customer detail header shows the AutoCount debtor type read-only (`-` when none).

## S2. Shared definition and report groups

- **AC-7 [BE][T]** Seeded month: IV 1,000.00, CS 200.00, DN 14.26, CN 300.00, a cancelled IV
  5,000.00, an IV with tax 60.00 on net 1,000.00. Sales = 1,000 + 200 + 14.26 - 300 + 1,000 =
  1,914.26 (net of tax, cancelled out). Every invoiced dataset returns this.
- **AC-8 [BE][T]** A document dated 31 Jan counts in January; one dated 1 Feb in February.
- **AC-9 [BE][T]** Company setting `document`: a document whose agent differs from the customer's
  agent counts for the document's agent. Setting `customer`: for the customer's agent.
- **AC-10 [BE][T]** Agent A in Project team Jan to Jun and Dealer from Jul: June sales are Project
  team, July sales Dealer.
- **AC-11 [BE][T]** An agent with no group row for the month, and a document with no agent, are in
  Ungrouped and in ALL SALES; nothing is dropped. ALL SALES = AC-7's whole-company sum.
- **AC-12 [BE][T]** A set-apart customer's sales go to Set apart, not to its agent's group, only in
  the months its row covers (Q3).
- **AC-13 [BE][T]** Adding an open row for an agent with an open row closes the old row at the
  previous month; an overlapping row is 422 with a named error.
- **AC-14 [BE][T]** Report groups routes: no token 401; without `sales.report_groups.view` 403 on
  read; without `.edit` 403 on write; rows of another company never returned or editable.
- **AC-15 [FE][E2E]** Report groups screen: two line tabs, DataGrid (fixed layout, resizable,
  server-side sort on every column), Add / Edit modal, deferred-action delete, empty state per
  tab, usable at 375 and 1280.

## S3. Reports

- **AC-16 [BE][T]** Sales by debtor type, one month: rows per agent within blocks Dealer, Project
  team, Set apart, Ungrouped; columns = debtor types present plus `(blank)`; block totals; Report
  total = Dealer + Project team + Set apart; ALL SALES = all.
- **AC-17 [BE][T]** View = Year to date sums January to the selected month; the Excel has one sheet
  per month plus YTD.
- **AC-18 [BE][T]** Mocha (`customer` setting, no groups): one list ending ALL SALES; columns are
  Mocha's own debtor types.
- **AC-19 [BE][T]** Yearly comparison defaults to Invoiced; on Invoiced the blocks are report
  groups (Q1); Delivered / Ordered still run and say so in the basis line.
- **AC-20 [BE][T]** Top selling items: a credit note line of 2 units / 100.00 nets against an
  invoice line of 5 units / 250.00 of the same item to 3 / 150.00; a line whose item code is not
  in the CRM still ranks by its code.
- **AC-21 [BE][T]** Every report column sorts server-side; a sort key not in the catalogue is 422.
- **AC-22 [BE][T]** Access: without `sales.reports.view` 403; a company outside the user's grant
  403; no Mocha row in a Sorento run.
- **AC-23 [FE][E2E]** Sales group sidebar shows Sales by debtor type, Top selling items and Report
  groups; each opens from `/` by clicks; usable at 375 and 1280.

## S4. Other figures

- **AC-24 [BE][T]** `/order-management/top-selling` with no basis returns the invoiced figures of
  AC-20; `basis=ordered` / `delivered` return today's figures.
- **AC-25 [BE][T]** Report-ask "sales" defaults to the invoiced measure; delivered / ordered /
  outstanding unchanged.
- **AC-26 [BE][T]** The delivered sales report, its MCP tool description and its Excel title say
  "Delivered"; order analytics says "Delivered value incl. tax".
- **AC-27 [BE][T]** MCP catalog descriptions of `crm_top_selling_report`, `crm_report_ask`,
  `crm_sales_analysis` state the invoiced definition.

## S5. Tally

- **AC-28 [BE][T]** A fixture shaped like January 2026 (fictional codes): dealer agents with I /
  III / IV codes, single-code project agents, a DN on one agent, 2 set-apart customers, 3 ungrouped
  agents and a no-agent document. Report total and ALL SALES differ by exactly the Ungrouped total.
- **AC-29** Crew runs the real January 2026 tally on the owner's copy: Dealer 6,513,047.67,
  Project team 6,084,471.57, set apart 122,232.99, ALL SALES 14,742,279.29.
