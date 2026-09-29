# UAC - Chatbot: a linked contact is scoped to its customers; "my" / "me" means them

Plan: `PLAN-chatbot-customer-scope-29sep.md`. Crew lane CHATBOT-CUSTOMER-SCOPE, PR #1365.
Written under the grill's RECOMMENDED options (Q1a, Q2a, Q3a, Q4a, Q5a, Q6a, Q7b, Q8a); an
owner ruling that differs changes the AC it names and nothing else.

## Journey

A dealer's purchaser (a WhatsApp contact whom CS has linked to the dealer's customer account,
`respond_contact_customers`) asks the bot about orders. Nothing on their side changes: they
type "what's my outstanding", "DO status", "outstanding for <their own account>", "status of
DO 12345". The bot answers about THEIR account only. They never see another customer's name,
figure or document, and they never have to say which account they are, because the link
already says so. If they name someone else's account, the bot says in one line that it can
only check on theirs, and names theirs so they know what to ask instead.

A Sorento / Mocha / Cabana office member (a contact holding an active office access type)
notices nothing: every ask works as today, across every customer, and "my" still means their
own linked account if they have one.

A contact nobody has linked yet notices nothing either: today's behaviour, gated by the field
reveal grants, until CS links them.

Vocabulary: "scoped contact" = a contact with at least one `respond_contact_customers` row and
no ACTIVE office access type (`orders._top_selling_is_staff`, shared). "Linked customers" = the
customer ids on its rows, every company, in link order. "Customer-scoped tool" = an MCP tool
that takes `customer_ids` and returns per-customer data (census in the plan, section 5).

## Phase 2 - backend (there is no screen in this lane)

### Who is scoped (Q1a, Q2a)

- **AC-CS-01** `[BE]` Given a contact with one link and no office access type, when any
  customer-scoped ask runs, then the turn is scoped to that customer id.
