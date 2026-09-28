# PLAN: chatbot ETA +x days from one per-contact switch; container and quantity deniable; packing list gate on incoming

Status: IN PROGRESS - issue #1328, full track (migration), cloud lane (28 Sep 2026)
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
- All three incoming routes accept `contact_id` / `space_id` and run the same gate
  (`apply_incoming_contact_rules`).

## Migration

`eta1_0001_contact_eta_offset` on `fin_0001_billing_documents`: one
`ADD COLUMN IF NOT EXISTS`. No data change, never touches `alembic_version` by hand.
