# PLAN: contact <-> customer links, and a sales agent's customers from the agent side

Status: built, review passed, hand test pending (29 Sep 2026); full track, no migration. PR #1366. Evidence: `evidence/contact-customers/evidence-run.md`.
Domain: sales (customer master, sales agents) + user_management (contacts).
UAC: `contact-customers-29sep-acceptance-criteria.md` alongside.
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
- PR #1333 merged on 29 Sep 2026 (f4f70531, joined by #1367): `app/services/
  portal_form_visibility_service.py:106` now gates the portal `customer_asks` kind on
  `price_tag_request_service.sales_agent_for_contact` (`:109`), which resolves the agent whose
  OWN contact this is (`sales_agents.contact_id`). Unrelated to the customer link.
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

## Journey

**Contact side.** A CS admin opens a WhatsApp contact (Internal Users > Contacts > a row). The
Profile tab shows, under Contact Information, a "Customers" card: the customer accounts this
phone number belongs to, each with the sales agent handling that account. The admin picks a
customer in one searchable select ("Add customer"; the option shows the customer's current
agent), and the row appears. If the contact belongs to several accounts, one click marks the
one a quote defaults to as Primary. Unlink is a countdown, not a dialog. Below the linked
rows the card offers up to five phone-matched customers as "Suggested", each with a one-click
Link; nothing is linked until a human clicks. Nobody else is told anything.

**Agent side.** A sales admin opens a sales agent (Master Data > Sales Agents > a row). A new
"Customers" line tab lists the customers this agent handles (the customers whose
`sales_agent_id` is this agent), searchable, paged. "Assign customer" is one searchable select
(the option shows the customer's current agent, if any); picking moves the customer to this
agent. Unassign per row is a countdown. The customer form's own "Sales agent" field keeps
working; both sides write the same column.

Decisions the user makes: which customer (once per link), primary or not (optional). Nothing
else is asked; the agent behind a customer is derived, never typed.

## Round 2 (owner rulings, 29 Sep 2026, relayed by crew on PR #1366)

- Q1 (a): reuse `respond_contact_customers`. Q3 (a): Customers card on the contact Profile tab.
  Q5 (a): Customers tab on the sales agent record with Assign / Unassign. Q6 (a): reassigning a
  customer another agent handles is allowed, the picker shows the current agent. Q7 (a): each
  page's own edit permission.
- Q2 (b), answered later on 29 Sep: NO primary customer in the UI. This lane neither shows
  nor sets `is_primary` anywhere: the PATCH route, `set_primary`, the `is_primary` body field
  on POST, the FE hook/service for it and the AC-24 tests are removed; the link responses do
  not carry `is_primary`. The existing column and the dealer kit's use of it
  (`resolve_customer`, `link_customer(is_primary=...)`, `_demote_other_primaries`) stay
  untouched: no schema change, no data change.
- Q4: NO suggestions. The owner links by clicking the Add customer select only: no phone-match
  rows, no backfill. `propose_customers` stays where it was (dealer kit), unused here; the GET
  no longer returns `suggested` (D2 amended), the card has no Suggested list (D3 amended),
  AC-6 and AC-21 are withdrawn.
- Q8 (b): ADD a read-only list of linked WhatsApp contacts on the customer detail page (D5).

## Design (round 2)

Track: **full, no migration**. No schema change: the link table and the FK exist. No new
permission slug. Security-reviewer runs (multi-company scoping of the link rows).

### D1 Relation and seams for the sibling lanes

- Customer link = `RespondContactCustomer` row. `contact_customer_service.list_links(db,
  contact_id)` is the read the sibling lanes use (CHATBOT-CUSTOMER-SCOPE: the contact may only
  query these `customer_id`s).
- New `contact_customer_service.agents_for_contact(db, contact_id) -> list[SalesAgent]`:
  distinct agents over the contact's links, ordered by agent code (SALES-ASKS-TODO: whose
  to-do a contact's ask lands on). Derived, never stored.
- Repair inside the lane: `link_customer` must stamp `company_id` from the CUSTOMER
  (`Customer.company_id`), because `before_insert` (`app/services/company_scope.py:301-326`)
  raises on an owned insert under a multi-company scope and leaves an already-set value alone.
  Today the function never sets it, so a staff user scoped to two companies cannot link at
  all. `propose_customers` and `list_links` run under the caller's scope unchanged.

### D2 Backend routes

Contact side, in `app/api/v1/user_management/contacts.py` (same file as the other per-contact
sections), read under `user_management.contacts.view`, write under `.edit`:

- `GET /api/v1/user-management/contacts/{contact_id}/customers` ->
  `{ "data": [ContactCustomerLink] }` (round 2: no `suggested`, Q4).
  `ContactCustomerLink`: `id` (the link row, what Unlink parks against), `customer_id,
  customer_code, customer_name, is_active, source, sales_agent_id, sales_agent_code,
  sales_agent_name, created_at` (round 2: no `is_primary`, Q2 b).
- `POST .../customers` body `{ "customer_id": str }` -> 201 `ContactCustomerLink`. Idempotent
  on the pair (a repeat answers 201 with the same row; a concurrent duplicate insert is
  caught and re-read, reviewer nit 6). Round 2: no `is_primary` (Q2 b).
  Unknown customer or a customer outside the caller's scope -> 404 (scope hides it, so the
  two are the same answer). Unknown contact -> 404.
- (Round 2, Q2 b: the PATCH `is_primary` route is removed.)
- Unlink: pending action `contact_customer_link.unlink`, `entity_types=("contact_customer_link",)`,
  `entity_id` = the LINK row id, `window=WINDOW_REVERSIBLE`, `permission=
  "user_management.contacts.edit"`, execute = `unlink_customer` by link id. No separate DELETE
  route: nothing would call it (the button parks the action). Registered in
  `app/services/record_actions.py` beside the spec-visibility remove.

Agent side, in `app/api/v1/master_data/sales_agents.py`, read under
`master_data.sales_agents.view`, write under `.edit`:

- `GET /api/v1/master-data/sales-agents/{id}/customers?page&limit&query&sort&dir` ->
  `ListResponse[CustomerResponse]` (customers whose `sales_agent_id` is this agent, under the
  caller's scope; `query` matches code or name; default sort `customer_code asc`).
  `CustomerResponse` gains `region` and `market_segment_code` (model columns that exist,
  `order.py:125,128`, never declared on the schema; `response_model` drops what a schema does
  not name, so the tab's two columns need them declared). Additive for every other caller.
- `POST .../customers` body `{ "customer_id": str }` -> 200 `CustomerResponse`. Calls
  `CustomerService.update_customer(customer_id, CustomerUpdate(sales_agent_id=agent.id))`, so
  an inactive agent or a cross-company pair is the same 422 the customer form gets, and the
  customer audit row (`sales_agent_id` joins `Customer.__audit_columns__`, `order.py:69-92`; it is not audited today) is written the
  same way. Reassignment from another agent is allowed (Q6a).
- Unassign: pending action `customer.unassign_sales_agent`, `entity_types=("customer",)`,
  `entity_id` = customer id, payload `{ "sales_agent_id": <agent> }`, `window=
  WINDOW_REVERSIBLE`, `permission="master_data.sales_agents.edit"`. Execute clears
  `customers.sales_agent_id` only while it still equals the payload's agent (a customer moved
  to another agent during the window is left alone).
- `GET /api/v1/order-management/customers/select` (`customers_select.py:19`) additionally
  returns `sales_agent_id, sales_agent_code, sales_agent_name` per row (additive; the
  relationship is already `selectin`, so no per-row query). Both pickers read this select.

### D3 Frontend

Contact side (`app/(protected)/user-management/contacts/[id]/`):

- `components/ContactCustomersSection.tsx`: a Card "Customers" placed directly after the
  Contact Information card on `page.tsx`. Body: rows `code - name` | `Sales agent` (`code -
  name`, or "No sales agent") | Unlink (row action, `useDeferredRowAction`, `surface:
  'inline'`, verb "Unlinking"). Round 2: no Primary badge or Make/Clear primary (Q2 b); no
  Suggested list (Q4). Empty state: heading "No customers linked" + hint "Link
  the customer accounts this contact belongs to". "Add customer": one `SearchableSelect`
  (clearable, server search through the customers select with `limit=50`, option label
  `code - name`, sub-label the current agent), adding on pick.
- `services/contactCustomersService.ts` (contract at the top of the file), `hooks/
  useContactCustomers.ts` (`useContactCustomers`, `useLinkContactCustomer`,
  `useSetContactCustomerPrimary`; invalidate `['contact-customers', contactId]` + toast).
- Layout at 375px: rows wrap to two lines (name on the first, agent + actions on the
  second); the select is full width.

Agent side (`app/(protected)/master-data-management/sales-agents/[id]/components/`):

- `SalesAgentCustomersTab.tsx`: a fourth line tab "Customers" after Transfers in
  `SalesAgentDetail.tsx:280-294`. Toolbar: search + "Assign customer" `SearchableSelect`
  (same select source, option sub-label the current agent). `DataGrid` (`tableLayout:
  { width: 'fixed', columnsResizable: true }`, `columnResizeMode: 'onChange'`, explicit
  `size` per column, `truncate` + `title`): Code, Name, Region, Market segment, Status
  (`Badge`), Unassign (row action, toast surface, verb "Unassigning"). `rowHref` to the
  customer detail. Empty state: heading "No customers assigned" + hint "Assign the customers
  this agent handles".
- `services/salesAgentService.ts` gains `getSalesAgentCustomers` (via `buildDataGridParams`)
  and `assignSalesAgentCustomer`; `hooks/useSalesAgents.ts` gains `useSalesAgentCustomers`
  and `useAssignSalesAgentCustomer`.
- Customer picker options: one new `searchCustomersSelect(query, pageIndex)` in
  `order-management/customers/services/customerService.ts` (server-searched, `limit=50`,
  `offset`, value = customer id, label `code - name`, `description` = the current agent
  `code - name` or "No sales agent"), used by BOTH pickers through `SearchableSelect`'s
  `fetchOptions` + `paginated`. The two existing callers of the select
  (`order-management/shared/hooks/use-customer-select-query.ts`, whole list, value = id;
  `scm/services/scmOptionsService.ts:86 searchCustomerOptions`, value = customer CODE) fit
  neither surface: the first pulls 6,397 rows, the second addresses by code and a code is
  not unique. Not a third copy of the same thing: a different key.

No new motion: countdowns use the existing `DeferredCountdown`; nothing else animates.

### D4 Out of scope

Permission gating of the customer PUT (#1190); backfill of phone matches (Q4, refused); the
portal and chatbot readers (sibling lanes); the Primary marker in the UI (Q2 pending).

### D5 Customer detail: linked WhatsApp contacts (round 2, Q8 b)

- `GET /api/v1/order-management/customers/{customer_id}/linked-contacts` under
  `order_management.customers.view` -> `{ "data": [{ "id" (link id), "contact_id", "name",
  "phone_number", "created_at" }] }` (no `is_primary`, Q2 b), ordered by `created_at`; the customer is
  read under the caller's scope (404 when hidden or unknown). Read-only: no write route.
- `order-management/customers/components/CustomerLinkedContactsSection.tsx`, rendered on the
  customer detail Details tab (`CustomerDetail.tsx`, after the existing cards, before
  Opportunities). Rows: name (or the phone number when the contact has no name), phone,
  linked date; the name links to `/user-management/contacts/{contact_id}` (the UI shows the
  name, never the id). Empty state: heading "No WhatsApp contacts linked" + hint "Link this
  customer from a contact's Customers card". Service `getCustomerLinkedContacts` in
  `customerService.ts`, hook `useCustomerLinkedContacts` in `useCustomers.ts`.
- Reviewer findings carried into the same round: unassign and unlink share one rule, a
  record that is gone or moved during the window ends the action `failed` with a readable
  message, never `committed` (nit 5); a concurrent duplicate link insert is caught on
  `IntegrityError` and the existing row returned (nit 6); assign/unassign invalidate the
  `['sales-agent-customers']` prefix and the customer detail query (nit 7); `link_customer`
  takes the customer the route already loaded (nit 9).
- Security review nits carried into the same round: the unlink handler raises not-found for
  a link the caller cannot see (the action is marked failed, not committed); parking
  `contact_customer_link.unlink` or `customer.unassign_sales_agent` checks the record exists
  under the caller's scope and refuses with 404 otherwise (same shape as the undo refusal in
  `app/api/v1/system/pending_actions.py`).

## Tests (tester-first; one line per AC in the UAC)

pytest `tests/test_contact_customers_lane.py` (Postgres, `pg_session`, ZZT prefixes), vitest
beside each component, browser evidence under `documentation/plans/sales/evidence/
contact-customers/`.

## Slices

- S1 Phase 1 FE mock: both surfaces against a mock service (no backend).
- S2 Phase 2 BE: tester red tests, then routes + service repair + pending actions, mock
  swapped for `apiFetch`.
- S3 Phase 3: reviewer + security-reviewer + browser verification, fix round, hand test.