- **AC-CS-02** `[BE]` Given a contact holding an ACTIVE "Sorento Office" (or Mocha / Cabana
  Office) access type, whatever links or other types it holds, when it names another customer,
  then the ask runs exactly as today (generic resolver, picker on ambiguity, the named
  customer's figures), no refusal.
- **AC-CS-03** `[BE]` Given a contact with NO link and no office type, when it names a customer
  or asks a bare order question, then the turn runs exactly as today (no forced customer ids,
  no refusal, the reveal grants stay the gate).
- **AC-CS-04** `[BE]` Given a contact whose only office type is INACTIVE and one link, then it
  is scoped (an inactive office type is no office type).
- **AC-CS-05** `[BE]` The lane and the routes decide "scoped" through ONE function
  (`app/services/contact_customer_scope.py`), and `orders._top_selling_dealer_scope` calls it
  too; the existing top selling tests stay green unchanged.

### Upstream block, before the resolver (Q3a, Q7b)

- **AC-CS-10** `[BE]` Given a scoped contact, when the message carries a customer-hint entity
  whose words match none of the linked customers (name substring, case-insensitive, or exact
  customer code), then the reply is the refusal line, the generic resolver is NEVER asked
  about that token, no picker is shown, and no MCP tool is called.
- **AC-CS-11** `[BE]` The refusal line is `Sorry, that isn't under your account. I can only
  check on <A>.` for one link and `... check on <A> and <B>.` for two, `<A>, <B> and <C>.`
  for three or more, where the names are the linked customers' `customer_name` in link order.
  No escalate offer follows it, and no open question is armed.
- **AC-CS-12** `[BE]` Given a scoped contact, when the customer word matches one of its linked
  customers ("outstanding for hanlim" with HANLIM TRADING linked), then the fetch runs with
  `customer_ids == [that id]` and no picker, even when the word would match other customers
  in the book.
- **AC-CS-13** `[BE]` Given a scoped contact with two links and a word matching both, then
  `customer_ids` is both ids, no picker.
- **AC-CS-14** `[BE]` Given a scoped contact, when the message names a customer by exact
  `customer_code` that belongs to someone else, then AC-CS-10 applies (a code is a customer
  word).
- **AC-CS-15** `[BE]` Given a scoped contact, when the message carries a DO / SO / order
  number entity (hint `order` / `customer_order` / `order_number`) that resolves to an order
  uuid, then the orders list tool is called with that `order_ids` AND `customer_ids` set to
  the linked customers, and the reply is the ordinary miss text when the order belongs to
  another customer (the route returns no rows). The refusal line is never shown for a number.

### Self-reference (Q5a, Q6a)

- **AC-CS-20** `[BE]` The parser's strict schema has a boolean key `self_reference`, listed
  in `contracts.TOLERATED_ABSENT` (an older prompt version omits it), and the prompt teaches
  it: "my", "mine", "me", "our", "us" (as the asker's own account, not the company),
  "saya punya", "kami punya", "我的", "我们的" -> `self_reference: true`; a message naming
  another party or none -> false. "where is my shipment" (ETA) stays the ETA rule AND
  `self_reference: true`.
- **AC-CS-21** `[BE]` A migration publishes the prompt with the new key as a new version, the
  `production` label unmoved (idempotent, same helper shape as `chatbot_top_selling_vocab`).
- **AC-CS-22** `[BE]` Given a contact with one link, when the verdict has
  `self_reference: true`, `order_status: "outstanding"` and no entities, then
  `crm_outstanding_report` is called with `customer_ids == [the link]`, no scope question
  ("which customer / product?") is asked, and the reply's Customer line names that customer.
- **AC-CS-23** `[BE]` Given a contact with two links, when `self_reference: true`, then
  `customer_ids` is both ids in link order, no picker, `is_primary` not consulted.
- **AC-CS-24** `[BE]` Given a contact with no link (staff or not), when `self_reference: true`,
  then the key is ignored and the turn runs exactly as today.
- **AC-CS-25** `[BE]` Given an office (staff) contact WITH a link, when `self_reference: true`,
  then `customer_ids` is its links (staff are unscoped otherwise, AC-CS-02).
- **AC-CS-26** `[BE]` Given a scoped contact, when `self_reference: true` AND the message
  names one of its own customers, then that customer alone is the subject; when it names
  another customer, AC-CS-10 applies.

### Every customer-scoped fetch is forced to the links (Q3a, Q8a)

- **AC-CS-30** `[BE]` Given a scoped contact, when an order-domain ask names no customer at
  all ("list outstanding DO", "orders in September"), then the fetch runs with
  `customer_ids == links`, and the "which customer / product?" scope question is NOT asked
  (the link is the subject).
- **AC-CS-31** `[BE]` `fetch.entity_ids_transformer`, given `semantic_input.scope_customer_ids`,
  forces `customer_ids` on every tool in `fetch.CUSTOMER_SCOPED_TOOLS` (orders list, orders by
  product, outstanding report, sales report, top selling, order analytics, debtors list):
  none requested -> the scope; a subset requested -> that subset; any requested id outside
  the scope -> `ScopeViolation` raised (no call). `customer_query` is never sent for a scoped
  contact. Tools outside that set are untouched.
- **AC-CS-32** `[BE]` `fetch.CUSTOMER_SCOPED_TOOLS` is pinned against the MCP catalogue: every
  catalogue tool whose `query_params` carry `customer_ids` is in the set (a new tool taking
  customer ids fails this test until it is classified).
- **AC-CS-33** `[BE]` Given a scoped contact, when it asks for the sales report of another
  customer, then AC-CS-10; for its own, `crm_sales_report` runs with its id.
- **AC-CS-34** `[BE]` A broaden to "all customers" (`broaden_axis: customer, broaden_to: all`)
  from a scoped contact leaves `customer_ids == links` on the next fetch.

### Route-level defence (Q3a, Q4a), only when `contact_id` + `space_id` are sent

- **AC-CS-40** `[BE]` `GET /order-management/orders/` with a scoped contact and `customer_ids`
  containing an id outside its links -> 403 `customer_not_permitted`; with none -> only rows
  of the linked customers (a seeded other customer's DO is absent); with `order_ids` of
  another customer's order -> 200 and empty `data`.
- **AC-CS-41** `[BE]` `GET /order-management/outstanding-report` gains `contact_id` /
  `space_id` params (both-or-neither, 422 `contact_identity_required` on one alone, the sales
  report's rule) and applies the same three rules as AC-CS-40; `customer_query` from a scoped
  contact is matched inside its links only and 403s when it matches none (no name oracle).
- **AC-CS-42** `[BE]` `GET /order-management/sales-report`: same rules as AC-CS-41.
- **AC-CS-43** `[BE]` `GET /order-management/orders/debtors` (customers list) with a scoped
  contact returns only the linked customers.
- **AC-CS-44** `[BE]` `GET /order-management/orders/analytics` and `/orders/by-product`: other
  ids -> 403; none -> forced to the links.
- **AC-CS-45** `[BE]` A staff contact (active office type) and a request with no contact
  identity are unchanged on every route above (no 403, no forcing).
- **AC-CS-46** `[BE]` The link lookup on the routes reads with company scope OFF (the sales
  analysis precedent: an API-key request's scope can hide the row for a NULL-workspace
  contact), so a scoped contact is never let through by a hidden link.

### Console cases

- **AC-CS-50** `[T]` `tests/chatbot/console_cases/2026-09-29-customer-scope.yaml` carries the
  leak attempts (other customer by name, by code, by DO number; "my" with 0 / 1 / 2 links;
  staff naming another customer) for the live parser, graded on `reply_contains` and
  `expect.parser.self_reference`. It cannot run in the cloud sandbox (no LLM key); it runs on
  the owner's stack and after deploy.
