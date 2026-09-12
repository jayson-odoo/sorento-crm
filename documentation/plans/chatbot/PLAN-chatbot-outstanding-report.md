# PLAN - Chatbot outstanding report: SO backlog and DO pending, one shape, four filters

Status: APPROVED by owner 12 Sep 2026 on the lavish page; lane `feat/chatbot-outstanding-report` (worktree `.claude/worktrees/chatbot-outstanding-report`, test DB `sorento_osr_ci`) S1 to S3b BUILT and rebased onto `origin/main` 13 Sep; S4 brief being rewritten for main's own picker mechanism (owner ruling 13 Sep: this lane ships without #847).
UAC: `chatbot-outstanding-report-acceptance-criteria.md` (AC-11xx).
Base: `origin/main`. Owner ruling 13 Sep: ships without #847.
Related: `PLAN-do-search-and-mcp-feedback-7sep.md` (built the `so_outstanding` bucket this
plan stops using for the chatbot).

## Why

The owner asked "Dealer outstanding quantity SRTWT7445 in 2026" and got a summary whose
three numbers cannot reconcile (Ordered 26,723, Transferred 24,565, SO Outstanding 3) and a
false miss for a year that holds real 2026 orders. Top management will quote these numbers.
Three defects and one missing definition, all measured (UAC "Measured"):

1. Ordered/Transferred sum every line including cancelled and retired-provisional
   duplicates; Outstanding sums only live lines. Different populations, so the identity
   Ordered = Transferred + Outstanding never holds.
2. The date window travels as `actual_delivery_date_*`; the SO arm drops it and the DO
   arm uses it to exclude every undelivered DO. A dated "outstanding" ask can only miss.
3. Rows are SO lines, so one SO prints once per line, with no customer and no location.
4. "Outstanding" is two different numbers at Sorento, and DO is raised before goods leave,
   so both matter: SO backlog (booked, not yet transferred to DO) and DO pending (DO raised,
   not yet delivered). The bot must name which, and ask when the message does not say.

## Decisions (owner rulings, 12 Sep 2026)

| # | Ruling |
|---|---|
| D1 | Two named numbers. Block titles are `Sales order outstanding` and `Delivery order pending`. The bare word never appears as a heading. |
| D2 | Missing scope word → ONE open question `outstanding_scope` (Sales orders / Delivery orders / Both). Scope words in the message bind without asking. |
| D3 | No date in the message = all dates, printed as `Order date: all`. A parsed window filters SO on `sales_orders.order_date` and DO on `orders.order_date`. No date question in this lane (trigger in UAC backlog). |
| D4 | Cancelled quantity is never shown and never summed. |
| D5 | Location grammar: a token equal to a warehouse code is that code only (`BRW` = `BRW`); a token that is a `-suffix` is every code with that suffix (`IB` = `BRW-IB`, `MWH-IB`). Resolved against the `warehouses` table. |
| D6 | Grain: totals sum lines; the list is one row per SO with lines rolled up; the DO list one row per DO. By location and By customer are printed INSIDE each block: SO figures under the SO block, DO figures under the DO block (owner markup, 12 Sep). |
| D7 | Customer filter by `customer_name` only. Debtor code is not an input and not printed. |
| D8 | Reply is `Label: value` lines, no `.` separators, exact date ranges (`dd/mm/yyyy to dd/mm/yyyy`), no "oldest", no "+N more". Every row is sent; n8n chunks long messages already. |
| D9 | RULED on the lavish page 12 Sep: SO breakdown lines read `name: ordered (O/S: outstanding)`, DO breakdown lines `name: DO qty (O/S: pending)`, the suffix shape the stock answer already uses (`presenters.py:1259-1287`). Sub-headings print `*_By location_*` / `*_By customer_*` (bold italic; WhatsApp has no underline). |
| D10 | Detail is offered as a numbered reply (`1. Sales order list`, `2. Delivery order list`), served from the report the bot already holds, no second fetch. |
| D11 | The chatbot stops calling the `so_outstanding` bucket for outstanding asks. That bucket and `include_pipeline` stay for their other readers; repairing them is backlog (trigger in UAC). |
| D13 | Access (owner ruling on the lavish page): every `order_enquiries` contact sees DO figures, as today. SO figures are gated per contact by ONE field-reveal key `sales_orders.outstanding` on Contacts > Access (same table and screen as `purchase_orders.placed`, which already gates a whole answer family: `answer.py:936, 1113-1122`). Default deny. Without the key the scope question is never asked (scope is DO) and an explicit SO ask prints `Sales order figures are not enabled for your account.` then the DO block. Checked before any fetch. No new table, no new agent. |
| D12 | The existing order-list MCP tools additionally expose `customer_query` and `warehouse_codes`. NOT `order_date_*`: the DO list tool's dates are actual delivery dates by a standing ruling (`sorento_crm_mcp/tests/test_catalog_compile.py::test_orders_list_uses_actual_delivery_date_only`), and pending DOs by order date are served by the new report route instead. |

