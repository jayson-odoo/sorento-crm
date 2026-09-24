# UAC - Chatbot: top X hot selling items by category / customer / sales agent / date range

Plan: `PLAN-chatbot-top-x-hot-selling-24sep.md`. Numbering: AC-19xx. Status: draft, pre-grill
(24 Sep 2026). Each criterion names its evidence (pytest / golden fixture / console check).
"Contact" = a Respond.io contact through `/api/v1/external/chat/turn`. Issue #1171.

Defaults written as `[Qn]` are proposals awaiting the grill answer to question n in the plan;
the criterion is rewritten with the ruling before the tester writes it red.

## Journey

Actor: a management or sales contact on WhatsApp holding the sales report grant
(`sales_orders.sales_report`). They want to know what is moving, for the whole book or for
one customer, one category, one salesperson, one period. The system already knows the
contact and its grants, its companies, every customer ledger, the product master and its
categories, the salesperson master, and every SO line AutoCount has pushed.

1. They type "top 5 selling items last month". One reply: a header naming the ranking, the
   metric and every filter axis (`all` where none was named), then five numbered rows, each
   `code name: Qty q, RM v`. Nothing is asked.
2. They type "top 10 for hanlim this quarter". Same list filtered to the HANLIM ledgers; an
   ambiguous name goes through the existing customer picker and "1" / "all" continues this ask.
3. They type "top 3 kitchen sinks in 2026". Same list filtered to that product category.
4. They type "top 5 by sales agent SEAN I this year". Same list filtered to that agent's SOs.
5. They type "by amount". The same filters re-run ranked by amount.
6. A contact without the grant gets `Sales report is not enabled for your account.` and no
   fetch happens.

Other stakeholders: nobody is notified; this is a read.

## Measured

Carried from `chatbot-sales-report-acceptance-criteria.md` "Measured" (prod copy
`sorento_ai_automation_0918_1900`, 19 Sep 2026): `sales_order_lines.line_total` is the money
source (142,401 of 144,318 lines dated 2026 satisfy `qty_ordered * unit_price - discount`);
the DO tables are not usable as money; 22,717 priced lines dated 2026 carry `line_total = 0`;
`required_date` is filled on 143,118 of 144,318 lines dated 2026; `demand_class` retail
30,571 / project 5,210 / null 170.

To measure before the grill (no database in the planning checkout): `sales_orders.
sales_agent_id` fill rate on SOs dated 2026; distinct `product_categories` reached by 2026
lines and the `products.category_id` null rate on sold products; row count and timing of a
whole-book `GROUP BY product_id` over 2026 and over all dates.

## Rulings (owner, grill pending)

| # | Ruling |
|---|---|
| H1 | Money and quantity come from `sales_orders` + `sales_order_lines` only, the sales report's own predicate: cancelled SOs and cancelled lines never count, a line with neither `required_date` nor its SO's `order_date` is excluded. |
| H2 | `[Q3]` Quantity = `qty_ordered`, amount = `line_total`, per line, summed per product over the window. |
| H3 | Ranking: `rank_by` desc, the other metric desc, `product_code` asc. Sorted in the route, in SQL; the presenter never re-sorts. |
| H4 | `[Q1]` `top_n` defaults to 5 when the message names none; the route clamps above 10 to 10 and 422s below 1. |
| H5 | `[Q2]` `rank_by` defaults to `qty` when the message names neither metric. |
| H6 | `[Q4]` No date in the message = the current calendar year (Malaysia time), built in the lane, never the route; "all dates" said in words turns it off. |
| H7 | Every filter is optional; none is required. Filters AND. |
| H8 | `[Q6]` A category word is a filter over `products.category_id`, never a breakdown. |
| H9 | `[Q7]` A sales agent word filters `sales_orders.sales_agent_id`. Ships only when #1168 / #1170 confirm `sales_agents` as the master (plan S5). |
| H10 | `[Q8]` `sales_channel` applies: dealer = `demand_class = 'retail'`, project = `'project'`, neither = all including null-class. |
| H11 | `[Q5]` Access: the existing per-contact reveal key `sales_orders.sales_report`, no new key. Without it the one denial line and no fetch. Company scope per contact applies. |
| H12 | `[Q10]` One reply, no detail offer, no pending kind. |
| H13 | The parser decides the ask (`order_status: "top_selling"`), the metric (`rank_by`) and the count (`top_n`). No word table in deterministic code. |
| H14 | Amounts print `RM 1,234.50`; quantities print thousands-separated whole units; no dash characters anywhere in the output. |

## Phase 1 - the reply (presenter over mock JSON)

- **AC-1901 [FE][T]** Given a body with five rows and no filters, when presented, then the text
  equals golden `top-selling-whole-book.txt` byte for byte: `Top 5 selling items`,
  `Ranked by: Quantity`, `Customer: all`, `Category: all`, `Sales agent: all`, `Channel: all`,
  `Delivery date: 01/01/2026 to 31/12/2026`, a blank line, then rows in the order given.
  Evidence: golden fixture.
