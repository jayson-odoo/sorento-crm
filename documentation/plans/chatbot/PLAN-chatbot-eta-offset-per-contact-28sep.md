# PLAN: chatbot ETA +x days from one per-contact switch; container and quantity deniable; packing list gate on incoming

Status: READY FOR CI - issue #1328, full track (migration), cloud lane, PR #1329, reviewer + security-reviewer addressed; fix round from the owner hand test (dealer ETA reply, stock vs incoming routing) built and tested, main 5b18b6d0 merged (28 Sep 2026)
Domain: chatbot / incoming stock / contacts
UAC: `chatbot-eta-offset-per-contact-28sep-acceptance-criteria.md`

## Problem (measured on main cd220251)

1. The stock ask pads the ETA with the product-or-category `chatbot_eta_offset_days`
   (`inventory_service.py:1721`, `eta_date + timedelta(days=y)`); the incoming enquiry route
   (`/api/v1/incoming-stock/list`, `/by-product`, `/shipments`) prints the exact
   `estimated_arrival_date`. One shipment, two answers, and nothing per contact decides which.
2. The Incoming Stock Enquiries reveal set (`field_access.GATED_FIELDS["incoming_stock"]`)
   has no row for the container number or the line quantity, so a dealer always sees both.
3. The incoming routes return the shipment's packing list attachment to every caller; the MCP
   presenter attaches it (`presenters._incoming_list`, `b.attach`), so the file leaves for a
   contact whose `packing_list_allowed` is off. The stock ask already gates it.

## Design

- **Switch:** `respond_contacts.chatbot_eta_offset_applied BOOLEAN NOT NULL DEFAULT true`,
  beside `notify_salesman` / `packing_list_allowed`. Those per-contact chatbot switches are
  columns, edited on the contact's Access > Chatbot card through
  `PUT /contacts/{id}/chatbot`. `contact_field_reveals` and `agent_field_access` are
  allow/deny grants over a field; the offset is a transform of a value that is already
  allowed, so it does not fit a reveal row, and the "Fields for <contact>" dialog is a per
  agent exception list, not the contact's own settings. Default true = today's stock ask.
- **Resolver:** `app/services/eta_policy.py`. `EtaPolicy.for_contact(db, internal_id)`
  reads the switch once; `offsets_for_products(db, ids)` resolves each product's
  `chatbot_eta_offset_days` through `stock_ask_limits.effective` (the existing rule);
  `policy.visible(eta, offset)` returns the padded date when the switch is on, the exact date
  when off. `apply_to_incoming(db, payload, policy)` pads every ETA-derived date on an
  incoming payload (`estimated_arrival_date`, `eta_delay_date`,
  `nearest_estimated_arrival_date`) by the largest offset among the row's products.
  No contact in play (staff console, raw API key) = exact date, unchanged.
- **Packing list:** `eta_policy.packing_list_allowed(db, internal_id)` is the one check; the
  stock ask and the incoming routes both call it; an incoming payload for a contact without
  it has `attachment` removed.
- **Deniable fields:** `shipping_container_number` ("Container number") and
  `remaining_incoming_quantity` ("Quantity") join `GATED_FIELDS["incoming_stock"]` and
  `DEFAULT_ALLOWED` (shipped allowed so deploy day changes nothing; an admin denies them on
  the agent, with per-contact exceptions). Denying quantity also strips the sibling quantity
  keys (`unallocated_quantity`, `allocated_quantity`, `total_remaining_incoming_quantity`) so
  no number leaks through a neighbour.
- All five incoming routes (`/list`, `/by-product`, `/shipments`, `/shipments/{id}/products`,
  `/shipments/{id}/attachment`) accept `contact_id` / `space_id` and run one gate
  (`incoming_stock._for_contact`). The contact is resolved ONCE per request, with the
  NULL-workspace fallback the chatbot's own access check uses, and both the ETA rules and
  the field reveals read that id. The stock ask reads its switches through the same resolver.
- **ETA windows** (`eta_from` / `eta_to`) are judged on the date the contact is told: the SQL
  lower bound widens by the largest offset any product or category carries, the widened set
  is read (up to 10 service pages of 50) and filtered on the padded date, then paged. Rows are
  re-ordered on the padded date.
- **A row naming several products** is padded by the LARGEST offset among them (`/list` asked
  for two products on one container, `/shipments`); a code carried by two companies' products
  takes the larger too. The stock ask answers one product and uses that product's own offset,
  so the two agree whenever one product is asked about. A `/shipments` row counts only its
  still-incoming lines, keyed by (company, shipment number); a row with no shipment number is
  padded by the largest offset there is.

