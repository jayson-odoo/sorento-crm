# PLAN - Chatbot: top X hot selling items by category / customer / sales agent / date range

Status: grilled (26 Sep 2026; owner rulings on PR #1175 folded in below, S1 in build on
`feat/chatbot-top-selling-s1`). Track: full track (new route + MCP tool = a new external
ingest surface, one policy-row migration, one prompt migration, one entity-kind migration;
the diff will pass 300 lines).
Issue: #1171. UAC: `chatbot-top-x-hot-selling-24sep-acceptance-criteria.md` (AC-19xx).
Classification: CORE, `public` schema, no new table, no new column. The chatbot module is
where the wiring lands; the report itself is an order-management read.
Precedent: `PLAN-chatbot-sales-report.md` (#1034, BUILT). Every seam below copies that lane's
seam WITH the justification that earned it, or says why it does not.

## Owner rulings (26 Sep 2026)

Source: the owner's PR #1175 comment starting "@claude Default N" (verbatim, binding), plus
two follow-ups relayed by the orchestrator the same morning. Each line below is dated so a
later reader can tell a ruling from a proposal.

- Owner ruling 26 Sep: **N.** A number in the message ranks that many, 1 to 100 (the owner's
  own example is "top 100"). No number = no cut-off: every ranked row. No invented default N.
- Owner ruling 26 Sep 01:50Z (amends the first reading of the N ruling): **no paging.** No
  "more", no "next", no "lagi" anywhere in the reply; the owner called paging "very not
  transparent". The header states the full count.
- Owner ruling 26 Sep 01:55Z: **long lists.** When the message names no number and the ranked
  list would not fit one WhatsApp message (about 50 rows, one setting), the bot sends no
  partial list: it states how many there are and asks how many to show. A list that fits is
  sent in full. The same rule applies to PR #833's counted set answers (that lane's work, not
  this one's).
- Owner, PR #1258 26 Sep 05:32Z (amends the 01:55Z reading above): **length is not the
  bot's problem.** n8n already chunks a long WhatsApp message, so there is no "fits one
  message" threshold, no `chatbot_top_selling_one_message_rows` setting and no bot-side
  split of a long reply. With no N named, the header states the full count and the bot asks
  how many (1 to the smaller of the count and 100), whatever the count; a named N up to 100
  goes out whole and n8n chunks it. One row is sent as is (nothing to choose between).
- Owner, PR #1258 26 Sep 05:32Z: **the ranked list is a sticky pick list**, the same as the
  customer and product pickers: the printed rows arm a `top_selling_pick` roster
  (`turn/pending.py::ROSTER_KINDS`), so a later "2", a typed code or a typed category name
  resolves against the last list shown through `turn/decide.py::picked_positions`, and the
  list stays open across picks. No turn clock (the pickers have none: `pending.tick` only
  expires the escalation offers); it closes on the pickers' own two rules in
  `turn/apply.py` (every row picked, `stale_roster_closed`; a new ask about something else,
  `new_ask_closes_stale_roster`).
- Owner ruling 26 Sep: **metric is required.** `rank_by` is quantity or amount; when the
  message does not say, the bot asks "By quantity or by amount?". No default metric.
- Owner ruling 26 Sep: **basis.** Both ordered (`qty_ordered`, ordered amount) and delivered
  (transferred to DO, `LEAST(qty_delivered, qty_ordered)` and its amount) are supported.
  "Selling" normally means delivered: when the message does not say, the reply uses delivered
  and says so in the header, and "ordered" as a follow-up re-runs on the ordered basis. A
  message ambiguous between the two ("top orders") gets a clarify question instead.
- Owner ruling 26 Sep: **group.** The bot ranks items (default grain for an item / product
  ask) OR ranks categories ("which category sells most"). A category word can also be a
  filter ("top items in category A"). When the message is ambiguous between filtering by a
  category and ranking categories, the bot clarifies; it never assumes.
- Owner ruling 26 Sep: **date.** No date said = the current calendar year. Months and ranges
  are supported. "By month" is either a month filter or a per-month breakdown; when unclear,
  clarify.
- Owner ruling 26 Sep: **filters.** Customer, channel (the existing dealer / retail / project
  word), category, sales agent. Sales agent = `sales_orders.sales_agent_id` (who sold the SO).
  The S5 gate on #1168 / #1170 is lifted by this ruling; the reply carries a fill-rate note
  when the agent field is thinly filled.
- Owner ruling 26 Sep: **access.** The `sales_orders.sales_report` reveal key, no new key.
  Staff may ask across all customers. A dealer is forced to its own ledgers and can never ask
  about another dealer: a named other customer gets a polite refusal, not data.
- Owner ruling 26 Sep: **zero-value lines** (`line_total = 0`) are included.
- Owner ruling 26 Sep: **detail offer required.** After the ranking the reply offers a detail
  follow-up. Chosen smallest useful detail (captain, 26 Sep): for an item ranking, "Reply with
  a rank number to see that item's customers and months."; for a category ranking, "Reply with
  a rank number to see that category's top items." (which is the item ranking filtered to that
  category, so it needs no new answer shape).