## The reply (contract for Phase 1)

```
Product: SRTWT7445
Customer: all
Location: IB (BRW-IB, MWH-IB)
Order date: 01/01/2026 to 31/12/2026

*Sales order outstanding*
Ordered: 2,411
Transferred to DO: 0
Outstanding: 2,411
Sales orders: 12
Order date range: 05/01/2026 to 28/08/2026
*_By location_*
BRW-IB: 1,200 (O/S: 1,200)
MWH-IB: 1,211 (O/S: 1,211)
*_By customer_*
Dealer A Sdn Bhd: 900 (O/S: 900)
Dealer B Trading: 811 (O/S: 811)
Dealer C Hardware: 700 (O/S: 700)

*Delivery order pending*
DO qty: 640
Delivered: 0
Pending: 640
Delivery orders: 3
DO date range: 03/02/2026 to 30/08/2026
*_By location_*
BRW-IB: 640 (O/S: 640)
*_By customer_*
Dealer A Sdn Bhd: 640 (O/S: 640)

Reply with a number for detail:
1. Sales order list
2. Delivery order list
```

Scope question (D2):

```
Product: SRTWT7445
Outstanding for which document?
1. Sales orders (not yet transferred to DO)
2. Delivery orders (not yet delivered)
3. Both
```

Detail, SO list (D6, D10), one item per SO:

```
1. *SO Number:* SO331785
*Customer:* Dealer A Sdn Bhd
*Location:* BRW-BB
*Ordered:* 410
*Transferred to DO:* 0
*Outstanding:* 410
*Order Date:* 20/12/2024
```

## Backend contract

`GET /api/v1/order-management/outstanding-report`

| param | type | rule |
|---|---|---|
| `product_code` | str, required | exact, case-insensitive (AC-1119) |
| `scope` | `so` / `do` / `both` | default `both` |
| `customer_query` | str | `customers.customer_name ILIKE %q%` |
| `warehouse_codes` | csv | exact codes; resolution of tokens happens in the chatbot lane, not here |
| `order_date_from`, `order_date_to` | date | SO on `sales_orders.order_date`, DO on `orders.order_date` |

Response (`OutstandingReportResponse`, every field declared):

```
{
  "product_code": "SRTWT7445",
  "customer_name": null | "Dealer A Sdn Bhd",
  "warehouse_codes": ["BRW-IB", "MWH-IB"] | [],
  "order_date_from": "2026-01-01" | null, "order_date_to": ... | null,
  "so": { "ordered_qty", "transferred_qty", "outstanding_qty", "so_count",
          "order_date_min", "order_date_max" },              # absent when scope=do
  "do": { "do_qty", "delivered_qty", "pending_qty", "do_count",
          "do_date_min", "do_date_max" },                    # absent when scope=so
  "so_by_location": [ { "code": "BRW-IB" | null, "ordered_qty", "outstanding_qty" } ],
  "so_by_customer": [ { "customer_name", "ordered_qty", "outstanding_qty" } ],
  "do_by_location": [ { "code" | null, "do_qty", "pending_qty" } ],
  "do_by_customer": [ { "customer_name", "do_qty", "pending_qty" } ],
  "so_rows": [ { "so_number", "customer_name", "location", "ordered_qty",
                 "transferred_qty", "outstanding_qty", "order_date" } ],
  "do_rows": [ { "do_number", "customer_name", "location", "do_qty",
                 "delivered_qty", "pending_qty", "do_date" } ]
}
```

SO population (one predicate, used by every SO figure):
`sales_orders.status = 'open' AND sales_order_lines.line_status = 'open' AND qty_ordered -
qty_delivered > 0` joined to the product and the optional filters. `ordered_qty = SUM
qty_ordered`, `transferred_qty = SUM qty_delivered`, `outstanding_qty = SUM (qty_ordered -
qty_delivered)`. The identity is then arithmetic, not luck.

DO population: `OrderService._outstanding_clause` (`order_service.py:67-93`) for pending,
`_delivered_clause` for delivered, qty from `order_lines.quantity` for the product, location
from `order_lines.warehouse_id`. `do_qty = delivered_qty + pending_qty` over the DOs in the
window, so the DO block carries the same identity as the SO block (captain ruling 12 Sep).

One service function `outstanding_report(db, filters) -> dict` in a new
`app/services/outstanding_report_service.py` (about 150 lines: two base queries, four
aggregations). No registry, no list-query resource: the chatbot is the only reader and the
shape is a report, not a grid.

## Slices

