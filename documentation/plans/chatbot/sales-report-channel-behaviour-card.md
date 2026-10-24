# Behaviour card: SALES-REPORT-CHANNEL (filed 24 Oct 2026)

Plan: `PLAN-sales-report-channel-24oct.md`. Figures: dev copy `sorento_cagent_stack`, all companies, read-only.

## Rule

Ruling Q14 (`finance/PLAN-finance-billing-documents-27sep.md:55,58`): the sales report's Channel is the type of the
sales order each DO line was delivered from (`sales_orders.demand_class`: retail = Dealer, project = Project). The SO is
found by the line's own SO link (`order_lines.sales_order_line_id`), else the DO's SO link (`orders.sales_order_id`),
else the line's `from_doc_no` (`from_doc_type` SO, same company). Today the report reads the CUSTOMER's market segment
(`delivery_order_lines.py:51-58`), and a customer with no segment counts in EVERY channel (`:211-213`). An SO with no
type is in no channel, the ranking's rule (`sales_order_lines_ask.py:120-121`). The report with no channel asked does
not change. Only caller: `crm_sales_report` (`sales_report_delivered.py:107`); no web page uses it.

## Examples (today -> new | ranking `crm_report_ask`, delivered)

1. SRT102-RG, Sep 2026, Project: Qty 3, RM 550.18 -> 0 | 1 pcs, RM 148.92 (eval row 17's figure). All 3 pcs are on
   customers with no segment: 2 on Dealer-type SOs, 1 on a DO with no SO. The ranking's 1 pc is an SO line dated
   24 Sep, delivered by a DO dated 14 Oct (date basis, Q2).
2. B2155-NL-BLUE, Sep 2026, Dealer: 584 pcs, RM 6,721.55 -> 25 pcs, RM 162.45 | 25 pcs, RM 162.45 (agree exactly).
   Project: 6,313 pcs, RM 46,546.66 -> 6,855 pcs, RM 52,989.36 | 7,174 pcs, RM 44,733.78.
3. SRT102-RG, Sep 2026, Dealer: 41 pcs, RM 6,559.66 -> 40 pcs, RM 6,280.66 | 122 pcs, RM 16,446.82 (the ranking
   counts SO lines dated in Sep, whatever DO delivered them and whenever).
4. SRT102-RG, May 2026, Dealer: 45 pcs, RM 6,697.89 -> 0 | 51 pcs, RM 7,294.89. May's DOs are old-system DOs with no
   SO link (Q1).
5. SRT102-RG, 2026, no channel: 244 pcs, RM 35,220.62 before and after.

## Edge cases (2026 DO lines, REP and cancelled left out)

- No SO link: old-system DOs (`source_book` NULL, Apr to Aug 2026 in dev) 1,109,567 qty, 64% of 2026 delivered qty;
  AutoCount direct DOs 1,080 qty. `orders.sales_order_id` is NULL on all 43,187 dev DOs. Q1. Prod share UNVERIFIED
  (the DO history backfill, `autocount/PLAN-do-history-backfill-13oct.md:291`, may have replaced old DOs with linked
  AutoCount ones); a read-only SQL for the owner can measure it.
- SO with no type: 10,078 qty on linked lines (677 SOs in 2026 carry no `demand_class`): in no channel, still in the
  no-channel total.
- Linked by `from_doc_no` only: 322,250 qty. Where the line link also exists it names the same SO (0 mismatches).
- Returns and consignment: RMA and CG DOs carry no lines in dev (1,143 and 363 headers), so they are out before and
  after. Credit notes are not in the DO report (invoiced basis only). No 2026 DO line links to a consignment SO; one
  that did would take that SO's type (the ranking leaves consignment SOs out, `sales_report_service.py:245-248`;
  unchanged here).
- Named customer: today the channel word is dropped when the customer's segment is one class
  (`sales_report_delivered.py:306-314`). Q3.

## Questions

- **Q1** DO lines with no SO link, when a channel is asked. (a) In no channel: they still count with no channel
  asked, but "Project sales in May" answers from linked DOs only (May 2026 answers 0 in dev), the same rule as an SO
  with no type. (b) Fall back to the customer's market segment, no segment = in no channel. (c) Fall back to today's
  rule (no segment = every channel). **Recommend (a)**: Q14 as written and the ranking's own rule; (b) and (c) bring
  back the customer-segment channel just rejected, and a month would mix two definitions.
- **Q2** Date basis. (a) Keep the DO date (owner Q4 "Delivered (DO date) and ordered (SO date)",
  `report-engine-behaviour-card.md:18`; AC-SR-20). (b) Date the sales report by the SO line date like the ranking
  (`sales_report_service.py:193-197`). **Recommend (a)**: the sales report answers "what was delivered when" and the
  owner already ruled it; report and ranking agree whenever an SO line and its DO fall in the same period (example 2)
  and differ by a line delivered in another period (example 1). The ranking's own date basis is not in this lane.
- **Q3** A named customer plus a channel ("Project sales for <customer>"). (a) Always apply the channel and print the
  Channel line. (b) Apply it only when that customer's DO lines span both SO types (today's rule, moved from segment to
  SO type). **Recommend (a)**: one customer buys through both channels (`scm/sales_agent_service.py:150-151`), and
  today a dealer-only customer asked for Project gets ALL its sales with no Channel line.

Note, no change proposed: the Channel line keeps its words "Retail" / "Project" (`sorento_crm_mcp/presenters.py:2795-2802`)
while the ranking prints "Dealer" / "Project team" (`sales_order_lines.py:38`). Say if the ranking's words are wanted.
