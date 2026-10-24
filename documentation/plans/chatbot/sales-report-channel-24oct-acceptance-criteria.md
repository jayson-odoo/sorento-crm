# UAC: SALES-REPORT-CHANNEL (Q2 + Q3 answered by crew 24 Oct; Q1 with the owner)

Plan: `PLAN-sales-report-channel-24oct.md`. Ruling Q14 (`finance/PLAN-finance-billing-documents-27sep.md:55,58`):
channel = the sales order's type (`sales_orders.demand_class`: `retail` = Dealer, `project` = Project team).

- **AC-SRC-1** `[BE]` The sales report's channel of a DO line is the `demand_class` of the sales order that line was
  delivered from: the line's own SO line link first, then the DO's SO link, then the line's `from_doc_no` when
  `from_doc_type` is `SO` (an SO of that number in the DO's company). The customer's market segment is not read.
- **AC-SRC-2** `[BE]` A channel filter keeps only lines whose SO class is in the asked channel. A line whose SO has no
  class is in no channel (the ranking's rule). It still counts in the report with no channel asked.
- **AC-SRC-3** `[BE]` A DO line with no sales order: per owner answer Q1 (draft: in no channel, like AC-SRC-2).
- **AC-SRC-4** `[BE]` A named customer plus a channel word (Q3 (a), crew 24 Oct): the channel is always applied and the
  Channel line printed (`channel` and `channel_shown` set), whatever the customer's segment or SO types.
- **AC-SRC-5** `[BE]` Date basis stays the DO date (`orders.order_date`) (Q2 (a), crew 24 Oct; owner Q4
  `report-engine-behaviour-card.md:18`).
- **AC-SRC-6** `[BE]` Agreement: for a seeded case whose DO date and SO line date fall in the same period and whose DO
  qty equals the SO line's delivered qty, the sales report's Project total and Dealer total equal `crm_report_ask`'s
  delivered ranking totals for the same channel, product and period (qty and RM).
- **AC-SRC-7** `[BE]` Unchanged: the report's total with no channel asked, REP DOs left out, amount rules AC-SR-21,
  location policy, product prefix match.