| slice | phase | what | files |
|---|---|---|---|
| S1 | 1 | Presenter over mock report JSON; golden fixtures for both / so / do / miss / detail lists; dash guard test | `sorento_crm_mcp/sorento_crm_mcp/presenters.py` (`_outstanding_report`, `_outstanding_detail`), `documentation/plans/chatbot/samples/outstanding-report-*.txt`, `sorento_crm_mcp/tests/test_presenters_outstanding.py` |
| S2 | 2 | Route + service + response model + tests (tester first) | `app/api/v1/order_management/orders.py` (new route), `app/services/outstanding_report_service.py`, `app/schemas/order_management.py`, `tests/test_outstanding_report.py` |
| S3 | 2 | MCP tool `crm_outstanding_report`; `customer_query` + `warehouse_codes` on the two order-list tools (no `order_date_*`); backend `warehouse_codes` on `GET /orders` and `/orders/by-product`; tool seeding | `sorento_crm_mcp/sorento_crm_mcp/catalog.py`, `orders.py`, `order_service.py:843-853`, `sorento_crm_mcp/tests/test_catalog.py` |
| S4 | 2 | Lane wiring: scope words and `outstanding_scope` question, location token resolution, `order_date_*` mapping, `detail_pick`, header lines, miss lines, D13 gate (`sales_orders.outstanding`: no scope question and DO scope without the key, refusal line on an explicit SO ask), key registered on the reveal screen | `app/services/chatbot/contracts.py` (two kinds), `dialogue/open_question.py` (two handlers), `lanes/business/fetch.py` (tool pick + DATE_PARAMS entry + location resolver), `lanes/business/answer.py`, `tail/compile_state.py` (`Location:` axis), tests `test_open_question.py`, `test_outstanding_lane.py`, one world under `tests/chatbot/worlds/` |
| S5 | 3 | reviewer + browser-less console check (chatbot-verification.md) in parallel; guide-writer updates the chatbot user guide with the six journey messages | `documentation/plans/chatbot/evidence/outstanding-report/`, `documentation/user-guides/` |

Phase 1 for a chatbot lane is the presenter against a mock: the "UI" is the WhatsApp text,
and the golden files are its screenshots. The captain reviews the golden files on the lavish
page before S2 starts.

## Tester's list (S2 and S4, one line per AC)

- AC-1110 `test_so_figures_share_one_population`: 10/3/7 from four seeded lines.
- AC-1111 `test_order_date_window_filters_so_and_do`: 2025 row excluded under a 2026 window.
- AC-1112 `test_warehouse_codes_filter_and_null_bucket`: filtered out when set; `code=None` when not.
- AC-1113 `test_customer_query_matches_name_not_debtor_code`.
- AC-1114 `test_so_rows_roll_up_lines_per_so`: 205 + 205 → one row, 410, locations joined.
- AC-1115 `test_do_block_pending_and_delivered`.
- AC-1116 `test_breakdowns_sum_to_totals`.
- AC-1117 `test_scope_omits_block_and_response_model_keeps_every_field`.
- AC-1118 `test_route_permission_and_api_key_act_as`.
- AC-1119 `test_product_code_exact_no_siblings`.
- AC-1120 `test_catalog_lists_outstanding_report_tool`; AC-1121 `test_order_list_tools_expose_new_params`.
- AC-1130 `test_missing_scope_asks_outstanding_scope`; AC-1131 `test_scope_words_bind` (table).
- AC-1132 `test_scope_answer_runs_report_with_carried_filters`.
- AC-1133 `test_location_token_resolution` (exact / suffix / none).
- AC-1134 `test_no_date_means_all_and_window_maps_to_order_date`.
- AC-1135 `test_detail_pick_renders_from_held_report`.
- AC-1136 `test_customer_name_becomes_customer_query`.
- AC-1140 `test_no_so_key_skips_question_and_runs_do_only`; AC-1141 `test_no_so_key_explicit_so_ask_refuses_then_do_block`; AC-1142 `test_so_key_listed_on_reveal_screen`.

## Design brief

Surface: WhatsApp text. Density: one report per ask, read a few times a day by management.
Nothing animates. No emoji. Bold only on block titles and detail-row labels (the existing
`*Label:*` convention).

## Risks

- `feat/chatbot-focus` is mid-build (14 local commits, never pushed). This lane inherits
  its churn; the captain rebases S4 once #847's open-question API settles. S1 to S3 do not
  touch the dialogue code and can start now.
- The `warehouses` table has codes with `/` (`SPARE/P`) and no `-`; suffix resolution
  splits on the LAST `-` only and ignores codes without one.
- 25,059 SO lines carry NULL warehouse; the `Unassigned` bucket will be large for older
  products. Printed, not hidden (D8 transparency).