## Fix round: owner hand test, 28 Sep 2026 (AC-EO13 to AC-EO16)

Owner, console, dealer contact: "stoick SRTWC286-SH-NEW" and "check stock SRTWC286-SH-NEW"
both answered "Here is the incoming stock I found." with the product twice. Rulings: "stock
is stock, incoming is incoming, no such thing as incoming stock"; the dealer incoming reply
"should just list deduped ETAs, and say please refer to sales person".

**Trace** (engine harness: real engine, real routes through TestClient, real MCP presenter,
parser verdict stubbed; `tests/chatbot/test_dealer_eta_stock_routing.py`). A clean stock
reading (`domain_hint: inventory`) reached the stock tool on this branch and on main. After
an incoming turn, a message the parser gives no domain ("stoick", a typo) or reads as
`incoming` against the carried focus inherits `incoming`, and nothing read the customer's
own stock word, so the stock ask ran `crm_incoming_stock_list`. Not caused by this PR (it
touched no routing) nor by the availability policy. The product printed twice because two
still-incoming lines share one ETA and the container and quantities that told them apart
are withheld from the contact.

- **Routing** (`app/services/chatbot/domain_words.py`, called in `engine._run_stages`
  after `order_list_verdict`, before `apply()`): a stock word (the inventory row's own
  `switch_words`, plus a one-slip typo of "stock": an extra, missing or swapped letter,
  never a changed one, so "stick" and "stack" stay words) and no incoming word turns an
  incoming or domain-less reading into the stock domain; a quantity with no incoming word
  does the same over a turn that would land on incoming; an incoming word and no stock
  word turns a stock reading into incoming; both words keep the parser's reading; any
  other domain is never touched. Recorded on the trace as `domain_words`.
- **Dealer reply** (`eta_policy.dealer_view`, applied last in `incoming_stock._for_contact`
  when `eta_policy.is_dealer`, the availability-policy test the chatbot profile uses): one
  row per product, `{product_code, etas}`, the ETAs distinct and sorted, padded by the
  offset rule, the revised ETA used when the contact may see one; plus
  `salesperson_name` (the sales agent on the contact's customer, primary link first).
  No container, quantity, allocation or packing list. The presenter
  (`presenters._incoming_dealer`) prints "<code>" and "ETA: <dates>" per product and
  `closing` "Please refer to your salesperson, <name>." (no name: "Please refer to your
  salesperson."); the engine prints it with no intro and no numbering, and the zero-stock
  ladder stands down for it as it does for an availability reply.
- **Identical rows**: `presenters._without_repeats` drops an incoming line that reads
  exactly like an earlier one, for any contact whose reveals leave two lines identical.
- Staff and non-dealer contacts keep today's full reply. A staff stock miss still climbs
  the zero-stock ladder to incoming under the stock answer (prod parity, 21 Sep ruling).
- Not changed here: a dealer's incoming MISS still offers the purchasing team; the
  "refer to your salesman" rule of 26 Sep covers the stock ask only.

## Behaviour changes on deploy (stated, not hidden)

- A contact that resolves to nobody (wrong `space_id`, unknown id) on `/by-product` and
  `/shipments` now gets every gated field withheld (ETA, container, quantity) and no packing
  list - fail closed, the rule `/list` already followed. Before, those two routes returned the
  whole payload for any `contact_id`.
- Contacts that DO resolve see no change on container and quantity (shipped allowed) and see
  the padded ETA on incoming (the switch defaults on, matching the stock ask).

## Out of scope (named so it is not assumed covered)

- The outstanding / order reports that print container numbers or incoming quantities
  (`sorento_crm_mcp/catalog.py` outstanding report) do not read the new incoming reveals.
- The Container Status workbook carries the raw ETA; it is `sorento_office` only.
- A contact can still confirm a guessed container number by searching for it on `/list` /
  `/shipments` `query`; the MCP tool specs do not expose `query` to the chatbot.

## Migration

`eta1_0001_contact_eta_offset`: one `ADD COLUMN IF NOT EXISTS`. Its `down_revision` is
BOTH of main's heads at merge time (`chatbot_esc_confirm_1323`, `fin_0002_billing_demand_class`,
both children of `fin_0001_billing_documents`), so it is also their merge point and the tree
has one head. No data change, never touches `alembic_version` by hand.
