# PLAN - Chatbot: a linked contact is scoped to its customers; "my" / "me" means them

Status: grilling (29 Sep 2026; crew lane CHATBOT-CUSTOMER-SCOPE, PR #1365). Standard track:
this is an authorization boundary (security-reviewer runs). UAC:
`chatbot-customer-scope-29sep-acceptance-criteria.md` (written once the grill is answered).

Owner, verbatim (29 Sep 2026):

> after we have binded a contact to customer(s), they can only check the details relevant to
> the linked customer, meaning, it cannot ask about DO of other customer, outstanding for other
> customers, basically at the MCP layer, when we detect the customer_ids is not aligned with the
> linked customer, we need to block, or, even at the resolve entity layer which is a bit more
> upstream, i think better be upstream so we block as early as possible, and the chatbot needs
> to be able to understand when the user refer to "my", "me" etc, it means the customer, like
> what's my delivery, what's my xxx, the parser might need to emit this as a signal, for resolve
> entity processing to know hey, this contact is asking for his details, so need to find his
> linked customer etc etc

## Sibling lane: the contact <-> customers relation already exists

The brief says to build against CONTACT-CUSTOMERS's planned relation. It is not planned, it is
shipped: `respond_contact_customers` (`app/models/access.py:11-64`, migration
`312_respond_contact_customers.py`), keyed on the INTERNAL `respond_contacts.id` (not the
Respond.io id), one row per (contact, customer), `is_primary` at most one per (contact,
company). Service: `app/services/contact_customer_service.py` (`list_links`,
`resolve_customer`, `link_customer`, `unlink_customer`, `propose_customers`). What does not
exist is a route or a screen that calls `link_customer` (the only writers are tests), so the
sibling lane is presumably the binding UI; this lane reads the table and needs nothing from it
beyond rows existing.

## Map of today's path for a customer-scoped ask

All paths under `sorento_crm_backend/app/` unless given in full. Read on main `bc75eb96`.

### 1. Entry and contact identity

- `api/v1/external/chat.py:171-218` `POST /chat/turn` -> `engine.run_turn(envelope)`.
- `engine.py:478-491` `_contact_respond_id(envelope)` = `envelope.contact["id"]`, the Respond.io
  id; the ONLY per-turn identity.
- `engine.py:1950-1957`: `_contact_company_scope` (`engine.py:414-439` ->
  `company_scope_resolver.resolve_contact_company_scope:210-230`) stamps every session in the
  turn with the contact's COMPANIES (`respond_contact_companies`). Company level only; nothing
  on the path ties a customer to the asking contact.
- `head/access.py:104-136` `check_access` (called `engine.py:2868-2872`): agent grant
  (`access_agents`), field-reveal keys (`sales_orders.outstanding`,
  `sales_orders.sales_report`, ...), hidden spec keys. None concerns WHICH customer's data.
- `turn_runtime.py:339-401` `load_profile` -> `Profile{tier, default_ledgers, ...}`
  (`turn/state.py:163-190`). `tier == "office"` is staff (`is_staff_profile`,
  `turn/state.py:192-199`). `default_ledgers` is loaded from `respond_contacts.chatbot_profile`
  and printed to the parser (`turn/memory.py:206-215`) but never resolved or enforced.

### 2. Parser: what it emits about a customer, and no self signal

- Wire schema: `head/parser.py:84-468` `_build_json_schema` (strict, `additionalProperties:
  false`); entity item `{raw, hint, canonical_code, current_message, confident,
  hint_confident, quantity, spec_key, spec_value}` (`:138-193`). A customer is only an
  `entities[]` item with `hint: "customer"` (`contracts.ENTITY_HINTS:190-207`).
- Prompt (`services/chatbot_parser_prompt.py:494`, rendered from the published registry
  version at runtime): OUTPUT block prompt L750-788; hint `customer` = "the party whose order,
  DO, account, or delivery the request is about" (L383); `order` = "an existing customer order
  or its DO number" (L385). `group_by: "customer"` is a breakdown axis, not a filter.
- **No key for "my / me / our".** The pronoun rule (L424-428) makes "this customer" / "them" a
  backward reference (`anaphora.backward_reference`), "where is my shipment" is an ETA ask
  (L304), "we / us" means the COMPANY (L924-925, L995-1003). "what's my outstanding" today
  emits no customer entity; under `order` the gate then fails on `ALLOWS_EMPTY["order"] =
  False` (`lanes/business/gate.py:133-142`) and asks for scope, or a carried customer is
  reused.
- Adding a key: `head/parser.py:422-467` (schema), `contracts.TOLERATED_ABSENT:501`, and a
  prompt-version migration that publishes a new version with the label unmoved (pattern:
  `alembic/versions/chatbot_top_selling_vocab.py`).

### 3. Resolve entity: customer mention -> customer ids

1. `engine.py:3181-3185` `with_carried_entities`; `engine.py:3199-3209` is where top selling
   already rewrites the resolver input per contact (precedent A below): the seam a general
   scope hook belongs on.
2. `engine.py:3229-3268` -> `turn_runtime.resolve_kinds:1749-2043` ->
   `lanes/business/resolve_gate.run:930` -> `services.resolve_entity(resolve_entity_body)`
   (`resolve_gate.py:1009-1017`; body `:518-704`, `allowed_entity_types=[hint]` `:587-588`,
   `contact_id`/`space_id` `:608-609`).
3. `lanes/business/services.py:139-161` calls `api/v1/system/references.py:2771`
   `resolve_reference_post` IN PROCESS -> `entity_resolver.resolve_references:4728`.
4. Customer probes: `_probe_customer` (`entity_resolver.py:1069-1151`, exact code, whole-word
   name or phone, cap 25), `_probe_customer_debtor_name` (`:1154`), prefix probes
   (`:1977`, `:1997`), trigram (`:2956-3042`). DO number: `_probe_customer_order`
   (`:976-1000`, exact `Order.order_number`). **None filters by contact**; company scope only.
   The route's `contact_id` drives spec/stock visibility only (`references.py:1406-1418`).
5. Result: `ResolvedEntity{entity_type: "customer", uuid, canonical_code, display}`
   (`:498-530`); settles onto `focus.customers` (`turn/apply.py:115-126`,
   `turn/state.py:87-92`). Ambiguous names open the customer picker
   (`gate.py:1745`, `resolve_gate.py:1090-1130`), which PRINTS every matching customer's name.

### 4. Tool args and the MCP call

- `engine.py:3580` `make_tool_runner` (`turn_runtime.py:2513`), `engine.py:3711`
  `turn/fetch.run_fetch:106` -> `lanes/business/__init__.py:1244 run_fetch` ->
  `fetch.entity_ids_transformer:591-1128` -> `fetch.call_tool:1227-1245` (read-only allow-list
  `:1208-1210`) -> `services._mcp_call:218-259` -> `MCPRuntimeClient` over HTTP
  (`ai_assistant_service.py:412-413`, `config.py:272` default `http://localhost:8765/mcp`).
- `fetch.TYPE_TO_PARAM:306-332`: `customer -> customer_ids`; `order`, `customer_order`,
  `order_number -> order_ids`. Outstanding (`:680-740`) and sales report (`:746-806`) also
  take carried `outstanding_carried_customer_ids` (`turn_runtime.py:2294-2349`).
  `contact_id` + `space_id` always sent (`:1123-1127`) = COMPANY scope only.
- **The one contact-derived customer scope today:** `fetch.py:832-835` overrides
  `customer_ids` with `slot["dealer_customer_ids"]` for `crm_top_selling_report`.
- The MCP server (`sorento_crm_mcp/sorento_crm_mcp/`) is a stateless pass-through: one shared
  `X-API-Key` (`http_client.py:20-30`), tool args forwarded as query params
  (`server.py:1596-1602`), no DB, no session. "The MCP layer" therefore means the backend
  route each tool calls; the backend resolves the key to the integration's act-as user
  (`dependencies.py:592-628`).

### 5. Every MCP tool that takes a customer identifier (census, `catalog.py`)

| Tool | Customer args | Route | Customer filter | Tied to the asking contact? |
| --- | --- | --- | --- | --- |
| `crm_order_management_orders_list` (`catalog.py:566-630`) | `customer_ids`, `customer_query`, `order_ids` | `orders.py:303` (`customer_ids` 321, `customer_query` 347) | `order_service.py:879-896`; `order_ids` `:876-877` | **No.** No customer arg = every customer's DOs in the company. A DO NUMBER resolves to `order_ids` with no ownership check. |
| `crm_order_management_orders_by_product_list` (`:631-673`) | `customer_ids`, `customer_query` | `orders.py:740` (766, 774) | `order_service.py:1786-1797` | No. |
| `crm_outstanding_report` (`:674-737`) | `customer_ids`, `customer_query` | `orders.py:1454` (1478, 1482); **no `contact_id` param** | `outstanding_report_service.py:306-313`, `:507-514` | No. The `sales_orders.outstanding` reveal is checked only in the lane (`lanes/business/__init__.py:62, 1612`), never on the route. |
| `crm_sales_report` (`:738-777`) | `customer_ids`, `customer_query` | `orders.py:1659` (contact params 1716-1727) | `sales_report_service.py:256-263` | Partly: reveal key re-checked when `contact_id` is sent (`orders.py:1796-1809`); any `customer_ids` honoured (`:1820-1844`). |
| `crm_top_selling_report` (`:778-824`) | `customer_ids`, `customer_query` | `orders.py:1944` | `sales_report_service.py:590, 633` | **Yes, the only one**: `_top_selling_dealer_scope` (`orders.py:1915-1941`) forces a non-staff linked contact to its links, 403 `customer_not_permitted` on any other id or name (`:2119-2142`); only when contact args are sent. |
| `crm_order_analytics` (`:857-888`) | `customer_ids` | `orders.py:942` (957) | `order_service.py:1498-1513`, `:1619-1628` | No. |
| `crm_master_customers_list` (`:1069-1091`) | `customer_ids` | `orders.py:653` (debtors) | `orders.py:700-702` | No. No arg = every debtor's name and code (limit 20). |
| `crm_complaints_list` (`:1093-1121`) | none | `complaints.py:220` | none; rows carry `customer_name` + `delivery_order_number` | No. Complaints have `customer_name` text only (`models/complaints.py:34`), no customer id. |
| `crm_sales_analysis` (`:825-856`) | `company` (not a customer); contact required | `sales/analysis.py:430` | company totals | Refuses ANY linked contact outright (`analysis.py:248-259`, scope OFF for the lookup). |
| `crm_projects_list` (`:1410-1461`) | `developer_party_ids` | `projects/projects.py:112` | `project_service.py:768` | No (a developer is a party, not a customer ledger). |

Tools with `contact_id`/`space_id` only (stock balance, low stock, portal link, ideation) carry
no customer data. No MCP tool exists for invoices, statements, credit, AR, or a customer detail
by id. `crm_order_cancel` (write, `record_actions.py:121-141`) takes any `order_id` with no
customer check but is not on the chatbot allow-list.

### 6. Precedents to reuse, not copy

- A. Lane: `lanes/business/services.py:525-577` `top_selling_dealer_ledgers` (staff = active
  office access type via `orders._top_selling_is_staff:1893-1912`; else links; else None) and
  `top_selling_dealer_customer_ids`; `engine.py:1237-1274` `_top_selling_dealer_scope` strips
  customer entities before the resolver, sets `dealer_customer_ids` or `dealer_refused`;
  refusal arm `lanes/business/__init__.py:1689-1691`, line "Sorry, I can only share sales
  figures for your own account." No escalate offer, no name oracle.
- B. Route: `orders.py:1915-1941` + `:2119-2142` (403 `customer_not_permitted`; a name that
  matches nobody gets the same 403).
- C. `sales/analysis.py:248-259`: a linked contact is refused outright (company scope OFF for
  the link lookup, security review B1: an API-key request's scope can hide the row).

### 7. The leak paths this lane closes

1. "outstanding for <other customer>" by name: resolver finds it, picker may print several
   other customers' names, report runs on it.
2. "<other customer code>": `_probe_customer` exact code match, same.
3. "status of DO <number>" belonging to another customer: `_probe_customer_order` ->
   `order_ids` -> `orders_list`, no ownership check.
4. "list outstanding DO" with no customer at all (after a carried subject, or via
   `customer_query`): every customer's rows in the company.
5. "who are your customers" -> `crm_master_customers_list`: every debtor's name.
6. "my outstanding" today: no entity, scope question or "all customers" header.

## Grill (posted as crew-ask on PR #1365)

See the PR comment; the answers are folded into "Decisions" below once they arrive.

## Decisions

(pending owner rulings)
