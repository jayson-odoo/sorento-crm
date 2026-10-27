# UAC: Sales unified (one sales definition + AutoCount-matching reports)

Plan: `PLAN-sales-unified-27oct.md`. Track: full. Status: round 2 (27 Oct 2026): Q1 (b) applied,
the sales type comes from the sales order chain; agent groups withdrawn.
Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` browser, `[T]` has a named test.

## Journey

Actor: the owner or a sales manager with "sales reports: view".

- **J1.** Opens Sales > Sales by debtor type for Sorento, January 2026: agent rows in blocks Dealer,
  Project team, Set apart, Mixed sales order types, Sales order type not set, No sales order;
  debtor types across; the blocks add up to every invoiced sale of the month.
- **J2.** Switches Company to Mocha: its own debtor types across, agents taken from the customers.
- **J3.** Opens Yearly comparison: Invoiced by default, one block per sales type.
- **J4.** Opens Top selling items: items with qty and RM, credit notes netted, sorted by RM.
- **J5.** Opens Sales > Set-apart customers, adds a debtor from this month; its sales move to Set
  apart from that month on.
- **J6.** Asks the chatbot "sales by agent this month" and "top selling items this month" and gets
  the same figures as J1 and J4.

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

## S2. Shared definition, sales type, set apart

- **AC-7 [BE][T]** Seeded month: IV 1,000.00, CS 200.00, DN 14.26, CN 300.00, a cancelled IV
  5,000.00, an IV with tax 60.00 on net 1,000.00. Sales = 1,914.26 (net of tax, cancelled out).
  Every invoiced dataset and route returns this.
- **AC-8 [BE][T]** A document dated 31 Jan counts in January; one dated 1 Feb in February.
- **AC-9 [BE][T]** Company setting `document`: a document whose agent differs from the customer's
  agent counts for the document's agent. Setting `customer`: for the customer's agent.
- **AC-10 [BE][T]** Sales type by the chain: an invoice line resolved onto a `retail` SO line is
  Dealer; an invoice line transferred from a DO (by number) whose SO is `project` is Project team;
  an invoice line transferred from a `project` SO by number is Project team.
- **AC-11 [BE][T]** A credit note with no traced line against a Dealer invoice is Dealer (negative).
- **AC-12 [BE][T]** A cash sale with no from-document is No sales order; an invoice tracing to one
  `retail` and one `project` SO is Mixed sales order types; one tracing only to an SO with no type
  is Sales order type not set. None is dropped; the blocks add up to AC-7's sum.
- **AC-13 [BE][T]** The sales type never reads the stored `billing_documents.demand_class`, the
  agent's class or the customer's market segment: a document with no traced SO whose agent is
  `project` is still No sales order.
- **AC-14 [BE][T]** A set-apart customer's sales go to Set apart, whatever their SO type, only in the
  months its row covers; a row with `to_month` before `from_month` is 422; an overlapping row for
  the same customer is 422.
- **AC-15 [BE][T]** Set-apart routes: no token 401; read without `sales.reports.view` 403; write
  without `sales.set_apart.edit` 403; another company's rows never returned or editable.
- **AC-16 [FE][E2E]** Set-apart customers screen: DataGrid (fixed layout, resizable, server-side sort
  on every column), Add / Edit modal, deferred-action delete, empty state, usable at 375 and 1280.

## S3. Reports

- **AC-17 [BE][T]** Sales by debtor type: one block per ticked sales type, rows per agent, columns
  the debtor types present plus `(blank)`; the summary's grand total equals the blocks' sum.
- **AC-18 [BE][T]** The Excel has the blocks on the summary sheet and one sheet per month.
- **AC-19 [BE][T]** Mocha (`customer` setting): agents from the customers; columns Mocha's types.
- **AC-20 [BE][T]** Yearly comparison defaults to Invoiced; on Invoiced the blocks are the sales
  types; Delivered / Ordered still run and say so in the basis line.
- **AC-21 [BE][T]** Top selling items: a credit note line of 2 units / 100.00 nets against an invoice
  line of 5 units / 250.00 of the same item to 3 / 150.00; an item code not in the CRM still lists.
- **AC-22 [BE][T]** Every report column sorts server-side; an unknown sort key is 422.
- **AC-23 [BE][T]** Access: without `sales.reports.view` 403; a company outside the grant 403; no
  Mocha row in a Sorento run.
- **AC-24 [FE][E2E]** Sales group sidebar shows Sales by debtor type, Top selling items and Set-apart
  customers; each opens from `/` by clicks; usable at 375 and 1280.

## S4. Other figures and the chatbot

- **AC-25 [BE][T]** `/order-management/top-selling` with no basis returns AC-21's invoiced figures;
  `basis=ordered` / `delivered` return today's figures.
- **AC-26 [BE][T]** `/api/v1/sales/analysis` defaults to Invoiced and accepts `rows` / `cols` =
  `agent` or `debtor_type` on Invoiced (422 on the order bases).
- **AC-27 [BE][T]** The delivered sales report's title, tool description and Excel title say
  "Delivered"; order analytics says "Delivered value incl. tax"; report-ask's sales measures say
  "ordered" / "delivered".
- **AC-30 [BE][T]** Tally: for the same company, period and channel, the figure
  `/api/v1/sales/analysis` returns (the route the MCP tool `crm_sales_analysis` calls) equals the
  Sales by debtor type report's grand total and its per-agent totals to the cent; the
  `/order-management/top-selling` invoiced figure (the route `crm_top_selling_report` calls) equals
  the Top selling items report's rows.

## S5. Tally

- **AC-28 [BE][T]** A fixture shaped like January 2026 (fictional codes): dealer and project SOs
  invoiced through DOs, a DN on one agent, a CN against an invoice, a cash sale with no SO, 2
  set-apart customers, an agent with no agent row master. The six buckets sum to all sales.
- **AC-29** Crew runs `scripts/sales_unified_tally.py` on the owner's copy for January 2026: per
  bucket, beside the AutoCount figures (Dealer 6,513,047.67, Project team 6,084,471.57, set apart
  122,232.99, all 14,742,279.29) with the gap, posted on the PR.
