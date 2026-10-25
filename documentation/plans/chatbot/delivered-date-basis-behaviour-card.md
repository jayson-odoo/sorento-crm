# Behaviour card: DELIVERED-DATE-BASIS (25 Oct 2026)

Plan: `PLAN-delivered-date-basis-25oct.md`. Owner ruling 25 Oct ~16:35: every DELIVERED sales measure uses the delivery
order (DO) date. Figures: crew live check of #1853 on the prod clone (this cloud lane has no DB copy; the read-only SQL
at the bottom fills the before/after table on `sorento_prod_1020`).

## Where delivered is computed today (by period)

| # | Surface | Rows / date today | File:line |
|---|---|---|---|
| 1 | Chatbot ranking / totals / follow-ups (`crm_report_ask`, delivered basis; drill, refine, compare all re-run it) | SO lines, line date = `required_date` else SO `order_date`; qty `LEAST(delivered, ordered)` | `app/services/reports/ask.py:46-56`, `datasets/sales_order_lines_ask.py:39,145,170`, `sales_report_service.py:240-268` |
| 2 | Agent fill rate note on a ranking | SO count on the SO line date | `app/api/v1/order_management/report_ask.py:523-551`, `sales_report_service.py:615` |
| 3 | Chatbot sales report (`crm_sales_report`) | DO lines, DO date (already right) | `sales_report_delivered.py:97-110`, `datasets/delivery_order_lines.py:296` |
| 4 | Yearly comparison screen + chatbot `crm_sales_analysis`, Basis = Delivered | SO lines, SO `order_date`; `confirmed_value` | `definitions/sales_yearly.py:89-129`, `datasets/sales_order_lines.py:79-82,209-262` |
| 5 | Legacy `GET /order-management/top-selling`, basis delivered (on no chatbot row since R4b; analytics connector `crm_top_selling_report`) | SO lines, line date | `sales_report_service.py:644-750`, `api/v1/order_management/orders.py:2180`, `analytics_connector/reused_tools.py:907` |
| 6 | Sales targets achievement (Delivered metric) | SO lines; linked DO qty on the DO date, capped at ordered, plus AutoCount residual on the SO date | `services/sales/achievement_service.py:28-35` (`delivered_by_date`) |

Ordered and outstanding (1, 4, 5 on their other bases) do not change.

## Rule (proposed)

