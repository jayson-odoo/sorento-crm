# PLAN: contact <-> customer links, and a sales agent's customers from the agent side

Status: grilling (crew-ask posted 29 Sep 2026); track to be named after the answers.
Domain: sales (customer master, sales agents) + user_management (contacts).
UAC: `contact-customers-29sep-acceptance-criteria.md` alongside (written after the grill).
Lane: CONTACT-CUSTOMERS. Siblings that build on this: SALES-ASKS-TODO, CHATBOT-CUSTOMER-SCOPE.

Owner, verbatim (29 Sep 2026, follow-up from PR #1333): "i think we need a way to configure
from a contact perspective, which customer does this contact belong to? it can be multiple,
cause hanlim can have multiple hanlim, then through this linkage, we know the sales agent that
the customer is handled by, now, in customer, we have a linkage to the sales agent, but, I want
to be able to configure from sales agent perspective, who's the customer that this sales agent
handles".

## Measured facts (origin/main bc75eb96, 29 Sep 2026)

### The contact -> customers relation ALREADY EXISTS in the schema, with no route and no UI

- Table `respond_contact_customers`, model `RespondContactCustomer`
  (`sorento_crm_backend/app/models/access.py:11-64`), migration
  `alembic/versions/312_respond_contact_customers.py` (dealer-kit lane). Columns: `id`,
  `contact_id` (Text FK `respond_contacts.id` CASCADE), `customer_id` (UUID FK `customers.id`
  CASCADE), `is_primary`, `source` ('manual' default), `linked_by`, timestamps, plus
  `company_id` from `CompanyScopedMixin`. Constraints: `(contact_id, customer_id)` unique; at most
  one `is_primary` per `(contact_id, company_id)` (partial unique index). Many-to-many by design:
  the docstring at `access.py:27-29` already says "a person genuinely can be the contact for two
  accounts".
- Service `sorento_crm_backend/app/services/contact_customer_service.py`: `list_links` (:34),
  `resolve_customer` (:44, one link or the primary, else None), `link_customer` (:62, idempotent,
  demotes other primaries), `unlink_customer` (:104), `propose_customers` (:144, phone-suffix
  match over the company's customers; never writes). Tests: `tests/test_contact_customer_link.py`.
- No HTTP route calls `link_customer`, `unlink_customer` or `propose_customers` (grep over
  `app/`). Readers of the link today: top-selling dealer scope
  (`app/api/v1/order_management/orders.py:1915-1941`), the chatbot business lane
  (`app/services/chatbot/lanes/business/services.py:525-560`), and the sales analysis dealer
  refusal (`app/api/v1/sales/analysis.py:247-258`, reads the model with scope OFF).
- No frontend surface reads or writes the link (grep `contact_customer|contact-customer|
  linked_customers` over `sorento_crm_frontend/app|services|hooks`: nothing).

### Customer -> sales agent is a single FK, editable from the customer only

- `customers.sales_agent_id` FK `sales_agents.id` ON DELETE SET NULL
  (`app/models/order.py:142-146`), eager `selectin` relationship (:163), `sales_agent_code` /
  `sales_agent_name` properties (:165-180). One agent per customer (owner-confirmed 24 Sep 2026,
  `PLAN-customer-sales-agent-assignment-24sep.md`).
- Written by `CustomerService.create_customer` / `update_customer`
  (`app/services/order_service.py:3623-3642`, `:3647-3660`) through `_resolve_sales_agent`
  (`:3567`: agent must exist, be active on a genuine change, and belong to the customer's company
  or be shared). The customer import (`customer_import_service.py`) does not touch it. Routes
  `PUT /customers/{id}` (`app/api/v1/order_management/customers.py:160-165`) are gated on
  `get_current_user` only; permission gating is follow-up #1190.
- FE: `CustomerForm.tsx:234-239` has the clearable `SearchableSelect` "Sales agent";
  `useCustomerSalesAgentOptions.ts` supplies options.

### Sales agent -> its OWN WhatsApp contact is a different relation (not this lane's)

- `sales_agents.contact_id` (`app/models/sales_agent.py:96-100`) is the salesperson's own phone.
  Resolved by `app/services/sales/portal_agent.py:19 agent_for_contact` (portal debtor dropdown,
  opportunity form) and `app/services/user_contact_link.py:15-38 is_salesperson_contact`.
- On main, `app/services/portal_form_visibility_service.py:45-104` holds only market-segment
  inheritance + per-contact overrides. The "contact linked to a sales agent" gate
  (`sales_agent_for_contact`, `NOT_A_SALES_AGENT`) lives on PR #1333's branch
  (`claude/chatbot-stock-ask-v2-s4-s6-113qmf`, open draft), not on main.
- Agent routes: `app/api/v1/master_data/sales_agents.py` (list :40, get :94, PATCH annotation
  :109) under `master_data.sales_agents.view` / `.edit`. Sales agents are an AutoCount mirror,
  no create or delete (:1-16).

### Screens

- Contact detail `user-management/contacts/[id]/layout.tsx:80-104`: route tabs Profile /
  Access / Routing / Chat. Profile (`page.tsx`) is a stack of cards: Contact Information, user
  account, market segments, attachment types, portal forms, stock visibility, spec visibility.
  Permissions `user_management.contacts.view` / `.edit` (`app/rbac/permission_registry.py:45,60`).
- Sales agent detail `master-data-management/sales-agents/[id]/components/SalesAgentDetail.tsx:280-294`:
  line tabs General / Sales orders / Transfers; General holds the annotation form (person label,
  aliases, demand class, location group, contact picker at :340-389).
- Customer detail `order-management/customers/components/CustomerDetail.tsx` (+ `CustomerForm`
  on `/edit`); `customer_contacts` (`app/models/order.py:220`) is a PERSON typed in by staff
  under a customer, unrelated to WhatsApp contacts (`access.py:14-16`).

### Company scope

`customers` is company-scoped, `respond_contacts` is not; the link row carries its own
`company_id` (why it is a table, `access.py:20-25`). `sales_agents.company_id` NULL = shared.

## Relation names (for the sibling lanes)

- **Customer link** = one `respond_contact_customers` row: "this WhatsApp contact belongs to this
  customer account". Read through `contact_customer_service.list_links(db, contact_id)`.
- **Handled by** = `customers.sales_agent_id`: "this customer is handled by this sales agent".
- A contact's sales agents = the distinct `sales_agent_id` over its customer links (derived,
  never stored twice).

## Design

To be written after the grill (see the crew-ask on the PR).