## Journey

Actor: a management or sales contact on WhatsApp who already holds the sales report grant,
or a dealer contact holding it (forced to its own ledgers). They want to know what is
moving. The system already knows the contact, its tier, its companies, every customer ledger,
the product master with its category, the salesperson master and every SO line AutoCount has
pushed (quantity ordered, quantity transferred to DO, line total, required date, the SO's
agent code).

1. They type "top 5 selling items by quantity last month". One reply: a header naming the
   ranking, the metric, the basis (delivered), the count of items with sales and every filter
   axis, then five numbered rows, code and name, quantity and amount, then the detail offer.
2. They type "top 5 selling items last month" (no metric). The bot asks "By quantity or by
   amount?"; "amount" answers it and the ranking follows.
3. They type "top 10 for hanlim by amount this quarter". Same list, filtered to the HANLIM
   ledgers, the header says so. An ambiguous customer name goes through the existing customer
   picker; "1" or "all" continues this ask.
4. They type "top 3 kitchen sinks by quantity in 2026". Same list, filtered to the KITCHEN
   SINK category. "which category sells most by amount" ranks categories instead. "top
   selling by category" is ambiguous and gets the group clarify question.
5. They type "top 5 by quantity for sales agent SEAN I this year". Same list, filtered to the
   SOs that agent sold.