Delivered = DO lines, one shared dataset: `datasets/delivery_order_lines.py` (not cancelled, not deleted, dated, not
`REP...`), filed by the DO's own date, amount = the DO line's amount (AutoCount line total, or the legacy DOC total
split, as #1401). The sales order behind a line is found ONCE (line link `order_lines.sales_order_line_id`, else the DO
header's `orders.sales_order_id`, else `from_doc_no` SO same company), and channel AND sales agent both come from that
SO. Today only channel uses the three-way lookup; the agent reads the header link alone, which is NULL on every DO in
dev, so a DO-based agent ranking would read "(no agent)" for every line. Surfaces 1, 2, 4, 5 move onto it. 3 already
is. 6: Q4.

## Examples (before -> after)

1. SRT102-RG, Project, 2026, ranking by sales agent: 4 lines, 6 pcs, 4 customers, RM 943.12 -> 1 line, 1 pc,
   RM 148.92 (the sales report's own figure; the two paths agree after). Crew measured both sides.
2. The same, no channel: the ranking counts SO lines dated 2026 whatever DO delivered them; after, every 2026 DO line,
   including the 31 lines (95 pcs) with no SO. Numbers: SQL A below.
3. A Sep SO line delivered by a 14 Oct DO: before in Sep, after in Oct (the SALES-REPORT-CHANNEL card example 1).
4. Yearly comparison, Delivered, Project, 2026 by month: before SO month, after DO month. Numbers: SQL B below.
5. A legacy DO with no SO link (Apr to Aug 2026 old-system DOs): before, only its SO-side delivered qty counted (if
   AutoCount stamped `qty_delivered`); after, counted on the DO line. Numbers: SQL A by month.

## Edge cases

- DO line with no SO (31 lines, 95 pcs in 2026): counts in every no-channel total and ranking; channel = none,
  sales agent = "(no agent)". With a channel asked it is out, and the bot says nothing about it today. Q1.
- Partial deliveries across months: each DO line in its own DO month; an SO line delivered in Sep and Oct splits
  across both. No cap at ordered (a DO over the SO qty counts as delivered). Q5.
- Returns / credit notes: RMA and CG DOs carry no lines in dev, so they are out before and after; credit notes are
  invoiced basis only, untouched. A consignment SO's DO line counts on the DO basis (the SO path left consignment
  SOs out): measure with SQL A (`doc_type`).
- "Orders" count measure on delivered: counts SOs today. Q2.
- Agent fill rate note: counts SOs on the line date. Q3.

## Questions

- **Q1** Channel asked, DO lines with no SO. (a) Out, silently (today's sales report rule). (b) Out, and the reply adds
  one line "N pcs delivered on DOs with no sales order are in no channel". **Recommend (a)**: same as an SO with no
  type; (b) is a new reply line the owner can ask for later.
- **Q2** The "orders" count on delivered. (a) Distinct DOs. (b) Distinct SOs found behind the lines (a DO with no SO
  not counted). **Recommend (a)**: the delivered row is a DO line, so "orders" counts what was delivered on.
- **Q3** Agent fill rate note on a delivered ranking. (a) Share of the window's DO lines' SOs (DO date) carrying an
  agent. (b) Leave on the SO line date. **Recommend (a)**: the note must describe the rows the ranking counted.
- **Q4** Targets achievement (surface 6) already dates delivered by the DO, but only SO-linked DO lines, capped, plus
  an AutoCount residual. (a) Leave it (it is DO-dated; its credit is per SO agent/customer and its cap is a target
  rule). (b) Move it onto the shared dataset in this lane. **Recommend (a)**: already DO-dated; moving it is a
  separate L-size lane with its own tests (#1319 shape).
- **Q5** Legacy top-selling route (surface 5, on no chatbot row). (a) Move its delivered basis onto the DO dataset.
  (b) Leave it and name it in the plan as retired-in-place. **Recommend (a)**: "everywhere"; the analytics connector
  still exposes it, and a second delivered number is the bug this lane removes.

## Read-only SQL for the before/after table (crew, `sorento_prod_1020`)

```sql
-- A: 2026 delivered by DO month, with/without an SO behind the line, by channel
WITH l AS (
  SELECT ol.id, o.order_date, ol.quantity,
         COALESCE((SELECT so.demand_class FROM sales_order_lines sol JOIN sales_orders so ON so.id = sol.sales_order_id
                   WHERE sol.id = ol.sales_order_line_id),
                  (SELECT so.demand_class FROM sales_orders so WHERE so.id = o.sales_order_id),
                  (SELECT so.demand_class FROM sales_orders so WHERE ol.from_doc_type = 'SO'
                     AND so.so_number = ol.from_doc_no AND so.company_id = ol.company_id)) AS channel
  FROM order_lines ol JOIN orders o ON o.id = ol.order_id
  WHERE NOT o.is_cancelled AND o.deleted_at IS NULL AND o.order_date >= '2026-01-01' AND o.order_date < '2027-01-01'
    AND o.order_number NOT LIKE 'REP%')
SELECT to_char(order_date, 'YYYY-MM') AS m, COALESCE(channel, '(none)') AS channel, count(*) AS lines, sum(quantity) AS qty
FROM l GROUP BY 1, 2 ORDER BY 1, 2;
-- B: today's Yearly comparison Delivered by SO month, for the same year
SELECT to_char(so.order_date, 'YYYY-MM') AS m, so.demand_class,
       sum(LEAST(sol.qty_delivered, sol.qty_ordered)) AS qty
FROM sales_order_lines sol JOIN sales_orders so ON so.id = sol.sales_order_id
WHERE so.status <> 'cancelled' AND sol.line_status <> 'cancelled' AND so.doc_type <> 'consignment'
  AND so.order_date >= '2026-01-01' AND so.order_date < '2027-01-01'
GROUP BY 1, 2 ORDER BY 1, 2;
```
