# UAC: report engine, slice 1 (top sales agent by product / brand)

Status: DRAFT, pending the owner's answers on `report-engine-behaviour-card.md`. Values marked
[Qn] follow that card's recommendation and change with the answer.
Plan: `PLAN-report-engine.md`.

## Journey

An office staffer on WhatsApp asks "top 3 salesman for Sorento brand last month" and gets a
ranked list of sales agents by delivered sales value. A dealer asking the same is told the
breakdown is not available. No new tool is built for the next angle.

## Acceptance criteria

- **AC-RE-1** Staff (active "<brand> Office" access type) holding `sales_orders.sales_report`
  asks "top sales agent for <product code> this year": the reply ranks sales agents by delivered
  amount (DO lines, DO date), highest first, for products matching the code prefix, 1 Jan to
  today, Malaysia time [Q3].
- **AC-RE-2** Same with a brand ("for Sorento brand"): only DO lines whose product's brand is
  that brand count.
- **AC-RE-3** Same with a category ("for basin category").
- **AC-RE-4** "top 3" prints 3 rows and "and N more" when there are more; no number given prints
  10 [Q5].
- **AC-RE-5** "bottom 5" ranks lowest first; an agent with no sale in the period is not listed.
- **AC-RE-6** "by qty" ranks by quantity; default ranks by amount.
- **AC-RE-7** DO lines with no sales order, or a sales order with no agent, appear as one row
  "(no agent)"; the rows always sum to the printed total.
- **AC-RE-8** The header names: measure, basis ("Delivered, by DO date"), period (dates), and
  every filter by name (brand / product / category / customer / location / channel).
- **AC-RE-9** "top 5 customers for Mocha brand last quarter", "which location sold most of
  <code> in September", "sales by month for agent <name> this year" are answered by the same
  tool with no code change beyond slice 1.
- **AC-RE-10** A customer-linked contact (dealer) asking any sales-agent ranking or filter is
  told "That breakdown is not available for your account." and no figure is returned [Q1].
- **AC-RE-11** A contact with no customer links and no office access type is treated as a
  dealer for AC-RE-10 (fail closed).
- **AC-RE-12** A dealer asking "top products for my account this year" gets its OWN delivered
  sales ranked by product; naming another customer is refused with the existing wording [Q2].
- **AC-RE-13** A contact without `sales_orders.sales_report` gets the existing sales-report
  refusal; nothing is computed.
- **AC-RE-14** Figures come only from the contact's companies; a staffer in Sorento only never
  sees Mocha figures.
- **AC-RE-15** An ask to slice by something not in the catalogue ("by colour") is answered with
  the list of what sales can be ranked by, not a guess.
- **AC-RE-16** Totals and per-agent amounts equal, to the sen, what
  `GET /order-management/sales-report?group_by=sales_agent` returns for the same product,
  window and company (parity).
- **AC-RE-17** The route refuses a request without `X-API-Key`; at most 10 asks per contact per
  10 minutes.