- **AC-1902 [FE][T]** Each row prints `n. CODE Name: Qty q, RM v` with `n` the body's own
  `rank`. A row with a null `product_name` prints the code alone before the colon.
  Evidence: pytest, presenter.
- **AC-1903 [FE][T]** Any header axis absent from the body prints `all`, never an omitted
  line. `Channel` prints `Dealer`, `Project` or `all`. Evidence: pytest.
- **AC-1904 [FE][T]** `rank_by: "qty"` prints `Ranked by: Quantity`; `"amount"` prints
  `Ranked by: Amount`. The title prints the body's `top_n` (`Top 3 selling items`).
  Evidence: goldens.
- **AC-1905 [FE][T]** A body carrying more than 10 rows prints the first 10 only.
  Evidence: pytest.
- **AC-1906 [FE][T]** A body with no rows prints the header, a blank line, `No sales found.`
  and nothing after it; `has_result` is false. Evidence: golden fixture.
- **AC-1907 [FE][T]** Rows print in the order given: an unsorted body comes out in input
  order. Evidence: pytest.
- **AC-1908 [FE][T]** Money prints `RM 1,234.50`, zero `RM 0.00`; quantity `1,240`; no dash
  characters anywhere. Evidence: pytest plus the dash guard.

## Phase 2 - route and service

- **AC-1920 [BE][T]** Given seeded lines over four products, `rank_by=qty` orders by summed
  `qty_ordered` desc, ties by summed `line_total` desc, then `product_code` asc; `rank_by=amount`
  orders by summed `line_total` desc, ties by qty desc, then code asc. Any other `rank_by` is
  422. Evidence: pytest, Postgres.
- **AC-1921 [BE][T]** No `top_n` returns 5 rows (H4); `top_n=25` returns 10 and echoes
  `top_n: 10`; `top_n=0` is 422. Evidence: pytest.
- **AC-1922 [BE][T]** `date_from` / `date_to` filter on `COALESCE(required_date, order_date)`,
  accept `_parse_flex_date` formats, 422 otherwise; no dates = every line (the default window is
  the lane's, not the route's). Evidence: pytest.
- **AC-1923 [BE][T]** `customer_ids` filters `sales_orders.customer_id IN`; `customer_query`
  ILIKEs `customer_name`, under 3 characters is 422; the echo `customer_name` is built by
  `_customer_echo`. Evidence: pytest.
- **AC-1924 [BE][T]** `category_ids` filters `products.category_id IN`; a product with no
  category is absent under a category filter and present without one; the echo
  `category_name` lists the matched `category_name`s comma joined. Evidence: pytest.
- **AC-1925 [BE][T]** `channel=dealer` counts only `demand_class = 'retail'`, `project` only
  `'project'`, none counts both and null-class; any other value 422. Evidence: pytest.
- **AC-1926 [BE][T]** A cancelled SO and a cancelled line contribute to nothing; a line with
  neither bucket date is excluded. Evidence: pytest.
- **AC-1927 [BE][T]** Customer + category + channel + dates together AND; a row that fails any
  one is absent. Evidence: pytest, one seed with a foil per axis.
- **AC-1928 [BE][T]** Every field of `TopSellingResponse` is declared and asserted present
  through the HTTP route. Evidence: pytest.
- **AC-1929 [BE][T]** No credential 401; a user without `order_management.orders.view` 403;
  API key with act-as user 200; `contact_id` without `space_id` 422; a contact without
  `sales_orders.sales_report` 403 `sales_report_not_enabled`; a contact-scoped key sees only its
  companies' lines. Evidence: pytest.
- **AC-1930 [BE][T]** Lines with `line_total = 0` rank by quantity unchanged and contribute
  `RM 0.00` to amount `[Q9]`. Evidence: pytest.

## Phase 2 - MCP tool

- **AC-1940 [BE][T]** The catalog lists `crm_top_selling_report` with path
  `/api/v1/order-management/top-selling`, domain `orders`, params `top_n`, `rank_by`,
  `customer_ids`, `customer_query`, `category_ids`, `sales_agent_ids`, `channel`, `date_from`,
  `date_to`, `contact_id`, `space_id`, and `restricted_fields = (("sales_orders.sales_report",
  "Sales report"),)`. Evidence: pytest, MCP.
- **AC-1941 [BE][T]** `fetch.CHATBOT_READ_ONLY_TOOLS` contains it through the `order` domain
  row; `test_tool_pool_is_read_only.py` still equals the catalogue's read-only set;
  `mcp_tool_domains` maps it to `orders`; the in-app assistant bootstrap does NOT carry it.
  Evidence: pytest.

## Phase 2 - the lane

