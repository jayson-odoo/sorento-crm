# UAC: contact <-> customer links, and a sales agent's customers from the agent side

Plan: `PLAN-contact-customers-29sep.md`. Track: full, no migration.
Status: round 2 (29 Sep 2026). The owner answered the grill (relayed by crew on PR #1366): Q1,
Q3, Q5, Q6, Q7 as recommended; Q2 (b) no primary in the UI or the API of this lane (answered later the same day); Q4 no
suggestions; Q8 (b) a read-only linked-contacts list on the customer detail. No criterion is
deleted: a withdrawn or changed one keeps its text and gains a "Round 2:" note; AC-13, AC-34
and AC-35 are new.
Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` browser via agent-browser, `[T]` has a named
test, `[UX]` measurable design criterion.

## Journey

Actor A: a CS admin holding `user_management.contacts.edit` (read-only with `.view`).
Actor B: a sales admin holding `master_data.sales_agents.edit` (read-only with `.view`).

- **J1.** A opens Internal Users > Contacts from the sidebar, then a contact. The Profile tab
  shows a "Customers" card right under Contact Information: the customer accounts this phone
  number belongs to, each with the sales agent handling that account.
- **J2.** A picks a customer in "Add customer" (searchable by code or name; the option says
  which agent currently handles it). The row appears with that agent. Nothing else is asked.
- **J3.** When the contact belongs to several accounts, A clicks "Make primary" on one; the
  badge moves. (Q2) Round 2: withdrawn (Q2 b), no primary anywhere in this lane.
- **J4.** A clicks Unlink on a row: the button becomes a 5s countdown with Cancel; when it
  lapses the row is gone. No dialog.
- **J5.** Under the rows, "Suggested" lists up to five customers whose phone matches the
  contact's; A clicks Link on one and it becomes a row. Nothing is linked without that click.
  (Q4) Round 2: withdrawn, the owner links by the Add customer select only.
- **J9.** Round 2 (Q8 b): B, or anyone with customers view, opens Sales > Customers > a
  customer: the Details tab shows "WhatsApp contacts", the contacts linked to this account,
  read-only, each opening the contact record.
- **J6.** B opens Master Data > Sales Agents from the sidebar, then an agent, then the new
  "Customers" tab: the customers this agent handles, searchable and paged.
- **J7.** B picks a customer in "Assign customer" (the option says its current agent, if any);
  the customer moves to this agent and appears in the grid. (Q5, Q6)
- **J8.** B clicks Unassign on a row: a countdown in a toast, then the customer no longer has
  an agent. The customer form's own "Sales agent" field shows the same result.

## Phase 1 (frontend against mocks)

- AC-1 `[FE][T]` Given a contact with two links, when the Profile tab renders, then the
  "Customers" card sits directly after Contact Information and shows one row per link:
  `code - name`, the agent as `code - name` (or "No sales agent"), and a Primary badge on the
  primary row. No UUID is rendered. Round 2: no Primary badge (Q2 b).
- AC-2 `[FE][T]` Given a contact with no links, then the card shows the empty state heading
  "No customers linked" and the hint "Link the customer accounts this contact belongs to", and
  the "Add customer" select is still present.
- AC-3 `[FE][T]` Given the "Add customer" select, when the user types, then options are
  fetched from the server (paged, 50 per page), labelled `code - name` with the current agent
  as the description; picking one calls the link mutation with that customer id and clears
  the select.
- AC-4 `[FE][T]` Given a non-primary row, when "Make primary" is clicked, then the set-primary
  mutation is called with `is_primary: true`; given the primary row, the button reads "Clear
  primary" and sends `false`. (Q2) Round 2: withdrawn (Q2 b); no hook, service or route for it in this lane.
- AC-5 `[FE][T]` Given a row, when Unlink is clicked, then the row's control becomes the
  deferred countdown (`useDeferredRowAction`, action key `contact_customer_link.unlink`,
  entity id = the link id); no dialog opens and Escape does not cancel.
- AC-6 `[FE][T]` Given suggestions, then a "Suggested" list shows `code - name`, the phone
  number and the agent, with a Link button per row that calls the link mutation; given no
  suggestions, the list is absent (not an empty heading). (Q4) Round 2: withdrawn (no
  suggestions at all); the card renders no Suggested list.
- AC-7 `[FE][T]` Given the sales agent detail, then a fourth line tab "Customers" follows
  Transfers and renders a DataGrid (fixed layout, resizable columns, explicit sizes,
  truncate + title) with Code, Name, Region, Market segment, Status and an Unassign action;
  `rowHref` opens the customer detail. (Q5)
- AC-8 `[FE][T]` Given an agent with no customers, then the tab shows the empty state heading
  "No customers assigned" and the hint "Assign the customers this agent handles".
- AC-9 `[FE][T]` Given the "Assign customer" select, when a customer that another agent
  handles is picked, then the option showed that agent and the assign mutation is called with
  the customer id (no refusal). (Q6)
- AC-10 `[FE][T]` Given a row, when Unassign is clicked, then the deferred row action parks
  `customer.unassign_sales_agent` on the customer id with the agent id in the payload; the
  countdown is a toast and the row dims.
- AC-11 `[UX]` Both surfaces are usable and unclipped at 375px and 1280px: the contact rows
  wrap to two lines at 375px, the selects are full width, the grid scrolls horizontally.
  Nothing new animates beyond the existing countdown; reduced motion is honoured by it.
- AC-13 `[FE][T]` Round 2 (Q8 b): Given a customer with two linked contacts, the customer
  detail Details tab shows a "WhatsApp contacts" section after the existing cards with one row
  per link: the contact's name (or its phone number when unnamed) as a link to the contact
  record, the phone number, the linked date; given none, the heading "No WhatsApp contacts
  linked" and the hint "Link this customer from a contact's Customers card". Read-only, no
  button.
- AC-12 `[FE]` A user without `user_management.contacts.edit` sees the card read-only (no
  select, no Make primary, no Unlink); without `master_data.sales_agents.edit` the tab is
  read-only (no select, no Unassign). (Q7)

## Phase 2 (backend, tester-first)

- AC-20 `[BE][T]` GET `/user-management/contacts/{id}/customers` returns `data` rows with
  `id` (the link row id), `customer_id, customer_code, customer_name, is_active, is_primary,
  source, sales_agent_id, sales_agent_code, sales_agent_name, created_at`, ordered by
  `created_at`; an unlinked contact returns `data: []`. Round 2: no `is_primary` and no
  `suggested` in the body (Q2 b, Q4).
- AC-21 `[BE][T]` The same GET returns `suggested`: at most 5 phone-matched customers not
  already linked, each `customer_id, customer_code, customer_name, phone_number,
  sales_agent_code, sales_agent_name`; a contact with no phone match returns `[]`. (Q4)
  Round 2: withdrawn; the GET body has no `suggested` key.
- AC-22 `[BE][T]` POST `.../customers` with a valid `customer_id` creates the link with
  `company_id` equal to the customer's company (also under a two-company scope), `source
  = "manual"`, `linked_by` = the caller's user id, and answers 201 with the row; a repeat POST
  for the same pair answers 201 with the same row and creates nothing.
- AC-23 `[BE][T]` POST with a customer outside the caller's scope or unknown answers 404;
  an unknown contact answers 404; `is_primary: true` on POST makes it the primary and demotes
  the other primary in that company. Round 2: the body has no `is_primary` (Q2 b); a body
  carrying it is a 422 (`extra="forbid"`), and two concurrent POSTs for the same pair both
  answer 201 with the same row (reviewer nit 6).
- AC-24 `[BE][T]` PATCH `.../customers/{customer_id}` `{is_primary: true}` demotes the other
  primary (same company) and returns the row; `{is_primary: false}` clears it; an unlinked
  pair answers 404. Round 2: withdrawn (Q2 b), the route does not exist (405 or 404).
- AC-25 `[BE][T]` The pending action `contact_customer_link.unlink` is registered with
  `WINDOW_REVERSIBLE` and permission `user_management.contacts.edit`; executing it with the
  link id deletes the row; the contact and the customer survive.
- AC-26 `[BE][T]` Permission: GET needs `user_management.contacts.view`, POST and PATCH need
  `.edit` (403 otherwise). (Q7)
- AC-27 `[BE][T]` `contact_customer_service.agents_for_contact(db, contact_id)` returns the
  distinct sales agents over the contact's links, ordered by agent code; links to customers
  without an agent contribute nothing; no links returns `[]`.
- AC-28 `[BE][T]` GET `/master-data/sales-agents/{id}/customers` returns
  `ListResponse[CustomerResponse]` of the customers whose `sales_agent_id` is this agent,
  under the caller's company scope, default sort `customer_code asc`, `query` matching code
  or name (ilike), paged by `page`/`limit`; an agent with none returns an empty page. Each
  row carries `region` and `market_segment_code` (declared on `CustomerResponse`).
- AC-29 `[BE][T]` POST `.../customers` `{customer_id}` sets `customers.sales_agent_id` to
  this agent through `CustomerService.update_customer` and answers 200 with the customer
  carrying `sales_agent_code`; a customer handled by another agent is moved (Q6); an
  inactive agent answers 422; a customer of another company than the agent's answers 422
  (shared agents always allowed); an unknown customer answers 404.
- AC-30 `[BE][T]` The pending action `customer.unassign_sales_agent` is registered with
  `WINDOW_REVERSIBLE` and permission `master_data.sales_agents.edit`; executing it clears
  `sales_agent_id` when it still equals the payload's agent, and leaves a customer already
  moved to another agent untouched. Round 2 (reviewer nit 5): in that moved case the action
  ends `failed` with a readable `error_text`, never `committed`; same rule as the unlink.
- AC-31 `[BE][T]` GET `/order-management/customers/select` rows carry `sales_agent_id,
  sales_agent_code, sales_agent_name` (null when unassigned) alongside the existing fields.
- AC-32 `[BE][T]` The customer audit row for an assign or unassign records the
  `sales_agent_id` change (the existing `__audit_columns__` path), so the move is traceable.
- AC-34 `[BE][T]` Round 2 (Q8 b): GET `/order-management/customers/{customer_id}/linked-contacts`
  returns `data` rows `id, contact_id, name, phone_number, created_at` (no `is_primary`,
  Q2 b) for the
  links of that customer, ordered by `created_at`; a customer with none returns `data: []`; a
  customer outside the caller's scope or unknown answers 404.
- AC-35 `[BE][T]` The route needs `order_management.customers.view` (403 otherwise). Parking
  `contact_customer_link.unlink` on a link id the caller cannot see, or
  `customer.unassign_sales_agent` on a customer the caller cannot see, is refused with 404 at
  park time; executing the unlink handler on a missing link marks the action failed, never
  committed.
- AC-33 `[FE]` The Phase 1 mocks are swapped for `apiFetch` calls at the service boundary;
  the contact card and the agent tab show real rows from the throwaway database.

## Phase 3

- AC-40 `[E2E]` Browser evidence via agent-browser, sidebar navigation from `/`: link a
  customer on a contact, reload, the row persists with its agent; unlink, wait out the
  countdown, the row is gone. Assign a customer on an agent, open the customer detail, the
  Sales agent field shows the agent; unassign, wait, the field reads "No sales agent
  assigned". At 1280 and at 375.
- AC-41 `[T]` Reviewer kill test on AC-22 (company stamp), AC-29 (move) and AC-30 (guard):
  commenting out the implementing branch turns the named test red.
- AC-42 `[T]` Security review on the multi-company scoping of the link rows and the two
  write routes (no new permission slug, no external surface).
