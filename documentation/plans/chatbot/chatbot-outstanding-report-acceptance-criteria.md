# UAC - Chatbot outstanding report (SO backlog + DO pending)

Plan: `PLAN-chatbot-outstanding-report.md`. Numbering: AC-11xx. Each criterion names its
evidence (pytest / golden fixture / world / console check). "Contact" = a Respond.io contact
through `/api/v1/external/chat/turn`. "Management" = a contact whose grants reveal customer
names and quantities (the owner's own test contact today). Stacked on lane 1 of
`PLAN-chatbot-focus-multi-domain.md` (`feat/chatbot-focus`), which owns the open-question
mechanism this plan adds two kinds to. REBASED 13 Sep: the lane ships off origin/main
without #847; Phase 2 lane ACs use main's `selection_context` / `pending.kind` picker
mechanism (see the plan's "S4 on main").

## Journey

Actor: a top-management user on WhatsApp. They arrive from the Respond.io channel with a
product code in hand and want one number they can quote, then the detail behind it. The system
already knows the contact and its grants, the product master, every warehouse code, every
customer name, and every sales order line and delivery order line AutoCount has pushed.

1. They type "Srtwt7443 sales order outstanding for IB". The bot resolves the product (exact
   code, no siblings), resolves "IB" to every warehouse whose code ends in `-IB`, sees no date
   and takes all dates, sees "sales order" and takes the SO scope. One reply: a header echoing
   Product / Customer / Location / Order date, then a Sales order outstanding block
   (Ordered, Transferred to DO, Outstanding, Sales orders, Order date range, then its own
   By location and By customer lines each reading `name: ordered (O/S: outstanding)`),
   then a numbered offer: 1 Sales order list.
2. They type "SRTWT7445 outstanding in 2026". The scope word is missing. The bot asks ONE
   question: 1 Sales orders, 2 Delivery orders, 3 Both. Nothing else in the reply.
3. They type "3". The report runs with product, dates 01/01/2026 to 31/12/2026, all
   customers, all locations, both scopes. Two blocks (Sales order outstanding, Delivery order
   pending), each carrying its own By location and By customer lines, then the offer: 1 Sales
   order list, 2 Delivery order list.
4. They type "1". Every matching sales order, one row per SO, lines rolled up: SO number,
   customer, location, ordered, transferred, outstanding, order date. Every row is sent; n8n
   chunks long messages as it does today. No "+N more".
5. They type "Dealer A outstanding SRTWT7445". Customer filter by name, same report.
6. A miss ("SRTWT9999 outstanding") gets the same header and a one-line "no open sales
   order" / "no pending delivery order" per scope, then the existing escalate offer.

Told automatically: nobody. Read-only. The owner sees the scope question, the location
resolution and the filter set in the console trace.

## Measured (prod copy `sorento_ai_automation_0907`, code at origin/main, 12 Sep 2026)

- `sales_order_lines` = 448,779 rows; 25,059 have NULL `warehouse_id`.
- Header `open` + line `closed` = 8,533 lines / 981,878 qty. 5,545 of those are
  `scm_order_inquiry` retired provisional rows (0 delivered), the doctrine in
  `project_so_ingest_service.py:85-95`. `line_status='open'` is the live filter; the defect is
  that the summary's Ordered/Transferred sums ignore it (`order_service.py:191-355`).
- SRTWT7445: header open + line open = 4 lines / 221 qty; header open + line closed = 89 lines
  / 7,263 qty (retired provisional); cancelled 6 lines / 308.
- The chatbot sends every date window as `actual_delivery_date_from/to`
  (`lanes/business/fetch.py:369-383, 496-503`); the `so_outstanding` arm forwards only
  `customer_ids/product_ids/limit` (`orders.py:474-479`), so SO figures are never
  date-filtered, and the DO-outstanding arm drops every undelivered DO (NULL actual date).
- `so_outstanding` rows are one per LINE (`order_service.py:138-188`): SO331785 has two
  open lines of SRTWT7443 at 205 each and prints twice.
- Warehouse codes: `BRW`, `BRW-BB`, `BRW-IB`, `BRW-IR`, `BRW-ACTS`, `MKT-D`, `SPARE/P`,
  `REPAIR` (top by SO-line count). The `-IB` suffix is a code convention seeded at warehouse
  creation (`inventory.py:46-60`), never parsed at runtime.
- Stock answers already print `Total: 51 (O/S: 36)` and `BRW: 20 (O/S: 12)`
  (`presenters.py:1259-1287`); this plan reuses that suffix shape.

## Phase 1 - presenter over a mock report (no backend)

- **AC-1101 [T]** Given the mock report JSON for SRTWT7445 / scope both / all customers /
  location IB / dates 2026, when the presenter renders it, then the text is byte-equal to
  `samples/outstanding-report-both.txt`: header lines `Product:`, `Customer:`, `Location:`,
  `Order date:`; block `*Sales order outstanding*` with `Ordered:`, `Transferred to DO:`,
  `Outstanding:`, `Sales orders:`, `Order date range:`; block `*Delivery order pending*` with
  `DO qty:`, `Delivered:`, `Pending:`, `Delivery orders:`, `DO date range:`; a `*_By location_*`
  and a `*_By customer_*` group (bold italic sub-heading) INSIDE each block (SO figures under
  SO, DO figures under DO);
  `Reply with a number for detail:` then `1. Sales order list`,
  `2. Delivery order list`. Evidence: golden fixture test.
- **AC-1102 [T]** Given scope SO only, then the Delivery order block and option 2 are absent
  and the option list is `1. Sales order list`. Given scope DO only, the mirror. Evidence:
  golden fixtures `outstanding-report-so.txt`, `outstanding-report-do.txt`.
- **AC-1103 [T]** Every SO breakdown line reads `<name>: <ordered> (O/S: <outstanding>)` and
  every DO breakdown line `<name>: <do_qty> (O/S: <pending>)`, with thousands separators, and NULL warehouse prints as
  `Unassigned`. No line is ever elided; no "+N more" anywhere in the reply. Evidence: fixture
  with 14 customers renders 14 lines.
- **AC-1104 [T]** Every date prints `dd/mm/yyyy`; `Order date: all` when no window; a range
  prints `dd/mm/yyyy to dd/mm/yyyy`; a single day prints once. No word "oldest", "newest",
  "since". Evidence: fixture.
- **AC-1105 [T]** Header `Location:` prints the resolved codes in brackets after the token,
  `IB (BRW-IB, MWH-IB)`; an exact code prints alone `BRW-IB`; no token prints `all`. Evidence:
  fixture.
- **AC-1106 [T]** Detail list (SO): one row per SO, fields `SO Number`, `Customer`,
  `Location`, `Ordered`, `Transferred to DO`, `Outstanding`, `Order Date`, in that order, as
  `*Label:* value` lines, numbered `1.`, `2.`, ... Every row rendered. Detail list (DO): `DO
  Number`, `Customer`, `Location`, `DO Qty`, `Delivered`, `Pending`, `DO Date`. Evidence:
  golden fixtures `outstanding-detail-so.txt`, `outstanding-detail-do.txt`.
- **AC-1107 [T]** Miss: a scope with zero rows prints its block as one line `No open sales
  order.` / `No pending delivery order.` under the same header; when every requested scope is
  empty the EXISTING escalate offer and team picker follow (`escalate_yes_no` then
  `team_pick`), byte-identical to the DO answer's miss today. Evidence: fixture + world.
- **AC-1108 [T]** No `.` separators, no em/en dashes, no arrows anywhere in the rendered
  text (dash guard). Evidence: fixture assertion over every golden file.

## Phase 2 - backend report, MCP tool, lane wiring

### Backend `GET /api/v1/order-management/outstanding-report`

- **AC-1110 [BE]** Given `product_code=SRTWT7445` and no other filter, then
  `so.ordered_qty`, `so.transferred_qty`, `so.outstanding_qty` are summed over the SAME
  population: header `status='open'`, line `line_status='open'`, `qty_ordered -
  qty_delivered > 0`; and `ordered_qty == transferred_qty + outstanding_qty` holds. Cancelled
  and retired-provisional lines contribute to none of the three. Evidence: pytest seeds one
  live line (10/3), one closed line (10/10), one cancelled line, one `scm_order_inquiry`
  retired line; asserts 10 / 3 / 7.
- **AC-1111 [BE]** `order_date_from/to` filter SO rows on `sales_orders.order_date` and DO
  rows on `orders.order_date`; `actual_delivery_date` is never a filter on this route. Given
  two live SOs dated 2025 and 2026 and window 2026, then only the 2026 SO counts in every
  block (totals, by_location, by_customer, so_rows). Evidence: pytest.
- **AC-1112 [BE]** `warehouse_codes=BRW-IB,MWH-IB` filters SO lines on
  `sales_order_lines.warehouse_id` and DO lines on `order_lines.warehouse_id`. A NULL
  warehouse line is excluded when the filter is set and appears as `by_location[].code =
  null` when it is not. Evidence: pytest.
- **AC-1113 [BE]** `customer_query=Dealer A` matches `customers.customer_name` ILIKE, never
  `debtor_code`. Evidence: pytest with a code that would match and a name that would not.
- **AC-1113b [BE]** `customer_ids` (csv of `customers.id`) filters the same way and is what
  the chatbot lane sends (the resolved customer entity); `crm_outstanding_report` exposes it.
  `customer_query` and `customer_ids` together intersect. Evidence: pytest (route + catalog).
- **AC-1114b [BE]** `detail=so|do` makes the MCP tool render `_outstanding_detail` for that
  scope instead of the report (`view=render`); the route itself is unchanged by `detail`.
  Evidence: MCP pytest on `present_response`.
- **AC-1114 [BE]** `so_rows[]` is one row per SO: an SO with two live lines of the product
  (205 + 205) returns one row with `ordered_qty=410`, `location` = the distinct warehouse
  codes joined by `, `. Sorted by `order_date` asc then `so_number`. Evidence: pytest.
- **AC-1115 [BE]** `do` block: `pending_qty` = SUM `order_lines.quantity` for the product on
  orders matching `_outstanding_clause` (`order_service.py:67-93`); `delivered_qty` = same
  sum over orders matching `_delivered_clause`; `do_qty = delivered_qty + pending_qty`;
  `do_count` counts both; `do_rows[]` one row per DO (pending and delivered, each row
  carrying its own `do_qty`, `delivered_qty`, `pending_qty`). Evidence: pytest with one
  delivered DO (qty 5) and one pending DO (qty 7) asserts 12 / 5 / 7.
- **AC-1116 [BE]** `so_by_location[]` / `so_by_customer[]` carry `ordered_qty` and
  `outstanding_qty`; `do_by_location[]` / `do_by_customer[]` carry `do_qty` and
  `pending_qty`; each filtered identically to its block's totals, and each group's sums equal
  its block totals. Evidence: pytest asserts equality for all four.
- **AC-1117 [BE]** `scope=so|do|both` (default `both`); a scope not requested is absent from
  the body (not empty). Response is declared on a `response_model` and a test asserts every
  field above is present (response_model drops undeclared fields). Evidence: pytest.
- **AC-1118 [BE]** Route is behind `order_management.orders.view` and the
  `order_management` module guard; the X-API-Key principal with
  `EXTERNAL_API_KEY_ACT_AS_USER_ID` reaches it. Evidence: pytest (403 without the grant).
- **AC-1119 [BE]** Product resolution is exact on `product_code` (case-insensitive); the
  route never expands to siblings. Evidence: pytest seeds `SRTWT7445` and `SRTWT7445-A`,
  asks for the first, gets only it.

### MCP

- **AC-1120 [BE]** New tool `crm_outstanding_report` wraps the route with params
  `product_code`, `scope`, `customer_query`, `warehouse_codes`, `order_date_from`,
  `order_date_to`; the catalog test lists it and the tool is seeded (MCP tool seeding rule).
  Evidence: pytest in `sorento_crm_mcp/tests`.
- **AC-1121 [BE]** `crm_order_management_orders_list` and `_by_product_list` expose
  `customer_query` and `warehouse_codes` (the last one is new on the backend route too and
  filters on `order_lines.warehouse_id`). `order_date_*` stays OFF these tools: the standing
  test `test_orders_list_uses_actual_delivery_date_only` keeps the DO list on actual delivery
  dates. Evidence: pytest, and that standing test still green.

### Chatbot lane

- **AC-1130 [BE]** Given a message carrying the bare word "outstanding" (or "o/s", "os",
  "backlog") with a product and no document word, from a contact holding
  `sales_orders.outstanding`, when the turn compiles, then no tool is called, the reply is
  the plan's scope question, and the session carries `selection_context =
  "outstanding_scope"`, `pending.kind = "outstanding_scope"`, `last_result_set` of three
  rows (so / do / both) and `outstanding_filters` holding the parsed product, dates,
  customer and location. Evidence: pytest on compile_state / pending + console case.
- **AC-1131 [BE]** Scope words bind without a question: "sales order", "SO", "so
  outstanding" → `order_status=so_outstanding` → scope `so`; "delivery order", "DO",
  "pending delivery" → `do_outstanding` → `do`; "both" → `outstanding_both` → `both`.
  Evidence: pytest table over the parser vocabulary and the fetch mapping.
- **AC-1132 [BE]** Given `pending.kind == "outstanding_scope"` from the previous turn and
  the next message is "2" or "delivery order", then `head/output_exchange.py` stamps
  `order_status=do_outstanding`, restores `outstanding_filters` into the parser output, and
  the business lane calls `crm_outstanding_report` in the same turn with those filters
  (no re-parse of the product). "1" → so, "3" / "both" → both; an out-of-range number
  re-asks. Evidence: pytest on output_exchange + console case (journey steps 2 and 3).
- **AC-1133 [BE]** Location token resolution: a token equal to a `warehouse_code` (case
  insensitive) → that code only (`BRW` → `BRW`); a token that is the suffix of one or more
  codes after `-` (`IB` → `BRW-IB`, `MWH-IB`) → all of them; a token matching nothing → no
  location filter and no header bracket. Resolution reads the `warehouses` table, never a
  hard-coded list. Evidence: pytest table.
- **AC-1134 [BE]** No date in the message → no `order_date_*` param and header `Order date:
  all`. A parsed window → `order_date_from/to`, never `actual_delivery_date_*`, for this tool.
  Evidence: pytest on `fetch.py`.
- **AC-1135 [BE]** After a report with at least one non-empty block, the session carries
  `selection_context = "outstanding_detail"`, `pending.kind = "outstanding_detail"`,
  `last_result_set` = the offered options only (1 Sales order list, 2 Delivery order list,
  per scope present) and the same `outstanding_filters`; no escalate offer is appended on a
  hit. Evidence: pytest on compile_state / pending.
- **AC-1138 [BE]** Given `pending.kind == "outstanding_detail"` and the next message is "1",
  then the lane calls `crm_outstanding_report` again with the stored filters plus
  `detail=so` and the reply is the SO detail list (AC-1106); "2" → `detail=do`. A product
  code or a domain word instead is a new ask and the pending is dropped. Evidence: pytest +
  console case (journey step 4).
- **AC-1139 [BE]** When the tool called was `crm_outstanding_report`, `_search_scope_header`
  prints nothing (the report carries its own header lines). Evidence: pytest.
- **AC-1136 [BE]** Customer name in the message ("Dealer A outstanding SRTWT7445") resolves
  through the existing customer entity and is sent as `customer_ids`; the header prints the
  response's `customer_name`. Evidence: pytest.
- **AC-1140 [BE]** Given a contact whose granted reveal keys lack `sales_orders.outstanding`,
  when the message is "SRTWT7445 outstanding" (no scope word), then no scope question is
  asked, the report runs with `scope=do`, and the reply carries only the DO block. Evidence:
  pytest on `answer.py` with `ctx.access.attributes = []` + world.
- **AC-1141 [BE]** Given the same contact and an explicit SO ask ("sales order outstanding"
  or scope answer "1"/"3"), then no SO query runs and the reply is the header, one line
  `Sales order figures are not enabled for your account.`, then the DO block. Evidence:
  pytest asserts the report call carries `scope=do`.
- **AC-1142 [FE]** `sales_orders.outstanding` is in `FIELD_REVEAL_KEYS` (label `Sales order
  outstanding`) and in `crm_outstanding_report`'s catalog `restricted_fields`, so the pinning
  test `tests/chatbot/test_field_reveal_keys_pinned_to_catalog.py` stays green and the key
  appears on Contacts > Access > field reveals, granted and revoked the way
  `purchase_orders.placed` is; the grant flips AC-1140 on the next turn. Evidence: pytest +
  agent-browser run.
- **AC-1137 [BE]** Console check (`documentation/agents/chatbot-verification.md`) passes for
  the six journey messages as `tests/chatbot/console_cases/2026-09-13-outstanding-report.yaml`
  against the lane stack, and the trace shows the scope question asked and resolved, the
  location resolution and the final filter set. Evidence: console run recorded under
  `documentation/plans/chatbot/evidence/outstanding-report/`.

## Out of scope (backlog)

- A date clarifying question. Trigger to build it: a replayed real message whose parsed
  window was wrong. None measured today.
- Repairing `so_outstanding_summary` / `stamp_so_outstanding_rows` for other consumers of
  `include_pipeline`. Trigger: a second consumer that reads those figures.
- The SHARED product resolver's family widening. A single product token takes the
  resolver's OR-mode, where the gate calls a candidate exact only on `match_tier ==
  "exact"` - a tier `entity_resolver._prefix_probe_product` never stamps - so the whole
  prefix family arrives and the reader picks one. AND-mode already keys on "canonical_code
  EQUALS a typed token" (`gate.py`, `prod_exacts`). This lane fixes it for the OUTSTANDING
  path only (`fetch.outstanding_product_code`), deliberately: every other domain widened to
  the family on purpose, and changing the shared gate would change all of them at once.
  Trigger for the shared fix: a SECOND domain measured answering about a sibling of a code
  the customer typed exactly.
