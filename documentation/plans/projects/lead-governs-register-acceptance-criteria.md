# UAC: LEAD-GOVERNS-REGISTER (29 Oct 2026)

Status: v1. Owner answers (crew relay a36136098, 29 Oct): Q1 (a), Q2 (a), Q3 (a), Q4 (b), Q5 (a). Screens (A, C, D)
wait for the owner's mock v1 feedback; B, E, F, H (API + RBAC) build now.

Terms: an **edit holder** holds `projects.projects.edit`. A **submit-only salesperson** holds
`projects.registrations.submit` without `projects.projects.edit` (`BE/api/v1/projects/projects.py:87-89`); after
PORTAL-P4 (#1953, migrations `pp3_0001` / `pp4_0001`) the `salesperson` role holds exactly that plus
`projects.projects.view_own`. A **limited reader** holds `projects.projects.view_own` without `projects.projects.view`
(`BE/services/own_scope.py:41-43`). A user's **own leads** = leads whose `owner_user_id` OR `created_by` is that user.
Card: `CARD-lead-governs-register-29oct.md`. Plan: `PLAN-lead-governs-register-29oct.md`.

## A. Create lead wizard

- **LGR-A1** Steps read, in order: Customer, The development, Who told us, Assign and confirm.
- **LGR-A2** Step 1 shows one picker labelled "Customer" (required). Next is disabled until a customer is picked;
  Enter does not advance either.
- **LGR-A3** The Customer picker searches the server (`GET /order-management/customers/select?query=&limit=20`) by
  name or code; it never loads the whole customer list. Each option shows the customer name only, no debtor code
  (owner mock note 1, 29 Oct).
- **LGR-A4** No "Create" row and no new-customer fields anywhere in the wizard. A search with no hit shows the empty
  message only.
- **LGR-A5** A failed customer search shows the picker's error state with Retry, never an empty list.
- **LGR-A6** Rough value and Notes sit in The development step; the typed-value check still stops the walk there.
- **LGR-A7** Confirm lists Customer first, with the picked name. "Buyer" appears nowhere in the wizard.
- **LGR-A8** Create lead sends `customer_id` and never `new_customer`.
- **LGR-A9** Who told us holds Source, Their reference and Contact name only: no Firm picker (owner answer a36797930,
  29 Oct). Confirm lists no Firm. Create lead never sends `informant_party_id`.
- **LGR-A10** A submit-only salesperson's wizard has no Assign picker; Confirm shows them as Salesperson, and no assign
  call is made (the server makes the lead theirs, LGR-H3).

## B. Lead API

- **LGR-B1** `POST /project-sales/leads` without `customer_id` -> 422 `lead_customer_required`.
- **LGR-B2** `POST /project-sales/leads` with `new_customer` -> 422 (no customer row is created; `customers` count
  unchanged).
- **LGR-B3** `PUT` a lead: `customer_id` may change to another existing customer; setting it to null on a lead that has
  one -> 422 `lead_customer_required`. A lead that never had one may stay without one.

## C. Lead screens wording

- **LGR-C1** No visible "buyer" word remains on the lead screens: Leads list column, lead page tab and fact, the empty
  state ("No customer yet" / "Set the customer"), the related-lists titles and empty text ("<name> - other leads",
  "No other leads on this customer", "<name> - projects", fallback "This customer"), and the lead edit dialog (title
  "Who told us, and the customer", picker label "Customer"). Internal ids (tab id `buyer`, listing key
  `...::buyer-other-leads`) stay so saved links and column preferences keep working.
- **LGR-C2** The lead edit dialog's Customer picker uses the same server search as LGR-A3, and is not clearable once
  the lead has a customer.
- **LGR-C3** The lead edit dialog has no Firm picker, and saving it leaves an old lead's `informant_party_id` as it
  was. The lead page, Leads list "Told us" column, Awaiting acceptance list and timeline still show an old lead's Firm
  (read-only). The API keeps accepting `informant_party_id` (no schema change).

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
- **LGR-D8** Submit-only salesperson: the form shows the same Lead / Customer / Salesperson section (Lead picker no
  longer hidden, `ProjectForm.tsx:697`). Lead is required for Submit for approval; Save draft may leave it empty.
  Their Lead picker lists only their own open leads. Their Create lead wizard has no Assign picker: the lead is
  theirs, and Confirm shows them as the salesperson.
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
- **LGR-E6** Submit-only register/save/submit (`crm_register`, `crm_submit` and the draft save path) accept
  `lead_id`. Submit (new or existing draft) without a lead -> 422 `project_lead_required`; a draft saves without one.
  A lead that is not one of the caller's own leads -> 404 `lead_not_found` (same answer as a missing lead, nothing
  leaks). With a lead, LGR-E2 / LGR-E3 customer rules apply and the lead is linked (409 rule, marks it qualified),
  exactly as for an edit holder.

## F. Qualify

- **LGR-F1** Qualifying a lead that has a customer creates a project whose `sales_profile.customer_id` is that
  customer. A lead without one qualifies as today (no customer).

## H. Own leads for the submit-only salesperson (Q4 b, RBAC)

- **LGR-H1** `GET /project-sales/leads`: allowed with `projects.projects.view` (all leads, unchanged) OR
  `projects.projects.view_own`. A limited reader gets only their own leads, `total` counts only those, and every
  filter / search / sort applies inside that set. Holding neither -> 403.
- **LGR-H2** `GET /project-sales/leads/{id}`: a limited reader gets their own lead; any other lead -> 404.
- **LGR-H3** `POST /project-sales/leads`: allowed with `projects.projects.edit` (unchanged) OR
  `projects.registrations.submit`. A submit-only caller's lead is owned by the caller (`owner_user_id` = caller,
  whatever the body says) and appears in their own `GET /leads`. The customer rules of B1 / B2 apply.
- **LGR-H4** Every other lead route (PUT, status, assign, accept, decline, qualify, qualify-preview, disqualify,
  reopen, delete, metrics, disqualify-reasons) keeps its current slug: a submit-only / limited-only user -> 403.
- **LGR-H5** A user holding `projects.projects.view_own` and `projects.projects.edit` but not `view` is still limited
  on reads (own leads only), creates as an edit holder.
- **LGR-H6** No new permission slug and no migration; nothing changes for an edit/view holder.

Out of scope (owner may add later): a Leads menu entry for the salesperson; they reach their leads through the
Register form's Lead picker and Create lead.

## G. Existing data

- **LGR-G1** No migration. No existing lead, project or customer row is rewritten by this change (only LGR-E3's
  fill of an empty lead customer, at the moment someone registers with that lead).
