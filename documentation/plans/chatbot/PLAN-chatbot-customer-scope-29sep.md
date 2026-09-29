# PLAN - Chatbot: a linked contact is scoped to its customers; "my" / "me" means them

Status: in build (29 Sep 2026; crew lane CHATBOT-CUSTOMER-SCOPE, PR #1365). Owner rulings received 29 Sep, all eight as recommended; see Decisions. Standard track:
this is an authorization boundary (security-reviewer runs). UAC:
`chatbot-customer-scope-29sep-acceptance-criteria.md` (written under the recommended options).

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
- Adding a key: `head/parser.py:422-467` (schema), `head/parser.py::TOLERATED_ABSENT:501`, and a
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

Owner rulings, 29 Sep 2026 (relayed by crew on PR #1365), every one the recommended option.
Verbatim: "Q1 (a) reuse the top-selling rule: office access type = staff sees all; linked
non-staff scoped to links. Q2 (a) a contact with NO link keeps today's behaviour, can ask
about any customer (reveal grants stay the gate). Q3 (a) both layers: engine before resolver
+ routes force/403. Q4 (a) other customer's DO/SO number reads as an ordinary miss. Q5 (a)
parser emits self_reference (my/me/our, incl. Malay/Chinese); engine substitutes linked
customers, linked staff included. Q6 (a) answer across ALL linked customers. Q7 (b) 'Sorry,
that isn't under your account. I can only check on <own linked customers>.' Q8 (a) all
customer-scoped tools incl. debtors, analytics, complaints (filter by linked names)."

| Q | Ruled | What it fixes in the design |
| --- | --- | --- |
| Q1 | (a) the shipped top selling rule: active office type = staff; else links = scoped | one function, `contact_customer_scope.py` |
| Q2 | (a) unlinked contact unchanged | `scope.enforced` false when no links |
| Q3 | (a) engine before the resolver + the routes | `engine._customer_scope_gate` + route checks |
| Q4 | (a) a foreign DO number is a miss inside the scope | routes AND the links onto `order_ids` |
| Q5 | (a) `self_reference` substitutes the links for anyone linked, staff included | `scope.linked` read even when not enforced |
| Q6 | (a) several links = all of them, `is_primary` unread | no picker of own customers |
| Q7 | (b) refusal names the linked customers | `REFUSED_OTHER_CUSTOMER(names)` |
| Q8 | (a) every customer-scoped tool, complaints included (filtered by the linked customers' names) | `fetch.CUSTOMER_SCOPED_TOOLS` pinned to the catalogue; complaints list route gains the contact filter (D5) |

## Design

### D1. One "who is scoped" function (core, importable by routes and lane)

`app/services/contact_customer_scope.py` (new):

```python
@dataclass(frozen=True)
class ContactCustomerScope:
    linked: tuple[tuple[str, str], ...]   # (customer_id, customer_name), link order, every company
    staff: bool                           # an ACTIVE office access type (the top selling rule)
    @property
    def enforced(self) -> bool: return bool(self.linked) and not self.staff
    @property
    def customer_ids(self) -> list[str]: ...
    def match_words(self, words: list[str]) -> list[str] | None:
        # each word: exact customer_code (case-insensitive) or a case-insensitive substring of
        # customer_name, over `linked` only; None when ANY word matches none (refuse)

def contact_customer_scope(db, contact_id: str) -> ContactCustomerScope
def is_office_staff(db, contact_id: str) -> bool   # moved from orders._top_selling_is_staff
def refusal_line(scope) -> str  # "Sorry, that isn't under your account. I can only check on A and B."
```

`contact_id` is the INTERNAL `respond_contacts.id`; callers resolve a Respond.io id through
`field_access.resolve_contact_with_null_workspace_fallback` first (the lane and the routes
both already do). The link read runs under `company_scope(db, None)` (precedent C, AC-CS-46)
and the names come from `Customer` under the same off-scope read. `orders._top_selling_is_staff`
becomes a one-line alias of `is_office_staff`; `orders._top_selling_dealer_scope` keeps its
fail-closed contract but reads `contact_customer_scope`. `business_services.top_selling_dealer_ledgers`
reads it too (returns `scope.linked` or None).

### D2. Parser: `self_reference`

- `head/parser.py` schema: `"self_reference": {"type": "boolean"}` beside `correction`;
  `head/parser.TOLERATED_ABSENT` gains it; `DECLARED_KEYS` follows the schema.
- Prompt: a new trailing addendum `SELF_REFERENCE_ADDENDUM` in `chatbot_parser_prompt.py`,
  appended to `SEMANTIC_PARSER_PROMPT` the way `TOP_SELLING_ADDENDUM` is, teaching the key
  (AC-CS-20 wording), with the "we / us = the company" rule narrowed: "we" as the asker's
  business ("what did we order") is `self_reference: true`; "do you / can you" about Sorento
  stays the company rule.
- Migration `alembic/versions/chatbot_self_reference_vocab.py`, `down_revision` = main's head
  at merge time (`scripts/alembic-reparent.sh`), publishing a new version, label unmoved.
- The prompt tail pins (`tests/chatbot/test_parser_prompt_tail*.py` or equivalent, whichever
  files pin the newest addendum) are updated for the new tail.

### D3. Engine: the upstream gate (before `resolve_kinds`)

`engine.py`, at the seam `:3199-3209`, a new `_customer_scope_gate(db, resolver_parse_output,
verdict, state_out.focus, ctx, contact_respond_id, space_id_for_turn, plan)`:

1. Read `scope = business_services.customer_scope(db, contact_respond_id, space_id)` once per
   turn (memoised on `ctx["customer_scope"]` = `{"ids": [...], "names": {...}, "enforced": bool,
   "linked": bool}`; None when unlinked).
2. Runs only when the plan touches a customer-scoped domain (`"order" in plan.domains`) or the
   verdict has `self_reference: true`; otherwise returns the input untouched.
3. `self_reference: true` and `scope.linked`: `focus.customers` = the linked rows
   (`{"uuid", "canonical_code": name, "name", "hint": "customer", "current_message": True,
   "scope": True}`); customer entities in the message are matched with `match_words`; a match
   narrows `focus.customers` to the matches; no match -> refuse (step 5).
4. `scope.enforced` and no self reference: customer entities matched with `match_words`
   (matches -> `focus.customers`, resolver never sees them); no customer entity ->
   `focus.customers` = the links (so the gate's `ALLOWS_EMPTY["order"] = False` is satisfied
   by the scope and the fetch has its subject).
5. Refuse: `focus.customer_scope_refused = True` (a Focus field, cleared on every turn); the
   business lane's tool pick (`lanes/business/__init__.py` beside the `dealer_refused` arm at
   `:1689`) returns `_fixed_reply(refusal_line)` before any tool; trace
   `customer_scope: {"refused": "customer_not_permitted"}`. No open question armed, no offer.
6. The header line (`tail/scope_block.py`) reads the scoped customers off `focus.customers`
   as it does today, so the reply says `Customer: HANLIM TRADING`.

Top selling keeps its own `_top_selling_dealer_scope` (it runs first and strips its customer
words); the general gate is a no-op on a turn whose customer entities are already gone.

### D4. Fetch: the defensive layer in the lane

- `lanes/business/__init__.py::_fetch_semantic_input` gains `scope_customer_ids`
  (`ctx["customer_scope"]["ids"]` when `enforced`, else absent).
- `fetch.py`: `CUSTOMER_SCOPED_TOOLS = frozenset({crm_order_management_orders_list,
  crm_order_management_orders_by_product_list, crm_outstanding_report, crm_sales_report,
  crm_top_selling_report, crm_order_analytics, crm_master_customers_list})`, pinned by a test
  against every catalogue `ToolSpec` whose `query_params` carry `customer_ids` (AC-CS-32).
- `entity_ids_transformer`, last step before `contact_id`: when `scope_customer_ids` is
  present and the tool is in the set: no `customer_ids` -> the scope; a subset -> kept; any id
  outside -> raise `ScopeViolation` (a `ToolNotAllowed` sibling, caught by `run_fetch` into the
  refusal reply, never a tool call); `customer_query` popped.
- `crm_complaints_list` is not on the chatbot's tool pool (`gate.ALLOWED` has no complaints
  domain), so the lane has nothing to force; the ROUTE carries the filter (D5, owner Q8).

### D5. Routes: the defensive layer behind the MCP

A shared helper `app/api/v1/order_management/_contact_scope.py::enforce_customer_scope(db,
contact_id, space_id, customer_ids, customer_query) -> list[str] | None`: both-or-neither
422 `contact_identity_required` (the sales report's rule); resolve the contact; `scope =
contact_customer_scope(...)`; not enforced -> None (caller unchanged); enforced: ids outside ->
403 `customer_not_permitted` ("You can only see orders for your own account."); a
`customer_query` matched inside the links only (none -> the same 403); return the effective
ids (requested subset, or the links). Applied to: orders list (`orders.py:303`), by-product
(`:740`), outstanding report (`:1454`, gains the two params), sales report (`:1659`, replacing
its own contact block's customer part), debtors (`:653`), analytics (`:942`). `order_ids`
stays as given: the customer filter ANDs onto it, so a foreign number returns no rows (Q4a).
Top selling keeps its own block (already equivalent).

Complaints (owner Q8): `GET /complaints-management/complaints/` (`complaints.py:220`) gains
`contact_id` / `space_id` (both-or-neither, 422 `contact_identity_required`); for a scoped
contact the rows are filtered to `lower(btrim(Complaint.customer_name)) IN (the linked
customers' names, lowered and trimmed)`. Complaints carry `customer_name` text only
(`models/complaints.py:34`), so the name is the join; a complaint filed under a misspelt
name is simply not shown to the contact (fail closed).

### D6. Tests (Phase 2, tester before coder)

- `tests/chatbot/test_customer_scope_lane.py`: AC-CS-01 to 05, 10 to 15, 22 to 26, 30, 33,
  34 through the `test_outstanding_lane._run_turn` harness (parser faked with
  `self_reference` in the verdict, links seeded by SQL like `test_top_selling_lane.TestDealer.
  _link_dealer`, office type by `_give_access_type`).
- `tests/chatbot/test_customer_scope_fetch.py`: AC-CS-31, 32 (transformer unit + catalogue pin).
- `tests/chatbot/test_customer_scope_parser.py`: AC-CS-20, 21 (schema, TOLERATED_ABSENT,
  prompt text, migration publish idempotent with label unmoved).
- `tests/test_customer_scope_routes.py`: AC-CS-40 to 47 through `TestClient` with the
  `test_top_selling_report.py` fixtures (`_contact`, `_link`, `_access`, `_as_contact`).
- `tests/chatbot/console_cases/2026-09-29-customer-scope.yaml`: AC-CS-50.

### Review round 1 (29 Sep 2026, reviewer + security-reviewer, both Opus)

Both reviewers reproduced their findings against real code and Postgres; the kill tests on
AC-CS-10 / 31 / 40 went red with the code removed. Fixed in fix round 1 (red tests first):
a refused turn kept the foreign word on `focus.customers` and refused every later turn; a
customer word tagged brand / category / order / product by the parser (`entity_resolver.
_DOMAIN_HINT_EXPANSIONS["order"]`), or asked under `purchase_order`, still reached the
resolver's picker (name oracle), so the scope is now ALSO applied after the resolver,
domain-independent; the order routes' legacy `debtor_name` OR let a same-named ledger's DOs
through (the name branch now applies to `customer_id IS NULL` rows only); a space-padded
`contact_id` turned the customer scope off while the company scope stayed on (stripped at
the three scope call sites); sales report's subject check ran before the scope; a foreign DO
number could print the other customer's name on the resolver-echo miss path; a fan-out
refused twice; the orders list `entities=` echo; own customer code via `customer_query`.

Known limitations, recorded and not built:

- **The route defence is opt-in by the caller.** A direct MCP or n8n call that omits
  `contact_id` + `space_id` stays company-scoped (AC-F1, the standing X-API-Key rule), as
  before this lane. Trigger to revisit: making the contact pair mandatory on the
  customer-scoped catalogue tools in `sorento_crm_mcp/server.py`, once every n8n caller sends
  it.
- **Complaints are joined on name.** Complaints carry `customer_name` text only, so a
  complaint filed under another customer sharing the linked name is shown; a name that differs
  by spelling is hidden (fails closed). Needs a customer id on complaints to do better.
- **A lone `contact_id` or `space_id` is 422** on orders list, by-product, debtors, analytics
  and the outstanding report (the sales report's shipped rule, now shared). The lane always
  sends both, non-blank.

### Not built (named triggers)

- A picker of the contact's own customers (Q6b) - built if the owner rules (b).
- Fail-closed for unlinked contacts (Q2b) - flip `enforced` to `not staff` once linking is
  backfilled; the owner's call.
- Complaints scoping in the LANE - when a complaints domain joins the chatbot tool pool
  (the route filter ships now, owner Q8).
