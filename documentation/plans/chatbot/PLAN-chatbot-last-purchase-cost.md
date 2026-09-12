# PLAN: "last purchase cost" answer, per product per location, gated per contact

Status: implemented, in review (12 Sep 2026)
Branch: `feat/chatbot-last-purchase-cost`, worktree
`.claude/worktrees/chatbot-last-purchase-cost`
UAC: `chatbot-last-purchase-cost-acceptance-criteria.md`
Siblings: `PLAN-chatbot-warehouse-entity-and-last-in.md` (the "last in" tool this copies the
shape of), `PLAN-chatbot-growth-r1.md` Slice C (the per-contact field-reveal mechanism this
reuses).

## Owner ruling (12 Sep 2026, verbatim)

> we need to support asking of last purchase cost and this must be permission controlled
> per contact ... similar to our spo allocation to answer last in, we need to display per
> product code, per location, what is the last purchase cost, so we need to find the latest
> purchase order line for this product for each location and answer in a similar way for
> spo allocation, so it will be PO number, Product code, PO quantity, PO date, Cost:
> {currency} {unit price}, Discount: {currency} {unit price}, Cost after discount:
> {currency} {number}, Warehouse: {warehouse}

Second ruling, same day, against the four calls put to the owner:

> make sure our answer says Cost / unit, Discount / unit, Cost after discount / unit for
> clarity, if no warehouse then just don't show the Warehouse: xxx, yes exclude cancelled
> lines, for family resolve, resolve all, last-in also should be all family, shouldn't have
> cap at top_n

## What exists today (measured, local prod copy `sorento_ai_automation`, 12 Sep 2026)

- `purchase_order_lines` carries the whole money line from AutoCount: `unit_cost`
  NUMERIC(12,2), `discount` NUMERIC(15,2), `line_total` NUMERIC(15,2), `currency` CHAR(3),
  `warehouse_id` nullable, `line_status` open | closed | cancelled. Header
  `purchase_orders.issue_date` is populated on 6,349 of 6,349 rows, so it is the ordering
  key with no fallback needed (unlike `spo_date` on last-in).
- Coverage: 91,717 lines; 67,556 with `unit_cost`; 59,440 with cost AND warehouse; 8,116
  with cost and NO warehouse (886 products have cost ONLY on such lines); 4,826 cancelled
  lines carry a cost; 2,245 cost lines have no `line_total` (source `scm_po_history`).
  Currencies on lines: CNY, EUR, MYR, USD; every line has one.
- **`discount` is a LINE amount, not a unit figure.** On 59,585 of 59,859 fully-populated
  lines `line_total = qty_ordered * unit_cost - discount` holds to the cent (sample: M218,
  qty 19, cost 110.00, discount 1,254.00, total 836.00). 59,409 of those lines carry a zero
  discount, so the discount field is "if any". The per-unit figures the owner asked for are
  DERIVED: `discount / qty_ordered` and `line_total / qty_ordered`.
- `crm_procurement_po_placed_list` cannot answer this: it reads OPEN lines only
  (`qty_ordered - qty_received > 0`), carries no money field, and sorts by expected date.
