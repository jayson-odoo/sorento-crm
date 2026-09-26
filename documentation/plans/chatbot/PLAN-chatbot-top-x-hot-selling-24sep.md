# PLAN - Chatbot: top X hot selling items by category / customer / sales agent / date range

Status: draft, pre-grill (24 Sep 2026). Track: full track (new route + MCP tool = a new
external ingest surface, one policy-row migration, one prompt migration, one entity-kind
migration in the gated slice; the diff will pass 300 lines). No feature code in this PR.
Issue: #1171. UAC: `chatbot-top-x-hot-selling-24sep-acceptance-criteria.md` (AC-19xx).
Classification: CORE, `public` schema, no new table, no new column. The chatbot module is
where the wiring lands; the report itself is an order-management read.
Precedent: `PLAN-chatbot-sales-report.md` (#1034, BUILT). Every seam below copies that lane's
seam WITH the justification that earned it, or says why it does not.

## Journey

Actor: a management or sales contact on WhatsApp who already holds the sales report grant.
They want to know what is moving. The system already knows the contact, its companies, every
customer ledger, the product master with its category, the salesperson master and every SO
line AutoCount has pushed (quantity ordered, quantity transferred to DO, line total, required
date, the SO's agent code).

1. They type "top 5 selling items last month". One reply: a numbered list of five products,
   code and name, quantity and amount, ranked by quantity. Nothing is asked.
2. They type "top 10 for hanlim this quarter". Same list, filtered to the HANLIM ledgers, the
   header says so. An ambiguous customer name goes through the existing customer picker;
   "1" or "all" continues this ask.
3. They type "top 3 kitchen sinks in 2026". Same list, filtered to the KITCHEN SINK category.
4. They type "top 5 by sales agent SEAN I this year". Same list, filtered to the SOs that
   agent sold. (Gated slice, see S5.)
5. They type "top 5 by amount" after any of the above. Same filters, ranked by amount.
6. A contact without the grant gets `Sales report is not enabled for your account.` and
   nothing is fetched.

Decisions asked of the user: none beyond the existing customer picker. N, metric, date range
and channel are derived, with the defaults the grill fixes (section "Grill questions").

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

**One new report, one new `order_status` value, one new parser key, one unblocked entity
kind, and (gated) one new entity kind. No registry, no new engine, no new pending kind, no
new reveal key, no detail offer.**

Why a second route rather than a mode on `crm_sales_report`: the sales report requires a
subject (422 `subject_required`, a scan guard), prints month blocks, arms a detail offer and
defaults product-only asks to the current year (S18). A ranking has no subject, prints one
list, offers nothing. Folding it in means a mode switch in a shipped, 60-AC report mid fix
round; a sibling route that reuses the same service helpers is fewer moving parts.

### The reply (contract for Phase 1)

```
Top 5 selling items
Ranked by: Quantity
Customer: HANLIM TRADING SDN BHD, HANLIM TRADING SDN BHD [A/C I]
Category: all
Sales agent: all
Channel: all
Delivery date: 01/08/2026 to 31/08/2026

1. SRTWT7445 Kitchen Sink 2 Bowl: Qty 1,240, RM 86,400.00
2. SRTKT39SS Kitchen Tap: Qty 980, RM 31,200.00
3. ...
```

Rules: at most 10 rows (the route caps `top_n` at 10 and the presenter never prints past
10); one line per row, `n. CODE Name: Qty q, RM v`; `Ranked by:` prints `Quantity` or
`Amount`; every absent header axis prints `all` (never an omitted line); dates print through
`_outstanding_date_range` and money through `_rm_money`, quantities through
`_outstanding_fmt_int` (all three exist in `presenters.py`). No closing offer sentence. Miss:
header, blank line, `No sales found.`. Denied: `Sales report is not enabled for your
account.` and nothing else (the sales report's own line, one literal). No dash characters.

### Backend contract

`GET /api/v1/order-management/top-selling` on the sales report's own no-prefix router
(`orders.py::sales_report_router`, mounted beside `/sales-report`), same auth dependency
(`order_management.orders.view` with API key), same `contact_id` / `space_id` both-or-neither
rule and the same per-contact `sales_orders.sales_report` re-check (S14 of the sales report).

| param | type | rule |
|---|---|---|
| `top_n` | int | default per grill (proposed 5); 1..10, above 10 clamps to 10, below 1 is 422 |
| `rank_by` | `qty` / `amount` | default per grill (proposed `qty`); else 422 |
| `customer_ids` | csv uuid | the lane's resolved ledgers |
| `customer_query` | str | `ILIKE %q%`, min 3 chars (same guard as the sales report) |
| `category_ids` | csv uuid | resolved category rows |
| `sales_agent_ids` | csv uuid | resolved `sales_agents` rows (S5, gated) |
| `channel` | `dealer` / `project` | absent = all, else 422 |
| `date_from`, `date_to` | flex date | on the bucket date, `_parse_flex_date` |

No subject is required: `top_n` bounds the output, and the date default bounds the scan
(section "Grill questions", Q4). No `detail` param, no `warehouse_codes` (not in the ask;
trigger to add: the owner asks "top 5 at BRW").

Response (`TopSellingResponse`, every field declared, asserted through the route):

```
{
  "top_n": 5, "rank_by": "qty",
  "customer_name": str | null, "category_name": str | null, "sales_agent": str | null,
  "channel": "dealer" | "project" | null,
  "date_from": date | null, "date_to": date | null,
  "rows": [ { "rank": 1, "product_code": str, "product_name": str,
              "qty": int, "amount": float } ]
}
```

Service: `top_selling(db, filters) -> dict` in `app/services/sales_report_service.py`, ONE
grouped query over `sales_order_lines` join `sales_orders` join `products`, optional join
`product_categories`, `GROUP BY product_id, product_code, product_name`, `ORDER BY <metric>
DESC, <other metric> DESC, product_code ASC`, `LIMIT top_n`. Reuses `_common_filters` (extended
with `category_ids` and `sales_agent_ids`), `_bucket_expr`, `_per_line_exprs` (the metric is
`ordered_qty` / `ordered_value` from that dict, or the confirmed pair if Q3 rules so),
`_customer_echo`, `_qty`, `_money_edge`. Aggregated in SQL (S17 of the sales report). Decimal
throughout, quantised at the edge. Company scope through the ORM classes, never raw text SQL.

### Parser (S4)

- `order_status` gains `top_selling`: "top 5 selling", "best selling", "hot selling", "top
  items", "most sold", "paling laku", "畅销". The addendum says in words that "top 5" with no
  sales word under an order / stock question stays what it was (`top_n` on an order list).
- New nullable key `rank_by`: `"qty" | "amount" | null`, from the current message only:
  "by quantity", "by qty", "by units", "ikut kuantiti" -> `qty`; "by amount", "by value", "by
  sales value", "by revenue", "ikut nilai" -> `amount`. Declared in the strict schema, in
  `required`, and in `TOLERATED_ABSENT` (the same reason `sales_channel` is: strict mode
  rejects a property absent from `required`, and no recorded emission carries it).
- `top_n`: unchanged, already taught. The lane applies the default when null.
- `category` under `order`: the addendum names category words on a top-selling ask as
  entities with hint `category`, `hint_confident: true`.
- `sales_agent` (S5): a new entity hint, "by sales agent X", "agent X", "salesman X",
  "jurujual X".

No word table anywhere in Python (S12 of the sales report holds).

### Lane wiring (S4), smallest shape per seam

1. `contracts.ENTITY_HINTS`: `sales_agent` added in S5 only.
2. `turn/policy_rows.DEFAULT_DOMAIN_ROWS["order"].tools` += `crm_top_selling_report`, plus
   `DATE_PARAM_TOOLS`; a `chatbot_rearch_s13`-style migration applies the same to a seeded DB.
3. `gate.ALLOWED["order"]` += `category` (and `sales_agent` in S5). `NO_TOOL_ID` stays as is
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
   entities typed `sales_agent` (S5); `rank_by` from `semantic_input`; `top_n` from
   `semantic_input` (absent = route default); `channel` from `sales_channel`; the date default
   (Q4) built HERE, never in the route, turned off by `broaden_axis == "date"` exactly as S18.
8. `_fetch_semantic_input` gains `rank_by`. `turn/apply._IDLE_CHAT_DISQUALIFIERS` gains
   `rank_by`. `rank_by` is NOT carried into `Focus` (current message only, like `top_n`); a
   follow-up "by amount" is a new ask under the carried `focus.status == "top_selling"` and
   the carried customer / category / dates, which is what the customer means.
9. `output_structurer`: `crm_top_selling_report` takes the miss path on `has_result: false`
   and arms nothing on a hit. `_search_scope_header` skipped for it, same as the two reports.
10. `resolve_gate` picker hint off for `top_selling` (R20 rule), same population reason.
11. `mcp_tool_domains.py`: `crm_top_selling_report` under `orders`. NO in-app assistant
    bootstrap (security B1 of the sales report: the same money, same reason).

## Filters combination matrix

Every filter is optional and every combination is one query with the filters ANDed. The
header prints the axis when given and `all` when not.

| customer | category | sales agent | date | channel | what runs |
|---|---|---|---|---|---|
| no | no | no | no | no | whole book over the default window (Q4); header says the window |
| yes | no | no | any | any | that ledger family only |
| no | yes | no | any | any | products in that category only |
| no | no | yes | any | any | SOs that agent sold (S5) |
| yes | yes | no | any | any | AND |
| yes | no | yes | any | any | AND; a customer whose SOs carry another agent code returns fewer rows, never a picker |
| no | yes | yes | any | any | AND |
| yes | yes | yes | any | any | AND |
| any | any | any | "all dates" said | any | date default off, `Delivery date: all` |
| any | any | any | any | dealer / project | `demand_class` filter, header `Channel: Dealer / Project` |

`top_n` and `rank_by` apply to every row of the matrix. An ambiguous customer name takes the
existing picker on every row that names one; a category token that resolves to several
categories takes `optional_filter` (the kind row's default) and a test pins what that means
here: all matched categories ANDed as an `IN`, never a picker (Q6 may change this).

## Slices

| slice | phase | what | files |
|---|---|---|---|
| S1 | 1 | Presenter over mock JSON; goldens for whole book / customer / category / by amount / miss; dash guard | `sorento_crm_mcp/sorento_crm_mcp/presenters.py` (`_top_selling`, `_top_selling_envelope`), `documentation/plans/chatbot/samples/top-selling-*.txt` + `.json`, `sorento_crm_mcp/tests/test_presenters_top_selling.py` |
| S2 | 2 | Route + service + response model | `app/api/v1/order_management/orders.py`, `app/services/sales_report_service.py`, `app/schemas/order_management.py`, `tests/test_top_selling_report.py` |
| S3 | 2 | MCP ToolSpec + domain map | `sorento_crm_mcp/sorento_crm_mcp/catalog.py`, `app/services/mcp_tool_domains.py`, `sorento_crm_mcp/tests/test_catalog_top_selling.py` |
| S4 | 2 | Parser addendum + prompt migration, `rank_by` key, policy-row migration, gate row, tool override, arg block, focus rules | `chatbot_parser_prompt.py`, `alembic/versions/<n>_chatbot_top_selling_vocab.py`, `alembic/versions/chatbot_rearch_s13.py`, `contracts.py`, `head/parser.py`, `turn/policy_rows.py`, `turn/apply.py`, `lanes/business/gate.py`, `lanes/business/__init__.py`, `lanes/business/fetch.py`, `lanes/business/resolve_gate.py`, `engine.py`, `tests/chatbot/test_top_selling_lane.py`, `tests/chatbot/console_cases/2026-09-24-top-selling.yaml` |
| S5 | 2, gated | Sales agent slot: entity hint + kind row migration + resolver source + gate row + arg param + route param + prompt words | `contracts.py`, `turn/policy_rows.py` + migration, `entity_resolver.py`, `gate.py`, `fetch.py`, `orders.py`, `sales_report_service.py`, `chatbot_parser_prompt.py` (+ migration), `tests/chatbot/test_top_selling_sales_agent.py` |
| S6 | 3 | reviewer + security-reviewer (new route, reveal gating, company scope) + console check, in parallel | `documentation/plans/chatbot/evidence/top-selling/` |

S5 is gated on #1168 (T4) / #1170 (T6) confirming `sales_agents` stays the salesperson
master and on the measured `sales_orders.sales_agent_id` fill rate. It ships only when both
are answered; S1 to S4 and S6 do not wait for it and the header prints `Sales agent: all`
until then. Phase 1 for a chatbot lane is the presenter against a mock: the "UI" is the
WhatsApp text and the goldens are its screenshots; the owner reviews the goldens before S2.

## Tests per slice (tester writes red first; pytest per slice, live console at the end)

S1: AC-1901 `test_whole_book_golden`; AC-1902 `test_row_line_shape`; AC-1903
`test_absent_axis_prints_all`; AC-1904 `test_ranked_by_label`; AC-1905
`test_never_prints_past_ten`; AC-1906 `test_miss_prints_no_offer`; AC-1907
`test_presenter_keeps_input_order`; AC-1908 `test_money_qty_format_and_no_dashes`.

S2: AC-1920 `test_rank_by_qty_and_amount_with_tiebreak`; AC-1921 `test_top_n_default_cap_and_422`;
AC-1922 `test_bucket_date_window_and_bad_date_422`; AC-1923 `test_customer_filter_ids_and_query`;
AC-1924 `test_category_filter`; AC-1925 `test_channel_filter`; AC-1926 `test_cancelled_excluded`;
AC-1927 `test_and_of_all_filters`; AC-1928 `test_response_model_keeps_every_field`; AC-1929
`test_auth_401_403_apikey_company_scope_and_reveal_403`; AC-1930 `test_zero_line_total_ranks_by_qty_only`.

S3: AC-1940 `test_catalog_lists_top_selling_tool`; AC-1941 `test_read_only_union_and_domain_map`.

S4: AC-1950 `test_tool_pick_top_selling_vs_reports`; AC-1951 `test_no_grant_denies_before_fetch_and_picker`;
AC-1952 `test_rank_by_and_top_n_from_parser_only`; AC-1953 `test_param_mapping_and_date_default`;
AC-1954 `test_category_entity_resolves_under_order`; AC-1955 `test_customer_picker_continues_ask`;
AC-1956 `test_follow_up_by_amount_keeps_filters`; AC-1957 `test_miss_takes_not_found_path_no_offer`;
AC-1958 `test_header_skipped`; AC-1959 `test_parser_prompt_live_sha_and_schema_key`; AC-1960
`test_plain_top_n_order_ask_unchanged`.

S5: AC-1970 `test_sales_agent_entity_resolves`; AC-1971 `test_sales_agent_filter_route_and_lane`;
AC-1972 `test_agent_plus_customer_and`.

S6: AC-1980 console case file against the lane stack, then production after deploy
(`documentation/agents/chatbot-verification.md`); AC-1981 SQL cross-check of one whole-book
top 5 to the cent on the prod copy.

All backend tests on Postgres via `tests/_pg_fixture.py`, seeding company, customers,
categories, products, agents, SOs and lines (CI's database is empty).

## Grill questions for the owner

1. **Default N** when the message names none: 5? (Hard cap 10 either way, WhatsApp.)
2. **Default metric**: quantity or amount when the message names neither? Proposed quantity,
   with the amount printed beside it on every row.
3. **Quantity basis**: ordered (`qty_ordered`, what the customer asked for) or confirmed
   (`LEAST(qty_delivered, qty_ordered)`, what has gone to DO)? Same question for amount.
4. **Date range default** when none is said: current calendar year (the sales report's S18
   precedent), current month, or all dates? Whole-book all-dates is the largest scan.
5. **Who may ask**: staff only (the `sales_orders.sales_report` reveal key, ticked per
   contact) or dealers too? A dealer holding the key can ask "top 5 for <another dealer>";
   company scope alone does not stop that. If dealers may ask, should the customer filter be
   forced to their own ledgers?
6. **"by category"**: a filter (items inside one category, proposed) or a breakdown (top N
   per category, one block each)? The breakdown is the backlog trigger otherwise.
7. **Sales agent attribution**: by `sales_orders.sales_agent_id` (who sold the SO, proposed)
   or by `customers.sales_agent_id` (the customer's assigned agent)? And does T4 / T6 keep
   `sales_agents` as the master, so the resolver source reads that table?
8. **Channel**: apply the existing dealer / project word (`sales_channel`) as a filter here
   too? Proposed yes, it is free.
9. **Zero-value lines**: 22,717 lines dated 2026 carry `line_total = 0`; an amount ranking
   undercounts those items. Accept and print, or exclude zero-amount lines from the amount
   ranking only?
10. **No detail offer**: one message, no "Reply 1 for ..."? Proposed none. Trigger to add
    one: the owner asks "which customers bought #1".

## Backlog triggers (not built)

- Breakdown mode (top N per category / per agent): when Q6 rules for it or the owner asks
  "per category" on the live console.
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
