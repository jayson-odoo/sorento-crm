# PLAN: the chatbot sales report splits by channel the way the ranking does (SALES-REPORT-CHANNEL)

Status: Review round 1 (PR #1841: red c96ae62453, fix 42ea3f8c47, kill-proof posted; reviewer: 0 blocking, 2 should-fix
in progress). Answers: owner Q1 (a) a DO line with no SO is in no channel ("we need to link, we will link": linking is
separate work), crew Q2 (a) keep DO date, crew Q3 (a) always apply the channel. Prod sizing SQL for the linking work:
`sales-report-channel-prod-link-share.sql`. Track: M, LEAD pattern. No migration, no auth change.

UAC: `sales-report-channel-24oct-acceptance-criteria.md` (alongside).

## Journey

Owner 24 Oct ~11:00 MYT: "Channel is sales order type yes correct". A staff user asks the chatbot "Project sales
SRT102-RG this year" (ranking, `crm_report_ask`) and then "Project is channel" (sales report, `crm_sales_report`) and
gets two totals for the same channel, product and year (EXPLORE-1023C rows 16/17: 5 pcs RM 794.20 vs Qty 3 RM 550.18).
After this lane the sales report's Channel means the sales order's type (ruling Q14), like the ranking.

## Measured today (file:line)

- Sales report: `GET /order-management/sales-report` (`app/api/v1/order_management/orders.py:1789`) ->
  `sales_report_delivered.delivered_sales_report` (`app/services/sales_report_delivered.py:232`) over the
  `delivery_order_lines` dataset (`app/services/reports/datasets/delivery_order_lines.py`).
  - Channel = the CUSTOMER's `market_segment_code` (`delivery_order_lines.py:51-58`, `CHANNEL_EXPR`), and a
    channel filter KEEPS a customer with no segment (`delivery_order_lines.py:211-213`): that customer is in every
    channel. Origin: AC-SR-22 (`selfref-scope-acceptance-criteria.md:52-54`), listed as "known semantics, documented
    not changed", never an owner ruling (`PLAN-report-engine.md:454-455`).
  - A named customer: the channel word is applied only when the customer set spans more than one SEGMENT class
    (`sales_report_delivered.py:129-132`, `:306-312`); a single-segment customer ignores the channel word.
  - Dated by the DO date `orders.order_date` (`delivery_order_lines.py:260`), owner Q4 "Delivered (DO date) and
    ordered (SO date)" (`report-engine-behaviour-card.md:18`), AC-SR-20.
- Ranking: `crm_report_ask` over `sales_order_lines_ask` (`app/services/reports/datasets/sales_order_lines_ask.py`):
  Channel = `SalesOrder.demand_class` (`:120-121`, `:156`), a NULL class is in no channel; dated by
  `sales_report_service._bucket_expr` (SO line required date, else SO date, `sales_report_service.py:193-197`);
  delivered qty = `LEAST(qty_delivered, qty_ordered)` on SO lines (`sales_report_service.py:204`). Owner direction
  4 Oct (`PLAN-report-engine.md:21-31`): every ranking basis reads SO lines because DO data carried no SO link.
- Q14: `finance/PLAN-finance-billing-documents-27sep.md:55,58,63` ("by the sales order type"); G4
  `sales/PLAN-retail-sales-reports-26sep.md:575-577`.

## The DO line -> sales order link (dev data, `sorento_cagent_stack`, 2026, REP and cancelled out)

| DO line kind | lines | qty |
|---|---|---|
| AutoCount DO, `order_lines.sales_order_line_id` set | 26,932 | 293,017 |
| AutoCount DO, no line link, `from_doc_type='SO'` + `from_doc_no` = an SO number in the same company | 15,063 | 322,250 |
| AutoCount DO with no SO at all (direct DO) | 1,227 | 1,080 |
| legacy DO (`source_book` NULL, Apr to Aug 2026 in dev): no line link, no `from_doc_no`, `orders.sales_order_id` NULL | 63,706 | 1,109,567 |

`orders.sales_order_id` is NULL on all 43,187 dev DOs. Where both links exist they always name the same SO
(0 mismatches). Linked lines whose SO has a NULL `demand_class`: 10,078 qty. RMA and CG DOs carry no lines in dev.

## ARCHITECTURE

- Layer: backend dataset only (`delivery_order_lines.py`: the `channel` dimension + `channel` filter) and the
  route-shaping rule for a named customer (`sales_report_delivered.py:304-316`). No presenter, parser, MCP catalog or
  FE change (the Channel line's words stay "Retail" / "Project", `sorento_crm_mcp/presenters.py:2798`).
- Shared mechanism: ONE SQL expression, "the DO line's sales order demand class", resolved in order line link
  (`sales_order_line_id` -> `sales_order_lines.sales_order_id`), header link (`orders.sales_order_id`), then
  `from_doc_no` (with `from_doc_type = 'SO'`, same company). The filter is `class IN (values)`, the ranking's own NULL
  rule (`sales_order_lines_ask.py:120-121`). The dimension and the filter read the same expression, so a split by
  channel and a channel filter cannot disagree.
- Classes fixed: every channel ask on the sales report (filter, Channel dimension, named-customer case), not one
  question shape. A DO line no link resolves is in no channel (owner Q1 (a)).
- Other callers of the changed code: `delivery_order_lines.DEFINITION` is run only by `sales_report_delivered`
  (`sales_report_delivered.py:107`); not registered on the Reports screen (`delivery_order_lines.py:27-29`); no FE page
  calls `/order-management/sales-report` (grep of `sorento_crm_frontend/app|components|services|lib`). The MCP tool
  `crm_sales_report` and the chatbot business lane are the only consumers. `NO_AGENT` (imported by
  `sales_order_lines_ask.py:25`, `reports/ask.py:151`) and `_CHANNEL_CLASS` + `resolve_locations` (imported by
  `reports/ask.py:21`) are untouched, so `crm_report_ask`'s numbers do not move. `crm_top_selling_report`
  (`sales_report_service.py:270-273`) and Sales > Yearly comparison (`sales_order_lines.py:66-72`,
  `billing_documents.py:73-74`) already read `demand_class` and are untouched.
- Decided, reviewer nit 3: the doc-number link requires `from_doc_type = 'SO'`. The AutoCount ingest also tries a
  NULL type (`autocount_doc_ingest_service.py:1169-1170`), but 0 of 116,487 dev DO lines carry a `from_doc_no` without a
  type, so the stricter rule moves no number; revisit if a feed starts sending NULL types.
- Not slower in kind: the two lookups are indexed scalar subqueries (pk; unique `(company_id, so_number)`). Worst ask
  measured on the dev copy (all products, full year, Project): 5.1 s vs main 2.7 s all companies, 2.8 s vs 1.6 s Sorento.
- Out of scope, noted: the sales report's `sales_agent` dimension reads only the header link `orders.sales_order_id`
  (`delivery_order_lines.py:177-178`), NULL on every dev DO. Separate ticket if wanted.

## Slices (after answers)

1. Tester: red pytest (Postgres, `tests/_pg_fixture.py`), from the UAC: seeded chain with customers of project,
   retail and no segment; SOs of class project, retail and NULL; DO lines linked by line, by header, by `from_doc_no`,
   and unlinked. Asserts the sales report's channel totals and its agreement with `crm_report_ask` (delivered basis) on
   the card's example shape (DO date and SO line date in the same period, DO qty = SO delivered qty).
   Commit `test(red): ...` alone.
2. Coder: make them green, touching only the files above.
3. Kill test, reviewer, hand test script `laneboard/scripts/<PR>.md`.