6. They type "top selling items by quantity" with no number. They get "How many items do you
   want to see? Reply with a number from 1 to 100." under a header that states the count.
   "20" or "top 20" answers it (amended by the owner, PR #1258 05:32Z).
7. They reply "2" after a ranking. That item's customers and months follow (the detail).
   The list stays open: "4" or "SRTBS1020" next answers against the same list, as a second
   pick over a customer or product picker does (owner, PR #1258 05:32Z).
8. They type "ordered" after a ranking. The same ranking re-runs on the ordered basis.
9. A dealer types "top 5 for <another dealer>". It gets "Sorry, I can only share sales
   figures for your own account." and nothing is fetched for that customer.
10. A contact without the grant gets `Sales report is not enabled for your account.` and
    nothing is fetched.

Decisions asked of the user: the customer picker (existing), the metric clarify, the group
clarify, the basis clarify (only when ambiguous), the month clarify (only when ambiguous) and
the how-many question when no N is named. Every other axis is derived.

## What exists today (measured against the code, 24 Sep 2026)

### Parser slots (`app/services/chatbot/head/parser.py::_build_json_schema`)

The strict schema has 35 top-level keys. The ones this ask needs:

| slot | exists | notes |
|---|---|---|
| `date_mode`, `date_filter_start`, `date_filter_end` | yes | carried to every tool through `DATE_PARAMS` |
| `entities[].hint = customer` | yes | resolver source `customers`, ledger-family grouping, `must_narrow_one` under `order` |
| `entities[].hint = category` | yes, but not usable under `order` | kind row exists (`policy_rows.DEFAULT_KIND_ROWS`, source `product_categories`), BUT `gate.ALLOWED["order"]` has no `category`, `gate.NO_TOOL_ID` = {brand, category} (maps to no `*_ids` param), `fetch.TYPE_TO_PARAM` has no `category`, and `entity_resolver._DOMAIN_HINT_EXPANSIONS["order"]["category"]` re-types a category token as customer / customer_order / transporter. So "top 5 kitchen sinks" under `order` today resolves KITCHEN SINK as a customer or drops it. |
| `entities[].hint = product` | yes | `list_all` under `order` |
| `demand_qty` | yes | unrelated (a quantity the customer wants to buy) |
| `top_n` | **yes** (growth r1, AC-910) | integer, current message only, "top 5" -> 5. Reaches `semantic_input` and `entity_ids_transformer`, where it aliases to `limit` for `ORDER_TOOLS` / `GROUP_BY_TOOLS` and is sent as `top_n` for `TOP_N_DIRECT_TOOLS`. Not carried into `Focus`. |
| `group_by` | yes | enum customer / transporter / date / product / warehouse / supplier. A breakdown axis, not a filter. No `category`, no `sales_agent`. |
| `order_status` | yes | the ask discriminator the two reports use: `outstanding` family and `sales_report` |
| `sales_channel` | yes | dealer / project, carried on `Focus.sales_channel` |
| ranking metric (`rank_by`) | **no** | nothing says qty vs amount anywhere in the schema, the prompt or the lane |
| sales agent slot | **no** | not in `contracts.ENTITY_HINTS`, no kind row, no resolver source in `entity_resolver.py`, not in `gate.ALLOWED`, not in `TYPE_TO_PARAM` |

Conclusion: `top_n` is already a slot and needs no new key. Two slots are new: `rank_by` and
the `sales_agent` entity kind. One existing slot needs unblocking under `order`: `category`.

### How a business_query "data page" is registered and answered

There is no registry and no page object. A report ask is one value plus five seams, all of
them already exercised by `crm_outstanding_report` and `crm_sales_report`:

1. **Parser**: an `order_status` value (`sales_report`) taught by a trailing prompt addendum
   (`chatbot_parser_prompt.SALES_REPORT_ADDENDUM`), published as a new unlabelled
   `chatbot_semantic_parser` version by one migration (`519_chatbot_sales_report_vocab`); the
   owner moves the `production` label. `turn/apply.py` projects it onto `Focus.status` so a
   refinement turn keeps the ask.
2. **Policy row**: the tool name is appended to the `order` domain's `tools` in
   `turn/policy_rows.DEFAULT_DOMAIN_ROWS` (frozen seed; a live DB is changed by a
   `chatbot_rearch_sNN` migration). That makes it a member of `fetch.CHATBOT_READ_ONLY_TOOLS`
   (the egress allow-list) and of `policy_rows.DATE_PARAM_TOOLS`. It is never `tools[0]`.
3. **Tool pick**: an override branch in `lanes/business/__init__.py::run_fetch` (line 1283 for
   the sales report): `domain == "order" and <subject rule> and order_status_raw == "<value>"`
   sets `tool_name`; the reveal-key gate runs right there, before any fetch. The engine has a
   grant-before-roster check too (`engine.py:1706`, SF-1) so an ungranted ask never renders the
   customer picker. `lanes/business/__init__.py:590` is the same check at `run_until_exit`.
4. **Arguments**: a `tool_name == "<tool>"` block in `fetch.entity_ids_transformer` builds the
   tool's own contract off `semantic_input` and the resolved entities; `fetch.DATE_PARAMS` names
   the two date params.
5. **Answer**: `sorento_crm_mcp/catalog.py` `ToolSpec` (path, params, `restricted_fields`),
   `presenters.py` renders the WhatsApp text and returns `{result_type, response, has_result}`;
   `fetch.output_structurer` dispatches on `ctx["tool"]` (line 2098) to arm an offer or take the
   miss path. A miss goes through `not_found_error_message`, so the escalate offer follows.

`documentation/plans/chatbot/PLAN-chatbot-turn-engine.md` carries no "data page" section by
that name; the policy it does carry is the one above: the domain row decides the tool, the
lane decides the arguments, the presenter decides the words, and the parser is the only
reader of the customer's text (D11).

### SQL source of truth for sales by item

`sales_orders` (header) + `sales_order_lines` (money and quantity), the source
`PLAN-chatbot-sales-report.md` measured and ruled on (S1: the DO tables `orders` /
`order_lines` are NOT usable as money; `order_analytics` and `orders_by_product` read those
and are therefore not the source here).

| need | column | table |
|---|---|---|
| item | `product_id` -> `products.product_code`, `products.product_name` | `sales_order_lines`, `products` |
| category | `products.category_id` -> `product_categories.category_code` / `category_name` | `products`, `product_categories` |
| customer | `sales_orders.customer_id` (ledger; family via the resolver) | `sales_orders` |
| sales agent | `sales_orders.sales_agent_id` -> `sales_agents.sales_agent` (code, e.g. `SEAN I`), `person_label` | `sales_orders`, `sales_agents` |
| date | `COALESCE(sales_order_lines.required_date, sales_orders.order_date)` (the sales report's bucket, S3) | both |
| channel | `sales_orders.demand_class` (`retail` = dealer, `project`) | `sales_orders` |
| quantity | `qty_ordered` (ordered) or `LEAST(qty_delivered, qty_ordered)` (confirmed, transferred to DO) | `sales_order_lines` |
| amount | `line_total` (the file's `Total (Inc)`; 22,717 lines dated 2026 carry 0, UAC sales report "Measured") | `sales_order_lines` |
| exclusions | `sales_orders.status <> 'cancelled'`, `line_status <> 'cancelled'`, bucket not null | both |

Existing ranking code: `sales_report_service._rank_breakdown` ranks a month's `by_product`
by ordered value desc, ordered qty desc, code asc, over exactly this predicate. That is a
per-month ranking with a mandatory subject; this feature is a whole-window ranking with no
mandatory subject. `_per_line_exprs`, `_common_filters` and `_bucket_expr` in that module are
the reusable parts; nothing else in the codebase ranks items on the SO source.

Not measurable from this checkout (no database here); measure before the grill and paste
into the UAC "Measured": fill rate of `sales_orders.sales_agent_id` on SOs dated 2026, count
of distinct `product_categories` reached by 2026 lines, `products.category_id` null rate on
sold products, and the row count of a whole-book `GROUP BY product_id` over 2026 (to size the
date default).

## Design: the smallest thing that works

**One new report, one new `order_status` value, three new nullable parser keys (`rank_by`,
`basis`, `rank_group`), one unblocked entity kind (`category` under `order`), one new entity
kind (`sales_agent`), one setting. No registry, no new engine, no new reveal key.** The
detail offer reuses the sales report's offer seam (S4 measures whether it carries a rank
number; if it cannot, ONE new pending kind `top_selling_detail` is the smallest shape).

Why a second route rather than a mode on `crm_sales_report`: the sales report requires a
subject (422 `subject_required`, a scan guard), prints month blocks and defaults product-only
asks to the current year (S18). A ranking has no subject and prints one list. Folding it in
means a mode switch in a shipped, 60-AC report; a sibling route that reuses the same service
helpers is fewer moving parts.

### The reply (contract for Phase 1, rewritten for the 26 Sep rulings)

Every reply is one of six shapes. The first three are rendered from the route's body by
`_top_selling_envelope`; the last three are fixed lines the lane sends before any fetch,
declared once in `presenters.py` so the goldens and the lane read the same literal.

1. **Ranking (hit).**

```
*Top 5 selling items*
Ranked by: Quantity
Basis: Delivered (transferred to DO)
Items with sales: 1,284
Customer: all
Category: all
Sales agent: all
Channel: all
Delivery date: 01/01/2026 to 31/12/2026

1. SRTWT7445 Kitchen Sink 2 Bowl: Qty 1,240, RM 86,400.00
2. SRTKT39SS Kitchen Tap: Qty 980, RM 31,200.00
3. ...

Reply with a rank number to see that item's customers and months.
```

   - Title: `*Top N selling items*` when the message named N, `*Top selling items*` when it
     did not (every row follows). Category grain: `*Top N selling categories*`, count line
     `Categories with sales: n`, offer `Reply with a rank number to see that category's top
     items.`
   - `Ranked by:` prints `Quantity` or `Amount`. `Basis:` prints `Delivered (transferred to
     DO)` or `Ordered`. The count line is the FULL count of ranked rows in the window (owner:
     the header states the full count), whatever N is.
   - Every absent filter axis prints `all`, never an omitted line. `Channel:` prints
     `Dealer`, `Project` or `all` (`_sales_channel_header`).
   - Under a sales agent filter, when the route sends `agent_fill_pct`, one extra line follows
     `Sales agent:`: `Note: only 87% of sales orders in this period carry a sales agent.`
     The route decides when to send it (S2: below 95%).
   - Rows: `n. CODE Name: Qty q, RM v` for items (code alone when the name is null);
     `n. NAME: Qty q, RM v` for categories (the category code when the name is null,
     `Unassigned` for products with no category). `n` is the body's own `rank`, rows print in
     the order given (the route sorts), at most 100 rows (the N ceiling).
   - No "more", "next" or "lagi" anywhere (owner ruling 01:50Z).
2. **How many (no N named).** The same header, a blank line, then `How many items do you want
   to see? Reply with a number from 1 to 100.` (`categories` at category grain; the upper
   bound is the smaller of the count and 100). No rows, no offer, no pick list.
   `has_result: true` (it is not a miss; nothing escalates).
3. **Miss.** The same header, a blank line, `No sales found.`, nothing after it.
   `has_result: false`, so the lane's not-found path offers the escalation.
4. **Metric clarify.** `By quantity or by amount?`
5. **Group clarify.** `Do you want the top items inside one category, or the categories
   ranked against each other?`
6. **Dealer asking about another customer.** `Sorry, I can only share sales figures for your
   own account.`

Also fixed lines, used only when the message is genuinely ambiguous: basis clarify
`Delivered (transferred to DO) or ordered?`; month clarify `One month only, or a month by
month breakdown?`. Denied (no grant): `Sales report is not enabled for your account.`, the
sales report's own line. Dates print through `_outstanding_date_range`, money through
`_rm_money`, quantities through `_outstanding_fmt_int`. No dash characters.

### Backend contract (S2)

`GET /api/v1/order-management/top-selling` on the sales report's own no-prefix router
(`orders.py::sales_report_router`, mounted beside `/sales-report`), same auth dependency
(`order_management.orders.view` with API key), same `contact_id` / `space_id` both-or-neither
rule and the same per-contact `sales_orders.sales_report` re-check (S14 of the sales report).

| param | type | rule |
|---|---|---|
| `rank_by` | `qty` / `amount` | **required** (owner: no default metric); absent or other is 422 |
| `top_n` | int | optional; absent = every row (subject to the one-message rule); 1..100, above 100 clamps to 100, below 1 is 422 |
| `basis` | `delivered` / `ordered` | default `delivered` (owner: "selling" means delivered); else 422 |
| `group` | `item` / `category` | default `item`; else 422 |
| `customer_ids` | csv uuid | the lane's resolved ledgers |
| `customer_query` | str | `ILIKE %q%`, min 3 chars (same guard as the sales report) |
| `category_ids` | csv uuid | resolved category rows |
| `sales_agent_ids` | csv uuid | resolved `sales_agents` rows |
| `channel` | `dealer` / `project` | absent = all, else 422 |
| `date_from`, `date_to` | flex date | on the bucket date, `_parse_flex_date` |
| `detail_code` | str | one product code (item grain) or category code (category grain): returns the detail body instead of the ranking |

Dealer scoping is enforced in the ROUTE, not only the lane: when the contact's tier is
dealer, the route replaces `customer_ids` with the contact's own ledgers and answers 403
`other_customer` when the request names a customer outside them (the lane checks first and
prints fixed line 6, so the 403 is a backstop, never the customer's words).

Response (`TopSellingResponse`, every field declared, asserted through the route):

```
{
  "group": "item" | "category", "rank_by": "qty" | "amount",
  "basis": "delivered" | "ordered", "top_n": int | null, "total": int,
  "customer_name": str | null, "category_name": str | null,
  "sales_agent": str | null, "agent_fill_pct": int | null,
  "channel": "dealer" | "project" | null,
  "date_from": date | null, "date_to": date | null,
  "rows": [ { "rank": 1, "code": str, "name": str | null, "qty": number, "amount": number } ]
}
```

`rows` is empty with `total > 0` exactly when `top_n` is absent and `total > 1` (owner, PR
#1258 05:32Z: no size threshold, no setting; n8n chunks long messages). The presenter renders
shape 2 off that pair. The envelope also carries `result_set`, one `{idx, label, code, name,
entity_type}` row per printed line (`idx` = rank; label = the product code at item grain, the
printed category name at category grain), empty on the how-many reply and the miss.

Detail body (`detail_code` set): `{..the same header fields.., "detail": {"code", "name",
"by_customer": [{customer_name, qty, amount}], "by_month": [{month, qty, amount}]}}`, both
lists sorted by the same metric desc; the detail presenter and its golden land with S2.

Service: `top_selling(db, filters) -> dict` in `app/services/sales_report_service.py`, ONE
grouped query over `sales_order_lines` join `sales_orders` join `products`, optional join
`product_categories`, `GROUP BY` product (or category), `ORDER BY <metric> DESC, <other
metric> DESC, code ASC`, `COUNT(*) OVER ()` for `total`, `LIMIT top_n` (or the setting + 1
when absent). Reuses `_common_filters` (extended with `category_ids` and `sales_agent_ids`),
`_bucket_expr`, `_per_line_exprs` (ordered pair = `ordered_qty` / `ordered_value`, delivered
pair = `confirmed_qty` / `confirmed_value`), `_customer_echo`, `_qty`, `_money_edge`.
Aggregated in SQL (S17 of the sales report). Decimal throughout, quantised at the edge.
Company scope through the ORM classes, never raw text SQL. Zero-value lines included (owner
ruling).

### Parser (S4)

- `order_status` gains `top_selling`: "top 5 selling", "best selling", "hot selling", "top
  items", "most sold", "which category sells most", "paling laku", "畅销". The addendum says in
  words that "top 5" with no sales word under an order / stock question stays what it was
  (`top_n` on an order list).
- New nullable key `rank_by`: `"qty" | "amount" | null`, from the current message only. Null
  is not defaulted: the lane asks the metric clarify.
- New nullable key `basis`: `"delivered" | "ordered" | "unclear" | null`. Null = delivered;
  `unclear` (e.g. "top orders") = the lane asks the basis clarify. "ordered" on its own as a
  follow-up under a carried `top_selling` ask sets it.
- New nullable key `rank_group`: `"item" | "category" | "unclear" | null`. Null = item;
  `category` for "which category sells most"; `unclear` when a category word could be either
  a filter or the grain ("top selling by category") = the lane asks the group clarify. A
  named category ("top kitchen sinks") is a filter entity, never `rank_group`.
- `top_n`: unchanged, already taught. Absent = no cut-off (owner ruling), never defaulted.
- Month: "by month" alone is `unclear` for the month clarify through the existing
  `date_mode`; the per-month breakdown answer is S7 below.
- All three new keys are declared in the strict schema, in `required`, and in
  `TOLERATED_ABSENT` (the same reason `sales_channel` is).
- `category` under `order`: the addendum names category words on a top-selling ask as
  entities with hint `category`, `hint_confident: true`.
- `sales_agent`: a new entity hint, "by sales agent X", "agent X", "salesman X",
  "jurujual X".

No word table anywhere in Python (S12 of the sales report holds).

### Lane wiring (S4), smallest shape per seam

1. `contracts.ENTITY_HINTS`: `sales_agent` added (S5; no longer gated, owner ruling 26 Sep).
2. `turn/policy_rows.DEFAULT_DOMAIN_ROWS["order"].tools` += `crm_top_selling_report`, plus
   `DATE_PARAM_TOOLS`; a `chatbot_rearch_s13`-style migration applies the same to a seeded DB.
3. `gate.ALLOWED["order"]` += `category` and `sales_agent` (S5). `NO_TOOL_ID` stays as is
   (the category id is read off the entities inside this tool's own arg block, the way
   `crm_low_stock_report` reads its product codes, so `TYPE_TO_PARAM` and every other domain
   are untouched).
4. `entity_resolver._DOMAIN_HINT_EXPANSIONS["order"]["category"]` re-types a category token
   as a customer. The reconciliation step asks for the hinted kind first when
   `hint_confident` is true (`head/parser.py` schema comment, AC-1506); a test pins that a
   confident `category` hint on a `top_selling` ask resolves against `product_categories`. If
   it does not, the narrowest fix is an `order_status`-aware exception in that one dict, not a
   resolver change.
5. `run_fetch`: one `elif` beside the sales report override: `domain == "order" and
   order_status_raw == "top_selling"` picks `crm_top_selling_report`, gate on
   `_SALES_REPORT_GRANT` first (same constant, no new key). The two engine-level checks
   (`engine.py:1706`, `__init__.py:590`) test `order_status in {"sales_report", "top_selling"}`
   through one shared tuple `SALES_FIGURE_STATUSES` declared in `contracts.py`.
6. `fetch.DATE_PARAMS["crm_top_selling_report"] = ("date_from", "date_to")`.
7. `entity_ids_transformer`: a `tool_name == "crm_top_selling_report"` block: pop
   `product_ids` / `warehouse_ids`; `customer_ids` from the generic map (carried ids win, same
   as the sales report); `category_ids` off entities typed `category`; `sales_agent_ids` off
   entities typed `sales_agent` (S5); `rank_by`, `basis`, `rank_group` (as `group`) and
   `top_n` from `semantic_input` (absent `top_n` sends no param: no cut-off, owner ruling 26
   Sep); `channel` from `sales_channel`; the current-calendar-year date default built HERE,
   never in the route, turned off by `broaden_axis == "date"` exactly as S18. Owner ruling 26
   Sep: a dealer contact's `customer_ids` are its own ledgers, whatever it named.
8. `_fetch_semantic_input` gains `rank_by`, `basis`, `rank_group`.
   `turn/apply._IDLE_CHAT_DISQUALIFIERS` gains the same three. Owner ruling 26 Sep changes
   the carry rule: because the metric and group clarify questions and the how-many question
   are answered in a SECOND message, `top_n`, `rank_by`, `basis` and `rank_group` are carried
   on `Focus` while `focus.status == "top_selling"` (a new value in the follow-up wins; a new
   subject is a new ask and clears them). "by amount", "ordered", "20" and "amount" are all
   refinements of the carried ask, which is what the customer means.
8a. Clarify seams (owner ruling 26 Sep, no defaults): before any fetch, in this order,
   `rank_group == "unclear"` sends the group clarify, a null `rank_by` sends the metric
   clarify, `basis == "unclear"` sends the basis clarify, an unclear month sends the month
   clarify. Each is one fixed line from `presenters.py`, arms nothing new (the carried
   `focus.status` is what makes the answer land), and fetches nothing. A dealer naming a
   customer outside its own ledgers gets the refusal line, also before any fetch.
9. `output_structurer`: `crm_top_selling_report` takes the miss path on `has_result: false`
   and, on a ranking hit, arms the envelope's `result_set` as a sticky `top_selling_pick`
   roster via `turn/pending.top_selling_pick` (owner, PR #1258 05:32Z: behaves like the
   customer and product pickers; owner ruling 26 Sep: detail offer required), so a rank
   number or a typed code / category name re-calls the tool with `detail_code` = that row's
   code (category grain: re-calls the item ranking with that category as the filter), and
   the list stays open for the next pick. The how-many reply arms nothing. `_search_scope_header` skipped for it, same as the two reports.
10. `resolve_gate` picker hint off for `top_selling` (R20 rule), same population reason.
11. `mcp_tool_domains.py`: `crm_top_selling_report` under `orders`. NO in-app assistant
    bootstrap (security B1 of the sales report: the same money, same reason).


## Filters combination matrix (rewritten for the 26 Sep rulings)

Every filter is optional and every combination is one query with the filters ANDed. The
header prints the axis when given and `all` when not. Three axes are NOT filters and are
settled before the matrix applies: the metric (asked when absent), the group (items unless
the message ranks categories; asked when unclear) and the basis (delivered unless the message
says ordered; asked when unclear).

| customer | category | sales agent | date | channel | what runs |
|---|---|---|---|---|---|
| no | no | no | no | no | whole book over the current calendar year; header says the window |
| yes | no | no | any | any | that ledger family only |
| no | yes | no | any | any | products in that category only (a filter, owner ruling 26 Sep) |
| no | no | yes | any | any | SOs that agent sold (`sales_orders.sales_agent_id`, owner ruling 26 Sep) |
| yes | yes | no | any | any | AND |
| yes | no | yes | any | any | AND; a customer whose SOs carry another agent code returns fewer rows, never a picker |
| no | yes | yes | any | any | AND |
| yes | yes | yes | any | any | AND |
| any | any | any | "all dates" said | any | date default off, `Delivery date: all` |
| any | any | any | a month / a range | any | that window |
| any | any | any | any | dealer / project | `demand_class` filter, header `Channel: Dealer / Project` |
| dealer contact | any | any | any | any | customer forced to the contact's own ledgers (owner ruling 26 Sep); another customer named = refusal line, no fetch |

Owner ruling 26 Sep, N across the matrix: a named N (1 to 100) cuts every row of the matrix;
no N returns the how-many question with the full count (owner, PR #1258 05:32Z: no size
threshold; n8n chunks long messages), except a single row, which is sent. Category grain (ranking categories) accepts every
filter above except a category filter, which it ignores with the header printing `all`.

An ambiguous customer name takes the existing picker on every row that names one; a category
token that resolves to several categories takes `optional_filter` (the kind row's default):
all matched categories as an `IN`, never a picker.

## Slices (rewritten for the 26 Sep rulings)

| slice | phase | what | files |
|---|---|---|---|
| S1 | 1 | Presenter over mock JSON: `_top_selling` / `_top_selling_envelope` and the fixed clarify / refusal lines. Goldens: items by quantity, items by amount, categories ranked, items within one category, customer filter, channel filter, sales agent filter (with the fill-rate note), the how-many reply for a long list with no N, the metric clarify, the group clarify, the dealer refused, a miss; the detail offer line on every ranking hit; dash guard | `sorento_crm_mcp/sorento_crm_mcp/presenters.py`, `documentation/plans/chatbot/samples/top-selling-*.txt` + `.json`, `sorento_crm_mcp/tests/fixtures/top_selling/` (the CI mirror), `sorento_crm_mcp/tests/test_presenters_top_selling.py` |
| S2 | 2 | Route + service + response model, `basis` / `group` / `detail_code`, dealer scoping, the one-message setting, the detail presenter + its golden | `app/api/v1/order_management/orders.py`, `app/services/sales_report_service.py`, `app/schemas/order_management.py`, `app/config.py`, `presenters.py`, `tests/test_top_selling_report.py` |
| S3 | 2 | MCP ToolSpec + domain map | `sorento_crm_mcp/sorento_crm_mcp/catalog.py`, `app/services/mcp_tool_domains.py`, `sorento_crm_mcp/tests/test_catalog_top_selling.py` |
| S4 | 2 | Parser addendum + prompt migration, `rank_by` / `basis` / `rank_group` keys, policy-row migration, gate row, tool override, arg block, focus carry, clarify seams, detail offer, dealer refusal | `chatbot_parser_prompt.py`, `alembic/versions/<n>_chatbot_top_selling_vocab.py`, `alembic/versions/chatbot_rearch_s13.py`, `contracts.py`, `head/parser.py`, `turn/policy_rows.py`, `turn/apply.py`, `turn/state.py`, `lanes/business/gate.py`, `lanes/business/__init__.py`, `lanes/business/fetch.py`, `lanes/business/resolve_gate.py`, `engine.py`, `tests/chatbot/test_top_selling_lane.py`, `tests/chatbot/console_cases/2026-09-24-top-selling.yaml` |
| S5 | 2 | Sales agent slot: entity hint + kind row migration + resolver source + gate row + arg param + route param + prompt words + fill-rate note. **No longer gated** (owner ruling 26 Sep: agent = `sales_orders.sales_agent_id`) | `contracts.py`, `turn/policy_rows.py` + migration, `entity_resolver.py`, `gate.py`, `fetch.py`, `orders.py`, `sales_report_service.py`, `chatbot_parser_prompt.py` (+ migration), `tests/chatbot/test_top_selling_sales_agent.py` |
| S6 | 3 | reviewer + security-reviewer (new route, reveal gating, dealer scoping, company scope) + console check, in parallel | `documentation/plans/chatbot/evidence/top-selling/` |
| S7 | 2 | Per-month breakdown ("top 5 by month" read as a breakdown): one ranking block per month in the window, the answer to the month clarify's second option. Shape to be confirmed by the owner on the S1 goldens before it is built | `presenters.py`, `sales_report_service.py`, `fetch.py`, tests |

Phase 1 for a chatbot lane is the presenter against a mock: the "UI" is the WhatsApp text
and the goldens are its screenshots; the owner reviews the goldens before S2.

## Tests per slice (tester writes red first; pytest per slice, live console at the end)

S1: AC-1901 `test_items_by_quantity_golden`; AC-1902 `test_row_line_shape`; AC-1903
`test_absent_axis_prints_all`; AC-1904 `test_ranked_by_and_basis_labels`; AC-1905
`test_never_prints_past_one_hundred`; AC-1906 `test_miss_prints_no_offer`; AC-1907
`test_presenter_keeps_input_order`; AC-1908 `test_money_qty_format_and_no_dashes`; AC-1909
`test_every_golden` (parametrised over all twelve); AC-1910 `test_no_paging_words`; AC-1911
`test_how_many_reply`; AC-1912 `test_detail_offer_on_every_hit`; AC-1913
`test_fixed_lines_match_goldens`; AC-1914 `test_category_rows`; AC-1915
`test_agent_fill_note`.

S2: AC-1920 `test_rank_by_qty_and_amount_with_tiebreak`; AC-1921 `test_top_n_optional_cap_and_422`;
AC-1922 `test_bucket_date_window_and_bad_date_422`; AC-1923 `test_customer_filter_ids_and_query`;
AC-1924 `test_category_filter`; AC-1925 `test_channel_filter`; AC-1926 `test_cancelled_excluded`;
AC-1927 `test_and_of_all_filters`; AC-1928 `test_response_model_keeps_every_field`; AC-1929
`test_auth_401_403_apikey_company_scope_and_reveal_403`; AC-1930 `test_zero_line_total_included`;
AC-1931 `test_basis_delivered_default_and_ordered`; AC-1932 `test_group_category_ranking`;
AC-1933 `test_one_message_setting_withholds_rows`; AC-1934 `test_dealer_forced_to_own_ledgers`;
AC-1935 `test_detail_code_customers_and_months`.

S3: AC-1940 `test_catalog_lists_top_selling_tool`; AC-1941 `test_read_only_union_and_domain_map`.

S4: AC-1950 `test_tool_pick_top_selling_vs_reports`; AC-1951 `test_no_grant_denies_before_fetch_and_picker`;
AC-1952 `test_rank_by_and_top_n_from_parser_only`; AC-1953 `test_param_mapping_and_date_default`;
AC-1954 `test_category_entity_resolves_under_order`; AC-1955 `test_customer_picker_continues_ask`;
AC-1956 `test_follow_up_by_amount_keeps_filters`; AC-1957 `test_miss_takes_not_found_path`;
AC-1958 `test_header_skipped`; AC-1959 `test_parser_prompt_live_sha_and_schema_key`; AC-1960
`test_plain_top_n_order_ask_unchanged`; AC-1961 `test_metric_clarify_then_answer`; AC-1962
`test_group_clarify_then_answer`; AC-1963 `test_dealer_other_customer_refused_no_fetch`;
AC-1964 `test_rank_number_opens_detail`; AC-1965 `test_how_many_then_number`.

S5: AC-1970 `test_sales_agent_entity_resolves`; AC-1971 `test_sales_agent_filter_route_and_lane`;
AC-1972 `test_agent_plus_customer_and`.

S6: AC-1980 console case file against the lane stack, then production after deploy
(`documentation/agents/chatbot-verification.md`); AC-1981 SQL cross-check of one whole-book
top 5 to the cent on the prod copy.

All backend tests on Postgres via `tests/_pg_fixture.py`, seeding company, customers,
categories, products, agents, SOs and lines (CI's database is empty).

## Grill questions for the owner (answered 26 Sep 2026)

1. **Default N** when the message names none: 5? (Hard cap 10 either way, WhatsApp.)
   Owner ruling 26 Sep: no default. No number = every row, no paging; a list longer than one
   message gets the how-many question. Cap is 100. Amended PR #1258 05:32Z: no number gets
   the how-many question whatever the count; n8n chunks long messages.
2. **Default metric**: quantity or amount when the message names neither? Owner ruling 26
   Sep: no default, clarify via chat.
3. **Quantity basis**: ordered or confirmed? Owner ruling 26 Sep: support both; normal
   meaning is delivered (transferred to DO).
4. **Date range default** when none is said: Owner ruling 26 Sep: current calendar year.
5. **Who may ask**: Owner ruling 26 Sep: the sales report key; staff see every customer; a
   dealer never sees another dealer.
6. **"by category"**: Owner ruling 26 Sep: both (filter and category ranking); clarify when
   unsure, never assume.
7. **Sales agent attribution**: Owner ruling 26 Sep: `sales_orders.sales_agent_id`. S5 is
   no longer gated.
8. **Channel**: Owner ruling 26 Sep: yes.
9. **Zero-value lines**: Owner ruling 26 Sep: include.
10. **No detail offer**: Owner ruling 26 Sep: a detail offer is required.

## Backlog triggers (not built)

- Breakdown mode per agent (top N per agent, one block each): the owner asks "per agent" on
  the live console. (Per category is now answered by the category grain, per month by S7.)
- Warehouse filter (`warehouse_codes` through the existing resolver): when the owner asks
  "top 5 at BRW".
- A `sales_agent` axis on `group_by` and on the sales report: when the sales module (#1170)
  needs agent-level figures from the chatbot.
- Product family collapsing (rank base codes, not variants): when the top 5 comes back as
  five colours of one sink.

## Risks

- `_DOMAIN_HINT_EXPANSIONS["order"]["category"]` (resolver) is the one seam that can
  silently turn a category into a customer. Pinned by AC-1954 before S4 is called done.
- `policy_rows.py` is frozen seed data; every policy change here needs its migration and
  the two must agree (`test_rearch_invariants.py` family).
- `fetch.py` and `lanes/business/__init__.py` are the files every chatbot lane collides in;
  the changes are one `elif`, one dict entry and one arg block, kept that small on purpose.
- The parser prompt is a mechanical derivation of the live n8n body with trailing
  addenda; this adds a trailing block only, so `test_parser_prompt_is_live.py` still holds.
- A named N up to 100 can exceed one WhatsApp message (about 4,096 characters, roughly 50
  rows). Settled (owner, PR #1258 05:32Z): the bot sends it as one reply and n8n's existing
  chunking splits it; the lane adds no splitting of its own.
