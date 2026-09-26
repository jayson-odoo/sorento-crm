# UAC - Chatbot: top X hot selling items by category / customer / sales agent / date range

Plan: `PLAN-chatbot-top-x-hot-selling-24sep.md`. Numbering: AC-19xx. Status: grilled
(26 Sep 2026; S2 + S3 built on PR #1263 and S4 on the combined lane PR, "As built" lines below; owner rulings from PR #1175 folded in as dated "Owner ruling 26 Sep" lines). Each criterion names its evidence (pytest / golden fixture / console check).
"Contact" = a Respond.io contact through `/api/v1/external/chat/turn`. Issue #1171.

Defaults written as `[Qn]` were proposals awaiting the grill answer to question n in the plan.
Every one is now answered: the ruling follows as an "Owner ruling 26 Sep" line and the
criterion is rewritten to it. No criterion was deleted; a superseded sentence says so.

## Journey

Actor: a management or sales contact on WhatsApp holding the sales report grant
(`sales_orders.sales_report`). They want to know what is moving, for the whole book or for
one customer, one category, one salesperson, one period. The system already knows the
contact and its grants, its companies, every customer ledger, the product master and its
categories, the salesperson master, and every SO line AutoCount has pushed.

1. They type "top 5 selling items last month". One reply: a header naming the ranking, the
   metric and every filter axis (`all` where none was named), then five numbered rows, each
   `code name: Qty q, RM v`. Nothing is asked.
   Owner ruling 26 Sep: the metric is required, so this exact message gets "By quantity or by
   amount?" first; with "by quantity" in it, the reply also names the basis (delivered), the
   full count of items with sales, and ends with the detail offer.
2. They type "top 10 for hanlim this quarter". Same list filtered to the HANLIM ledgers; an
   ambiguous name goes through the existing customer picker and "1" / "all" continues this ask.
3. They type "top 3 kitchen sinks in 2026". Same list filtered to that product category.
4. They type "top 5 by sales agent SEAN I this year". Same list filtered to that agent's SOs.
5. They type "by amount". The same filters re-run ranked by amount.
   Owner ruling 26 Sep, added steps: "ordered" re-runs on the ordered basis; a rank number
   opens that item's customers and months; "which category sells most" ranks categories and
   an ambiguous "by category" is asked; no number and a long list gets "How many ... do you
   want to see?" and no partial list, no "more"; a dealer naming another customer gets
   "Sorry, I can only share sales figures for your own account."
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

## Rulings (owner, grilled 26 Sep 2026)

| # | Ruling |
|---|---|
| H1 | Money and quantity come from `sales_orders` + `sales_order_lines` only, the sales report's own predicate: cancelled SOs and cancelled lines never count, a line with neither `required_date` nor its SO's `order_date` is excluded. |
| H2 | `[Q3]` Quantity = `qty_ordered`, amount = `line_total`, per line, summed per product over the window. Owner ruling 26 Sep: both bases are supported. Delivered (transferred to DO) = `LEAST(qty_delivered, qty_ordered)` and its amount (the sales report's confirmed pair) is the default and the header says `Basis: Delivered (transferred to DO)`; ordered = `qty_ordered` / `line_total` when the message or a follow-up says "ordered". A message ambiguous between them is asked. |
| H3 | Ranking: `rank_by` desc, the other metric desc, `product_code` asc. Sorted in the route, in SQL; the presenter never re-sorts. |
| H4 | `[Q1]` `top_n` defaults to 5 when the message names none; the route clamps above 10 to 10 and 422s below 1. Owner ruling 26 Sep (superseding): no default N. A named N ranks that many, 1 to 100 (above 100 clamps to 100, below 1 is 422). No N = every ranked row, no paging, no "more" / "next" / "lagi" anywhere (amended 01:50Z). When there is no N and the list would not fit one WhatsApp message (setting `chatbot_top_selling_one_message_rows`, default 50), no partial list is sent: the header states the count and the bot asks how many to show (01:55Z). Amended by the owner on PR #1258 (05:32Z): n8n already chunks long messages, so there is no size threshold and no setting: with no N the bot always states the count and asks how many (a single row is sent), and a named N goes out whole. |
| H5 | `[Q2]` `rank_by` defaults to `qty` when the message names neither metric. Owner ruling 26 Sep (superseding): no default metric. Neither named = the bot asks `By quantity or by amount?` and fetches nothing; the route 422s a missing `rank_by`. |
| H6 | `[Q4]` No date in the message = the current calendar year (Malaysia time), built in the lane, never the route; "all dates" said in words turns it off. Owner ruling 26 Sep: confirmed. Months and ranges supported; "by month" that could be a month filter or a per-month breakdown is asked. |
| H7 | Every filter is optional; none is required. Filters AND. |
| H8 | `[Q6]` A category word is a filter over `products.category_id`, never a breakdown. Owner ruling 26 Sep (superseding "never a breakdown"): both. A named category is a filter ("top items in category A"); "which category sells most" ranks categories (group `category`); a message that could be either is asked, never assumed. |
| H9 | `[Q7]` A sales agent word filters `sales_orders.sales_agent_id`. Ships only when #1168 / #1170 confirm `sales_agents` as the master (plan S5). Owner ruling 26 Sep: attribution is `sales_orders.sales_agent_id`; the gate is lifted, S5 is not waiting. A thinly filled agent field prints a fill-rate note in the header. |
| H10 | `[Q8]` Owner ruling 26 Sep: yes. `sales_channel` applies: dealer = `demand_class = 'retail'`, project = `'project'`, neither = all including null-class. |
| H11 | `[Q5]` Access: the existing per-contact reveal key `sales_orders.sales_report`, no new key. Without it the one denial line and no fetch. Company scope per contact applies. Owner ruling 26 Sep: staff may ask across all customers; a dealer contact is forced to its own ledgers (enforced in the route too) and a named other customer gets `Sorry, I can only share sales figures for your own account.` with no fetch. |
| H12 | `[Q10]` One reply, no detail offer, no pending kind. Owner ruling 26 Sep (superseding): a detail offer is required. Item ranking ends `Reply with a rank number to see that item's customers and months.`; category ranking ends `Reply with a rank number to see that category's top items.`. The miss and the how-many reply carry no offer. |
| H13 | The parser decides the ask (`order_status: "top_selling"`), the metric (`rank_by`) and the count (`top_n`). No word table in deterministic code. Owner ruling 26 Sep adds `basis` and `rank_group`, both parser keys with an `unclear` value that sends a clarify line. |
| H15 | Zero-value lines. Owner ruling 26 Sep (answers `[Q9]`): lines with `line_total = 0` are included in both rankings. |
| H14 | Amounts print `RM 1,234.50`; quantities print thousands-separated whole units; no dash characters anywhere in the output. |

## Phase 1 - the reply (presenter over mock JSON)

Owner ruling 26 Sep rewrites this section: the header gains `Basis:` and the full count line,
the title follows the named N (or none), the row cap is 100, a hit ends with the detail offer,
and four new reply shapes join (how-many, metric clarify, group clarify, dealer refused).
Goldens live in `samples/top-selling-*.txt` (+ `.json` for the body-driven ones) and their CI
mirror `sorento_crm_mcp/tests/fixtures/top_selling/`.

- **AC-1901 [FE][T]** Given a body with five rows and no filters, when presented, then the text
  equals golden `top-selling-whole-book.txt` byte for byte: `Top 5 selling items`,
  `Ranked by: Quantity`, `Customer: all`, `Category: all`, `Sales agent: all`, `Channel: all`,
  `Delivery date: 01/01/2026 to 31/12/2026`, a blank line, then rows in the order given.
  Owner ruling 26 Sep: the golden is `top-selling-items-qty.txt`; the title is bold
  (`*Top 5 selling items*`), `Basis: Delivered (transferred to DO)` follows `Ranked by:`,
  `Items with sales: 1,284` follows it, and the reply ends with a blank line and the detail
  offer. Evidence: golden fixture.
- **AC-1902 [FE][T]** Each row prints `n. CODE Name: Qty q, RM v` with `n` the body's own
  `rank`. A row with a null `product_name` prints the code alone before the colon.
  Owner ruling 26 Sep: the row keys are `code` / `name` so one shape serves both grains.
  Evidence: pytest, presenter.
  As built (PR #1263), owner ruling 26 Sep ~07:40Z (supersedes the row-keys reading above):
  "don't need to show name, just show code will do." A row carries `code` only; S1's
  presenter prints `n. CODE: Qty q, RM v` for both grains, never a name.
- **AC-1903 [FE][T]** Any header axis absent from the body prints `all`, never an omitted
  line. `Channel` prints `Dealer`, `Project` or `all`. Evidence: pytest.
- **AC-1904 [FE][T]** `rank_by: "qty"` prints `Ranked by: Quantity`; `"amount"` prints
  `Ranked by: Amount`. The title prints the body's `top_n` (`Top 3 selling items`).
  Owner ruling 26 Sep: `basis: "delivered"` prints `Basis: Delivered (transferred to DO)`,
  `"ordered"` prints `Basis: Ordered`; a null `top_n` prints `*Top selling items*` (no number,
  every row). Evidence: goldens.
- **AC-1905 [FE][T]** A body carrying more than 10 rows prints the first 10 only.
  Owner ruling 26 Sep (superseding the 10 cap): the cap is 100 (the owner's "top 100"); a
  body carrying more than 100 rows prints the first 100. Evidence: pytest.
- **AC-1906 [FE][T]** A body with no rows prints the header, a blank line, `No sales found.`
  and nothing after it; `has_result` is false. Owner ruling 26 Sep: `total` is 0 on a miss;
  no detail offer follows. Evidence: golden fixture `top-selling-miss`.
- **AC-1907 [FE][T]** Rows print in the order given: an unsorted body comes out in input
  order. Evidence: pytest.
- **AC-1908 [FE][T]** Money prints `RM 1,234.50`, zero `RM 0.00`; quantity `1,240`; no dash
  characters anywhere. Evidence: pytest plus the dash guard.
- **AC-1909 [FE][T]** (Owner ruling 26 Sep) One golden each, byte for byte: items by
  quantity, items by amount, categories ranked, items within one category, a customer filter,
  a channel filter, a sales agent filter, the how-many reply, the metric clarify, the group
  clarify, the dealer refused, a miss. Evidence: golden fixtures.
- **AC-1910 [FE][T]** (Owner ruling 26 Sep 01:50Z) No golden and no rendered reply contains
  "more", "next", "lagi" or "Showing". Evidence: pytest over every golden.
- **AC-1911 [FE][T]** (Owner ruling 26 Sep 01:55Z, amended PR #1258 05:32Z) A body with
  `total > 0` and no rows (the message named no N) prints the header, a blank line and `How
  many items do you want to see? Reply with a number from 1 to 100.` (`categories` at
  category grain; the bound is the smaller of the count and 100), no rows, no offer, an
  empty `result_set`; `has_result` is true. Nothing in it speaks of message length. Evidence:
  golden `top-selling-how-many`.
- **AC-1916 [FE][T]** (Owner, PR #1258 05:32Z) Every ranking hit's envelope carries
  `result_set`, one `{idx, label, code, name, entity_type}` row per printed line, `idx` the
  printed rank, label the product code (items) or the printed category name (categories).
  Evidence: pytest `test_envelope_carries_one_pick_row_per_printed_item` and siblings.
- **AC-1912 [FE][T]** (Owner ruling 26 Sep) Every ranking hit ends with a blank line and the
  detail offer: `Reply with a rank number to see that item's customers and months.` at item
  grain, `Reply with a rank number to see that category's top items.` at category grain.
  Evidence: pytest.
- **AC-1913 [FE][T]** (Owner ruling 26 Sep) The fixed lines are one constant each in
  `presenters.py` and equal their goldens: metric clarify `By quantity or by amount?`, group
  clarify `Do you want the top items inside one category, or the categories ranked against
  each other?`, dealer refused `Sorry, I can only share sales figures for your own account.`.
  Evidence: pytest.
- **AC-1914 [FE][T]** (Owner ruling 26 Sep) `group: "category"` prints `*Top N selling
  categories*`, `Categories with sales: n`, and rows `n. NAME: Qty q, RM v` (the code when
  the name is null, `Unassigned` when both are). Evidence: golden `top-selling-categories`.
- **AC-1915 [FE][T]** (Owner ruling 26 Sep) A body carrying `agent_fill_pct` prints `Note:
  only p% of sales orders in this period carry a sales agent.` directly under `Sales agent:`;
  absent, no line. Evidence: golden `top-selling-agent`.
  As built (PR #1263): the route sends `sales_agent_fill_rate` (0 to 1) whenever an agent
  filter is used; the presenter derives the percentage and the threshold.

## Phase 2 - route and service


- **AC-1920 [BE][T]** Given seeded lines over four products, `rank_by=qty` orders by summed
  `qty_ordered` desc, ties by summed `line_total` desc, then `product_code` asc; `rank_by=amount`
  orders by summed `line_total` desc, ties by qty desc, then code asc. Any other `rank_by` is
  422. Evidence: pytest, Postgres.
  As built (PR #1263): `rank_by` is `quantity` | `amount`; the metric follows `basis`.
- **AC-1921 [BE][T]** No `top_n` returns 5 rows (H4); `top_n=25` returns 10 and echoes
  `top_n: 10`; `top_n=0` is 422. Owner ruling 26 Sep (superseding): no `top_n` returns every
  row and echoes `top_n: null` when `total` fits the one-message setting, and no rows with
  the real `total` when it does not; `top_n=250` returns 100 and echoes `top_n: 100`;
  `top_n=0` is 422; a missing `rank_by` is 422. Evidence: pytest.
  As built (PR #1263, relaunch rule): the param is `n`; absent = every row and `total_count`;
  0, negative or above 100 is 422 (no clamp); missing `rank_by` is 422.
- **AC-1922 [BE][T]** `date_from` / `date_to` filter on `COALESCE(required_date, order_date)`,
  accept `_parse_flex_date` formats, 422 otherwise; no dates = every line (the default window is
  the lane's, not the route's). Evidence: pytest.
  As built (PR #1263): no dates = the current calendar year, set in the route and echoed.
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
  As built (PR #1263): owner ruling 26 Sep ~07:40Z drops `name` from a row - `TopSellingRow`
  is `rank, code, quantity, amount`, no `name` field at all.
- **AC-1929 [BE][T]** No credential 401; a user without `order_management.orders.view` 403;
  API key with act-as user 200; `contact_id` without `space_id` 422; a contact without
  `sales_orders.sales_report` 403 `sales_report_not_enabled`; a contact-scoped key sees only its
  companies' lines. Evidence: pytest.
- **AC-1930 [BE][T]** Lines with `line_total = 0` rank by quantity unchanged and contribute
  `RM 0.00` to amount `[Q9]`. Owner ruling 26 Sep: included. Evidence: pytest.
- **AC-1931 [BE][T]** (Owner ruling 26 Sep) `basis` absent = delivered
  (`LEAST(qty_delivered, qty_ordered)` and its amount); `basis=ordered` = `qty_ordered` /
  `line_total`; the echo carries the basis; any other value 422. Evidence: pytest.
  As built (PR #1263): as written; `line_total` null counts 0; a closed, short-delivered
  line counts its whole `qty_ordered` / `line_total`.
- **AC-1932 [BE][T]** (Owner ruling 26 Sep) `group=category` ranks `product_categories` by
  the summed metric; products with no category rank as one null-category row. Evidence:
  pytest.
- **AC-1933 [BE][T]** (Owner ruling 26 Sep 01:55Z) With no `top_n`, `total` above the setting
  returns `rows: []` and the true `total`; at or below it returns every row. Evidence: pytest.
  As built (PR #1263): superseded by the relaunch rule; no setting, the route never
  withholds rows. The lane decides the how-many reply off `total_count`.
- **AC-1934 [BE][T]** (Owner ruling 26 Sep) A dealer contact's request is scoped to its own
  ledgers whatever `customer_ids` says, and a customer outside them is 403 `other_customer`;
  a staff contact sees any customer. Evidence: pytest.
  As built (PR #1263): the code is `customer_not_permitted`; an unlinked contact that is not
  office staff is refused the same way (fail closed); a dealer `customer_query` matching only
  other customers or nobody is one answer.
- **AC-1935 [BE][T]** (Owner ruling 26 Sep, detail offer) `detail_code` returns that code's
  `by_customer` and `by_month` under the same filters, sorted by the metric desc; the detail
  presenter renders it (golden lands with S2). Evidence: pytest plus golden.
  As built (PR #1263): on the route; `rows` / `totals` narrow to the code and `detail`
  carries both lists; the detail presenter and golden are S1's.

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
  lane never reads the message text. Owner ruling 26 Sep: absent `rank_by` sends the metric
  clarify and no fetch at all (the route no longer defaults it). Evidence: pytest.
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
  offer follows unchanged; a hit arms no pending and offers nothing. Owner ruling 26 Sep
  (superseding "offers nothing"): a hit arms the detail offer (AC-1964); the how-many reply
  arms nothing. Owner, PR #1258 05:32Z: the offer is armed as a sticky `top_selling_pick`
  roster (AC-1966). Evidence: pytest.
- **AC-1958 [BE][T]** The generic search-scope header is skipped for
  `crm_top_selling_report`. Evidence: pytest.
- **AC-1959 [BE][T]** `rank_by` is in the strict schema's `properties` and `required` and in
  `TOLERATED_ABSENT`; the prompt fallback and its migration teach `order_status:
  "top_selling"` and `rank_by`; `test_parser_prompt_is_live.py` passes. Evidence: pytest.
- **AC-1960 [BE][T]** "last 3 DO for hanlim" (a plain `top_n` on an order list) still reaches
  `crm_order_management_orders_list` with `limit=3`; nothing about the growth r1 `top_n` path
  changes. Evidence: pytest, existing tests stay green.

## Phase 2 - clarify, detail and dealer seams (owner ruling 26 Sep)

- **AC-1961 [BE][T]** A `top_selling` emission with a null `rank_by` sends `By quantity or by
  amount?`, fetches nothing, and a follow-up "amount" runs the carried ask (N, filters,
  dates) by amount. Evidence: pytest, fetch spy.
- **AC-1962 [BE][T]** `rank_group: "unclear"` sends the group clarify and fetches nothing; a
  follow-up naming a category runs the item ranking filtered to it, "categories" runs the
  category ranking. Evidence: pytest.
- **AC-1963 [BE][T]** A dealer contact naming a customer outside its own ledgers gets `Sorry,
  I can only share sales figures for your own account.`, no fetch, no picker. Evidence:
  pytest.
- **AC-1964 [BE][T]** After an item ranking, a bare rank number calls the tool with that
  row's `detail_code`; after a category ranking, it runs the item ranking filtered to that
  category. A number past the last row is a polite miss, not an error. Evidence: pytest.
- **AC-1965 [BE][T]** After the how-many reply, "20" or "top 20" runs the carried ask with
  `top_n=20`. Evidence: pytest.
- **AC-1966 [BE][T]** (Owner, PR #1258 05:32Z) The ranked list behaves like the customer and
  product pickers: `top_selling_pick` is in `ROSTER_KINDS`; a bare "2" (`reference_positions`)
  or a typed code / category name (exact label match) picks that row; the list stays open
  for a later pick against the same list; it has no turn clock; it closes when every row
  was picked or a new ask about something else was answered. Evidence: pytest
  `tests/chatbot/test_top_selling_sticky_pick.py`.

As built (S4), evidence per criterion, all in `tests/chatbot/test_top_selling_lane.py`
unless named: AC-1950 `TestToolPick`; AC-1951 `TestNoGrant`; AC-1952
`test_rank_by_and_top_n_from_parser_only` (the parser's `rank_by` is sent, `top_n` is
`n`, absent `top_n` is `count_only`); AC-1953 `test_param_mapping_and_date_default` (no
date sends none, the route's year is echoed); AC-1954 `TestCategory` (the lane resolves
the word, the generic resolver is never asked); AC-1955 `TestCustomerPicker`; AC-1956
`TestFollowUp`; AC-1957 `test_miss_takes_not_found_path` (the ranking's own header and
`No sales found.` above the offer); AC-1958 `test_header_skipped`; AC-1959 `TestParser`;
AC-1960 the existing order list tests, unchanged and green; AC-1961 to AC-1965
`TestClarify`, `TestDealer`, `TestPickList`, `TestHowMany`; AC-1966 `TestPickList` plus
`test_top_selling_sticky_pick.py`. AC-1963's "no fetch" is as built "no figures": the
route is the check and answers 403, which the presenter prints as the refusal line.

## Phase 2 - sales agent slot (S5; the gate on #1168 / #1170 is lifted, owner ruling 26 Sep)

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

- Breakdown mode (top N per agent): the owner asks "per agent" on the live console. Owner
  ruling 26 Sep: per category is answered by the category grain; per month is plan S7.
- Warehouse filter: the owner asks "top 5 at BRW".
- Family collapsing (rank base codes): the top 5 comes back as five variants of one product.
- `sales_agent` on `group_by` and on the sales report: the sales module (#1170) needs it.
