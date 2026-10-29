# UAC: LEAD-GOVERNS-REGISTER (29 Oct 2026)

Status: DRAFT on the card's recommended answers (Q1-Q5 all (a)); final once crew relays the owner's answers.
Card: `CARD-lead-governs-register-29oct.md`. Plan: `PLAN-lead-governs-register-29oct.md`.

## A. Create lead wizard

- **LGR-A1** Steps read, in order: Customer, The development, Who told us, Assign and confirm.
- **LGR-A2** Step 1 shows one picker labelled "Customer" (required). Next is disabled until a customer is picked;
  Enter does not advance either.
- **LGR-A3** The Customer picker searches the server (`GET /order-management/customers/select?query=&limit=20`) by
  name or code; it never loads the whole customer list. Each option shows the name, with the code as its second line.
- **LGR-A4** No "Create" row and no new-customer fields anywhere in the wizard. A search with no hit shows the empty
  message only.
- **LGR-A5** A failed customer search shows the picker's error state with Retry, never an empty list.
- **LGR-A6** Rough value and Notes sit in The development step; the typed-value check still stops the walk there.
- **LGR-A7** Confirm lists Customer first, with the picked name. "Buyer" appears nowhere in the wizard.
- **LGR-A8** Create lead sends `customer_id` and never `new_customer`.

## B. Lead API

- **LGR-B1** `POST /project-sales/leads` without `customer_id` -> 422 `lead_customer_required`.
- **LGR-B2** `POST /project-sales/leads` with `new_customer` -> 422 (no customer row is created; `customers` count
  unchanged).
- **LGR-B3** `PUT` a lead: `customer_id` may change to another existing customer; setting it to null on a lead that has
  one -> 422 `lead_customer_required`. A lead that never had one may stay without one.

## C. Lead screens wording

- **LGR-C1** Leads list column, lead page tab and fact, and the lead edit dialog say "Customer", not "Buyer".
- **LGR-C2** The lead edit dialog's Customer picker uses the same server search as LGR-A3, and is not clearable once
  the lead has a customer.

## D. Register a project form

- **LGR-D1** Details no longer holds Lead. The bottom section is titled "Lead, customer and salesperson" and holds, in
  order: Lead (required on Register), Customer, Salesperson.
- **LGR-D2** Customer is a read-only value on Register. Picking a lead fills it with the lead's customer name; clearing
  the lead clears it. Register project stays disabled until a lead is picked.
- **LGR-D3** Picking a lead with no customer turns Customer into the required search picker (same search as LGR-A3);
  Register stays disabled until one is picked.
- **LGR-D4** Picking a lead fills Salesperson with the lead's assigned salesperson when the user may change the
  salesperson; otherwise Salesperson stays the signed-in user. A lead with no assignee leaves Salesperson as it was.
- **LGR-D5** The Lead picker's "Create lead '<text>'" row opens the wizard with the text as its title; on Create lead
  the new lead is picked, and its customer fills Customer read-only.
- **LGR-D6** AI extract never sets Customer (title, developer, parties, type, state, mukim still fill as today).
- **LGR-D7** Edit: Lead optional. With a lead, Customer is read-only and shows the project's customer; picking a
  different lead re-fills it from that lead. With no lead, Customer is the editable, clearable picker it is today.
- **LGR-D8** Submit-only salesperson (no `projects.projects.edit`): form unchanged by this lane (no Lead picker,
  Customer picker as today).
- **LGR-D9** Usable and not clipped at 375px and 1280px; long lead titles and customer names truncate with the full
  text in `title`.

## E. Project API

- **LGR-E1** `POST /project-sales/projects` by an edit holder without `lead_id` -> 422 `project_lead_required`; no
  project row is created.
- **LGR-E2** With `lead_id` whose lead has a customer: the project's `sales_profile.customer_id` is the lead's customer.
  A request `customer_id` that differs -> 422 `project_customer_not_lead_customer`; absent or equal -> created.
- **LGR-E3** With `lead_id` whose lead has NO customer: `customer_id` is required (existing 422
  `project_customer_required`); the project stores it AND the lead's empty `customer_id` is set to it. A lead that
  already has a customer is never overwritten.
- **LGR-E4** `PUT` changing `lead_id` to a lead with a customer sets the project's customer to that lead's customer
  (same mismatch 422 as LGR-E2). `PUT` without a lead change leaves the stored customer alone. Old projects without a
  lead still save with no lead.
- **LGR-E5** The 409 `lead_already_linked` rule is unchanged.
- **LGR-E6** Submit-only `crm_register` behaviour unchanged.

## F. Qualify

- **LGR-F1** Qualifying a lead that has a customer creates a project whose `sales_profile.customer_id` is that
  customer. A lead without one qualifies as today (no customer).

## G. Existing data

- **LGR-G1** No migration. No existing lead, project or customer row is rewritten by this change (only LGR-E3's
  fill of an empty lead customer, at the moment someone registers with that lead).