- `crm_procurement_spo_allocations_last_receipt_list` (`spo_last_receipt_service`) is the
  shape to copy: `product_ids` / `warehouse_ids` / `top_n`, a `row_number()` window per
  product when products are named, a plain `top_n` cap when none is, an explicit company
  predicate on the windowed subquery (`.subquery()` loses the session's scope listener).
- Per-contact gating that already exists for PO data: `contact_field_reveals`
  (`app/models/access.py::ContactFieldReveal`), keys frozen in
  `contact_field_reveal_service.FIELD_REVEAL_KEYS` (`inventory.sellable`,
  `purchase_orders.placed`, `purchase_orders.supplier`), pinned to the MCP catalogue's
  `ToolSpec.restricted_fields` by `tests/chatbot/test_field_reveal_keys_pinned_to_catalog.py`.
  Default is HIDDEN. The Contacts > Access > Field reveals card is server-fed
  (`GET field-reveal-keys`), so a new key needs NO frontend change. Enforcement is in two
  places: `fetch.output_structurer` drops any envelope field whose key is in
  `restricted_fields` unless the contact holds the permission, and
  `answer._CROSSDOMAIN_RUNG_GRANT` skips a whole rung without `purchase_orders.placed`.
- One domain = one tool: `fetch.select_tool` returns `DOMAIN_SPEC[domain].tools[0]`, so the
  new tool needs its own domain row, its own intent, and the parser has to be taught it
  (the domain_hint list in the prompt is a literal; `tests/chatbot/test_domain_spec.py`
  pins the prompt's tuples to `DOMAIN_SPEC`). The parser prompt ships as an UNLABELLED new
  version through a migration (precedent `490_chatbot_parser_growth_r1.py`); the owner
  moves the `production` label.
- Family resolution: `entity_resolver._prefix_probe_product` returns up to
  `PREFIX_LIMIT = 20` candidates for a code token; every resolved member reaches the tool as
  `product_ids`, and the backend windows PER product, so a family already answers one row
  per member on last-in. The largest measured families (SRTWC8517: 8, M218: 3) sit well
  under 20. `top_n` was never an overall cap when products are named; the ruling is pinned
  by a test rather than by a code change (see "Last-in family" below).
- `system_settings.chatbot_completed_lanes` on the local copy includes `business_query`,
  so the CRM completes this lane and n8n needs no edit. **Assumed, not verified:** the
  same is true on prod.
- There is no `agent_mcp_tools` table (a stale memory says otherwise); the chatbot's pool is
  `CHATBOT_READ_ONLY_TOOLS`, derived from `DOMAIN_SPEC`, so adding the domain row is the
  whole seeding.

## Decisions

- D1 Per-unit money, labelled as such. `Cost / unit` = `unit_cost`. `Discount / unit` =
  `discount / qty_ordered`, shown only when `discount > 0`. `Cost after discount / unit` =
  `line_total / qty_ordered` when `line_total` is present, else `unit_cost` (the 2,245
  history lines state no discount and no total, so the after-discount figure IS the unit
  cost there). Two decimals, prefixed by the line's currency: `CNY 44.00`.
- D2 Location = `warehouse_id`, NULL is its own bucket. The window partitions on
  `(product_id, warehouse_id)`; Postgres groups NULLs together in `PARTITION BY`, so a
  product bought with no warehouse stated answers one row with no `Warehouse` field. The
  presenter drops a None value, which is what "just don't show" means.
- D3 Cancelled excluded: `purchase_order_lines.line_status <> 'cancelled'` AND
  `purchase_orders.status <> 'cancelled'`. Lines with `unit_cost IS NULL` never answer: a
  cost answer with no cost is not an answer.
- D4 Ordering key: `purchase_orders.issue_date DESC`, then `purchase_order_lines.created_at
  DESC`, then `id` for determinism. No fallback chain and no `_source` field: `issue_date`
  is 100% populated.
- D5 Family = every member. `product_ids` carries every resolved member and `top_n` is per
  `(product, warehouse)` group, never an overall cap. Same rule on last-in (per product).
  Unscoped ask (no `product_ids`): plain `top_n` cap over every line, newest first, exactly
  as last-in does, so a bare "last purchase cost?" costs `top_n` rows, not one per pair.
- D6 Permission = ONE field-reveal key, `purchase_orders.cost`, label "Last purchase cost",
  default hidden. Enforced twice: (a) the presenter marks the three money fields
  `restricted` so a stripped answer can never carry a cost; (b) the lane refuses the WHOLE
  domain without the grant, because a PO row without its cost is a different answer from
  the one asked. The refusal reuses the existing registered `access_denied` template
  (`CHATBOT_REPLY_ACCESS_DENIED` = "Sorry, you are not allowed to access {{team}}") but with
  the SUBJECT set to the feature, never the parser's `suggested_agent`: the reply text is
  EXACTLY `Sorry, you are not allowed to access purchase cost`. `lanes/canned.py::
  access_denied_text` (the head-level per-agent denial) is untouched; the gate calls the new
  `lanes/canned.py::field_grant_denied_text(copy, "purchase cost")` instead, so no new
  wording is invented and the two refusals stay independent. The MCP server itself stays
  unfiltered (in-app assistant and n8n operators are internal), same as every other
  restricted field.
- D7 No migration for the grant: `contact_field_reveals` already exists; the key is a
  literal in `FIELD_REVEAL_KEYS`. The only migration is the parser prompt publish.

## Change (simplest thing)

Backend (`sorento_crm_backend/`):

1. `app/services/po_last_cost_service.py` (new, read-only, mirrors
   `spo_last_receipt_service.py`): `last_cost_rows(db, *, product_ids=None,
   warehouse_ids=None, top_n=1) -> list[dict]`. Windowed branch when `product_ids` is
   given: `row_number() over (partition by product_id, warehouse_id order by
   purchase_orders.issue_date desc nulls last, purchase_order_lines.created_at desc,
   purchase_order_lines.id)`, filters D3, `warehouse_ids` narrows BEFORE the pick, explicit
   `build_company_predicate(PurchaseOrderLine, ...)` AND `build_company_predicate(
   PurchaseOrder, ...)` on the subquery. Unscoped branch: same ordering, `.limit(top_n)`.
   Row keys: `po_number`, `product_id`, `product_code`, `product_name`, `po_quantity`
   (`qty_ordered`, plain number), `po_date` (`issue_date` ISO), `currency`, `unit_cost`,
   `discount_per_unit` (None unless `discount > 0`), `unit_cost_after_discount`,
   `warehouse` (`warehouse_code` or None). Money values as `float` rounded to 2 dp.
2. `app/api/v1/procurement/purchase_orders.py`: `GET /last-cost` registered BEFORE any
   `/{po_id}` route (same reason `/placed` and `/last-receipt` are), params `product_ids`,
   `warehouse_ids` (via `parse_uuid_list`), `top_n` (1..50), `Depends(
   get_current_user_or_api_key)`, same `{data, pagination, empty}` envelope as
   `/spo-allocations/last-receipt`.
3. `app/services/contact_field_reveal_service.py`: add
   `("purchase_orders.cost", "Last purchase cost")` to `FIELD_REVEAL_KEYS`.
4. `app/services/chatbot/contracts.py`: new `DomainSpec` row `purchase_cost`
   (`intents=("check_po_cost",)`, `bare_entity_type=None`, `switch_words=("cost",
   "成本", "harga belian")` matched per whole token, `tools=(
   "crm_procurement_po_last_cost_list",)`, `escalation_team="purchasing"`).
   `CHATBOT_READ_ONLY_TOOLS` derives from it.
5. `app/services/chatbot/lanes/business/gate.py`: `ALLOWED["purchase_cost"] = ["product",
   "warehouse", "category", "brand"]`; no `ALLOWS_EMPTY` row (a bare "last purchase cost"
   with no product fails the gate and asks, same as `spo_allocation`).
6. `app/services/chatbot/lanes/business/fetch.py`: add the tool to `TOP_N_DIRECT_TOOLS`
   (it has its own `top_n`); `TYPE_TO_PARAM["warehouse"]` already maps to `warehouse_ids`.
7. `app/services/chatbot/head/output_exchange.py::derive_routing`: `purchase_cost` ->
   `{"suggested_team": "purchasing", "suggested_agent": "general_enquiries"}` (same as
   `purchase_order`).
8. Whole-domain grant gate, in `lanes/business/__init__.py` at the point where the domain
   is known and `ctx["access"]["attributes"]` is available, BEFORE any tool call:
   `DOMAIN_GRANT_REQUIRED = {"purchase_cost": "purchase_orders.cost"}` (module constant in
   `answer.py` beside `_CROSSDOMAIN_RUNG_GRANT`). Without the grant: trace entry
   `{"domain": "purchase_cost", "skipped": "not_granted", "needs":
   "purchase_orders.cost"}`, reply = `access_denied_text(...)` for team `purchasing`,
   turn ends. No probe, no tool call.
9. `app/services/chatbot_parser_prompt.py`: a `LAST_COST_ADDENDUM` appended to BOTH bodies
   (full and slim), teaching `intent_hint "check_po_cost"`, `domain_hint "purchase_cost"`,
   the phrasing ("last purchase cost", "last cost", "what did we pay", "buying price",
   "成本", "上次采购价", "harga belian terakhir"), and that "how much do we sell it for" is
   NOT this domain. Extend the literal `domain_hint = ONE of:` list and the intent list.
10. `alembic/versions/513_chatbot_parser_last_cost.py`: publishes both bodies as the next
    `chatbot_semantic_parser` versions, NO label, idempotent, `publish(session)` callable
    outside alembic, exactly as 490. Numbered 513, not 511: main's own head is already
    `512_hidden_by_default_col`, and two unrelated `511_*` files already occupy that
    number. `down_revision` = `512_hidden_by_default_col` (re-verify against the current
    main head with `./scripts/alembic-reparent.sh` before PR).
11. `app/services/mcp_tool_capability_service.py`: `ToolIntent` for the new tool
    (category `general_enquiries.procurement`, typical questions in en / zh / ms).

MCP (`sorento_crm_mcp/sorento_crm_mcp/`):

12. `catalog.py`: `ToolSpec("crm_procurement_po_last_cost_list", ...)`, path
    `/api/v1/procurement/purchase-orders/last-cost`, params `("product_ids",
    "warehouse_ids", "top_n", "contact_id", "space_id")`, `domain="purchase_cost"`,
    `related_tools=("crm_procurement_po_placed_list",
    "crm_procurement_spo_allocations_last_receipt_list")`, `escalation_team="procurement"`,
    `restricted_fields=(("purchase_orders.cost", "Last purchase cost"),)`. Description
    states the row order, the per-unit derivation, the "if any" fields, D5, and that the
    whole answer is RESTRICTED to a contact holding `purchase_orders.cost`.
13. `presenters.py`: `_po_last_cost(rows, b)` rendering, in this exact order:

        PO Number, Product Code, PO Quantity, PO Date, Cost / unit,
        Discount / unit (if any), Cost after discount / unit, Warehouse (if any)

    Money as `f"{currency} {value:.2f}"`. Then `b.restrict("unit_cost",
    "purchase_orders.cost")`, `b.restrict("discount_per_unit", ...)`,
    `b.restrict("unit_cost_after_discount", ...)`. Intro line: "Here is the last purchase
    cost per product and location." Register in the presenter map and the intro map.

Last-in family (D5, no code change expected):

14. `tests/test_spo_last_receipt.py`: a 3-member family with `top_n=1` returns 3 rows, one
    per member; `top_n=2` returns up to 2 per member, never 2 overall. If this test is
    already green on `origin/main` it is kept as the pin; if it is red, the fix is in
    `spo_last_receipt_service`, not in the lane.

No frontend change (the reveals card is server-fed). No n8n change (see the assumption
above). No new table, no new column.

## Tests (Phase 2, red first, Postgres only via `tests/_pg_fixture.py`)

- `tests/test_po_last_cost.py` (service + route): one row per `(product, warehouse)`;
  NULL warehouse is its own row with `warehouse is None`; cancelled line and cancelled PO
  excluded; `unit_cost IS NULL` excluded; ordering by `issue_date` then `created_at`;
  `discount_per_unit` None when discount is 0 or NULL, `66.0` for the M218 shape (qty 19,
  discount 1254); `unit_cost_after_discount` = `line_total/qty` (44.0), and = `unit_cost`
  when `line_total` is NULL; `warehouse_ids` narrows before the pick; family of 3 with
  `top_n=1` -> 3 rows; unscoped `top_n=2` -> exactly 2 rows; company scope: a line owned
  by another company on the same product never answers under a scoped session; route
  envelope shape and `top_n` bounds.
- `tests/chatbot/test_domain_spec.py` passes with the new row (prompt tuples, read-only
  pool, switch words unique).
- `tests/chatbot/test_field_reveal_keys_pinned_to_catalog.py` passes with the new key.
- `tests/chatbot/test_last_cost_gate.py`: contact WITHOUT `purchase_orders.cost` ->
  `access_denied` reply, no MCP call, trace carries `not_granted`; contact WITH it -> tool
  called, reply contains "Cost / unit"; `output_structurer` drops the three money fields
  when the grant is absent even if the gate were bypassed.
- `sorento_crm_mcp/tests/test_presenters.py`: exact field order as a list; "if any" absence
  for discount and warehouse; money formatting; the three restricted keys in the envelope.
- `sorento_crm_mcp/tests/test_field_reveal_keys_declared.py` covers the new
  `restricted_fields` pair.
- Console case `tests/chatbot/console_cases/2026-09-12-last-cost.yaml`: "last purchase
  cost for M218" as a granted contact and as a default contact (both outcomes), plus a
  family code (SRTWC8517) asserting one row per member.

## Rollout

0. HARD PRECONDITION, before the label move (review S2/S3): confirm on prod that
   `system_settings.chatbot_completed_lanes` contains `business_query` AND
   `chatbot_business_lane_enabled` is true. A turn the CRM does not complete itself
   DELEGATES to n8n, which has no field-reveal drop of its own - moving the parser
   label with either switch off would let an ungranted contact reach the tool's raw
   answer through the n8n path, bypassing the whole-domain gate entirely. `python -m
   app.scripts.seed_mcp_tool_capabilities` is safe to run any time after deploy: the
   `_EMBEDDING_SKIP_TOOLS` entry (SF1) removes the tool from the RAG pool and from
   `ai_assistant_configs.enabled_tools` on the same pass, it does not add it anywhere.
1. Deploy. The prompt version is unlabelled, so no customer turn changes.
2. Owner grants `purchase_orders.cost` on the test contact (Contacts > Access > Field
   reveals), moves the `production` label to the new parser version, runs the console case.
3. Rollback = move the label back and untick the key. No deploy.

Owner calls, not changed (review S2/S3):

(a) `GET /purchase-orders/last-cost` keeps its siblings' posture -
`get_current_user_or_api_key`, no RBAC permission slug - because the chatbot's
act-as principal may not hold `scm.purchase_orders.view`; a permission slug here
would 403 the very caller this tool exists for.
(b) The grant is issued under the `user_management.contacts.edit` permission, same as
the existing `purchase_orders.supplier` field-reveal key - Contacts > Access is one
screen with one edit permission, not a per-key permission matrix.