- **AC-1950 [BE][T]** Domain `order` AND `order_status = "top_selling"` picks
  `crm_top_selling_report` with or without a resolved subject; `sales_report` still picks
  `crm_sales_report`; every outstanding status still picks `crm_outstanding_report`.
  Evidence: pytest, lane.
- **AC-1951 [BE][T]** A contact without `sales_orders.sales_report` gets the denial line, the
  fetch function is never called, no picker renders for an ambiguous customer, nothing is
  armed. Evidence: pytest with a fetch spy, both engine seams.
- **AC-1952 [BE][T]** `rank_by` and `top_n` reach the tool from the parser's emission only;
  absent `rank_by` sends no param (the route defaults); absent `top_n` sends no param. The
  lane never reads the message text. Evidence: pytest.
- **AC-1953 [BE][T]** Parsed dates map to `date_from` / `date_to`; a resolved customer to
  `customer_ids` (carried ids win on a pick turn); a resolved category to `category_ids`;
  `sales_channel` to `channel`; no date and no "all dates" word builds the current calendar
  year (H6); `broaden_axis == "date"` sends no dates. `product_ids` and `warehouse_ids` are
  popped. Evidence: pytest.
- **AC-1954 [BE][T]** A parser entity `{hint: "category", hint_confident: true}` on a
  `top_selling` ask resolves against `product_categories` under domain `order`, never as a
  customer; `gate.ALLOWED["order"]` admits it. Evidence: pytest against the real resolver.
- **AC-1955 [BE][T]** An ambiguous customer on a `top_selling` ask renders the existing picker
  with no `has DO` hint; "1" or "all" continues the ask with the original `top_n`, `rank_by`,
  dates and channel. Evidence: pytest.
- **AC-1956 [BE][T]** A follow-up naming only a metric ("by amount") under a carried
  `focus.status == "top_selling"` re-runs with the carried customer / category / dates and the
  new `rank_by`; a follow-up naming a new subject is a new ask. Evidence: pytest.
- **AC-1957 [BE][T]** A miss (`has_result: false`) takes the not-found path so the escalate
  offer follows unchanged; a hit arms no pending and offers nothing. Evidence: pytest.
- **AC-1958 [BE][T]** The generic search-scope header is skipped for
  `crm_top_selling_report`. Evidence: pytest.
- **AC-1959 [BE][T]** `rank_by` is in the strict schema's `properties` and `required` and in
  `TOLERATED_ABSENT`; the prompt fallback and its migration teach `order_status:
  "top_selling"` and `rank_by`; `test_parser_prompt_is_live.py` passes. Evidence: pytest.
- **AC-1960 [BE][T]** "last 3 DO for hanlim" (a plain `top_n` on an order list) still reaches
  `crm_order_management_orders_list` with `limit=3`; nothing about the growth r1 `top_n` path
  changes. Evidence: pytest, existing tests stay green.

## Phase 2 - sales agent slot (S5, gated on #1168 / #1170)

- **AC-1970 [BE][T]** `sales_agent` is in `contracts.ENTITY_HINTS` and has a kind row
  (`resolver_source: sales_agents`, `did_you_mean: true`, `optional_filter`); the resolver
  matches `sales_agents.sales_agent` (code, case-insensitive, trimmed) and `person_label`.
  Evidence: pytest.
- **AC-1971 [BE][T]** `sales_agent_ids` filters `sales_orders.sales_agent_id IN` on the route;
  the lane maps a resolved agent entity to it; the echo `sales_agent` prints the agent code(s).
  Evidence: pytest, route and lane.
- **AC-1972 [BE][T]** Agent + customer AND: a customer's SO under another agent code is absent,
  no picker. Evidence: pytest.

## Phase 3 - live

- **AC-1980 [E2E]** Console check `tests/chatbot/console_cases/2026-09-24-top-selling.yaml`
  against the lane stack, graded line by line: the six journey messages, one fuzzy phrasing
  ("what's selling well this month"), one Malay phrasing ("barang paling laku bulan lepas"),
  and two traps ("last 3 DO for hanlim" must reach the order list with `limit=3`; "sales report
  for hanlim" must still reach `crm_sales_report`). Then once against production after the
  deploy. Evidence: console logs under `evidence/top-selling/`.
- **AC-1981 [E2E]** On the prod copy, the whole-book top 5 for the current year equals an
  independent SQL over the same predicate, quantity and amount to the cent. Evidence: SQL plus
  console log.

## [UX]

WhatsApp text only. Nothing animates. No screen is touched.

## Backlog (triggers, not built)

- Breakdown mode (top N per category / per agent): Q6 rules for it, or the owner asks "per
  category" on the live console.
- Warehouse filter: the owner asks "top 5 at BRW".
- Family collapsing (rank base codes): the top 5 comes back as five variants of one product.
- `sales_agent` on `group_by` and on the sales report: the sales module (#1170) needs it.
