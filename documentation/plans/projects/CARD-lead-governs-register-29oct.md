# CARD: LEAD-GOVERNS-REGISTER v1 (29 Oct 2026)

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend/app/(protected)/project-sales`. Code read on
origin/main 98773e5aa9 (contains #1957 PROJECT-REGISTER-V2).

## What "Buyer" is today, and why its dropdown is empty

- **Buyer IS the customer.** The wizard's Buyer is `leads.customer_id`, a foreign key to the same core `customers`
  table (the AutoCount debtor = the dealer) that the register form's Customer uses (`BE/models/projects.py:742`;
  register form stores `sales_profile.customer_id`, `BE/models/projects.py:387`). Only the word differs. The word
  "Buyer" also sits on the leads list column (`FE/leads/components/LeadsGrid.tsx:168,171`), the lead page tab and fact
  (`FE/leads/[leadId]/components/LeadDetailClient.tsx:79,518`) and the lead edit dialog
  (`EditLeadInformantDialog.tsx:92`).
- **Empty dropdown.** The wizard loads the WHOLE debtor master in one unpaged call
  (`LeadWizardDialog.tsx:98` -> `order-management/shared/hooks/use-customer-select-query.ts:20`, no `limit`; 6,397
  customers on prod, 6,850 on the dev copy per the #1957 card) and filters it in the browser. Two code paths leave
  the menu empty: (1) while that call is in flight the picker shows its empty state, because the wizard passes it no
  loading or error state (`LeadWizardDialog.tsx:284-302`); (2) a failed call toasts once, then returns `[]` as a
  SUCCESS (`use-customer-select-query.ts:23-29`) cached with `staleTime: Infinity` (`:41`), so the menu stays empty
  for the rest of the session. Which one hit the owner is UNVERIFIED (their session cannot be read). The register
  form's Customer picker does not have the problem: it searches the server, 20 at a time
  (`_shared/services/projectService.ts:249-261`). The fix below moves the lead screens onto that same search, which
  removes both causes.

## How lead, customer and project connect today (facts)

- Register (`POST /projects`, `BE/api/v1/projects/projects.py:380`): Customer required on the server
  (`require_customer`, `:411` -> `project_registration_service.py:710-717`); Lead optional, linked by
  `set_project_lead` in the same transaction (`projects.py:438-452`).
- One lead links to ONE project through the form: 409 `lead_already_linked` when another project holds it
  (`BE/services/project_lead_service.py:1108-1121`). Linking marks the lead qualified (`:1139`), so it drops out of the
  register picker, which lists open leads only (`FE/_shared/hooks/useProjects.ts:788`).
- Qualify (lead page) creates the project itself and copies location and value, NOT the customer
  (`project_lead_service.py:993-1012`); it never calls `require_customer`.
- A project's shown customer = its own `sales_profile.customer_id`, else the lead's (`BE/services/project_service.py:743-751`).
  No write sync either way, so the two can differ today.
- The wizard CREATES a customer when the buyer is not on file (`select_or_create_customer`,
  `project_lead_service.py:360-381`, `source='project_lead'`), the open #1957 question 6 back door.
- Lead create needs `projects.projects.edit` (`BE/api/v1/projects/leads.py:243`); lead list needs `projects.projects.view`
  (`leads.py:96`). The submit-only salesperson (PORTAL-P4, #1953, not merged) never sees the Lead picker
  (`FE/_shared/components/ProjectForm.tsx:697` `!submitOnly`), and `crm_register` drops `lead_id`
  (`project_registration_service.py:734,755`; `_CRM_DETAIL_KEYS` at `:72` has no `lead_id`).
- AI extract matches `customer_name` to exactly one existing customer and fills Customer; it returns no lead
  (`BE/services/project_ai_extract_service.py:111-138`, `FE ProjectForm.tsx:316-319`).

## Rules (with my recommended answers)

Create lead
1. Step 1 is **Customer**: search existing customers by name or code on the server (the register form's search,
   20 at a time). Required: Next stays off until one is picked. No "Create" row, no name/phone/email fields (Q2).
2. Steps become: **Customer, The development, Who told us, Assign and confirm** (4, like the reference). Rough value and
   Notes move into The development. Confirm lists Customer first.
3. "Buyer" reads **Customer** everywhere a lead shows it (list column, lead page tab and fact, edit dialog, wizard).
4. The lead edit dialog uses the same server search; a set customer can be changed, not cleared.

Register a project
5. **Lead** leaves Details and joins the bottom section, renamed **Lead, customer and salesperson**: Lead *, Customer,
   Salesperson.
6. Lead is **required on Register** (Q1). Picking it fills **Customer read-only** with the lead's customer. Clearing
   the lead clears the customer. No lead yet: the picker's existing "Create lead '<text>'" row opens the wizard
   (`ProjectForm.tsx:713`); the new lead and its customer are picked on return.
7. The server enforces it, not only the screen: Register without a lead -> 422 `project_lead_required`; the project's
   customer is taken from the lead, and a different `customer_id` in the request -> 422.
8. AI extract no longer fills Customer (it belongs to the lead); it still fills title, developer, parties, type.
9. Edit keeps old projects saving: Lead optional; with a lead, Customer is read-only (the project's own); changing
   the lead re-fills it from the new lead; with no lead, Customer stays the editable picker it is today.
10. One lead, one registered project stays (409 above). A masterplan's second phase gets its own lead.

Lead page Qualify
11. Qualify copies the lead's customer onto the new project (one line beside location and value, `:995-998`).

Existing data: no migration, no rewrite. Old leads without a customer stay valid and show "Not set" with the existing
Set button (`LeadDetailClient.tsx:765`). Old projects without a lead keep their customer. A project whose customer
differs from its lead's keeps its own until someone changes its lead. A lead's later customer change does not cascade
to its project (explicit links only).

## Real examples (dev copy; from the #1957 card's 28 Oct read)

I could not re-query: auto-mode blocks SQL on `sorento_prod_1020` ("Production Reads"). Fresh counts:
`documentation/plans/projects/lead-governs-register-dev-counts.sql` (read-only, for crew or the owner).

1. PRJ-000004 "TRX Zus Coffee" -> LEAD-000001, buyer customer set. Edit shows Lead LEAD-000001 and its Customer
   read-only. Today its customer is reachable only through the lead (`project_service.py:743-751`).
2. PRJ-000001 "Setia Alam", no lead: Edit keeps Lead optional and the Customer picker editable (rule 9).
3. PRJ-000003 "Restroom Refurbishment For sekolah memangah", the AI extract case: extract fills the title; Customer
   comes from the lead picked, not from the text (rule 8).
4. PRJ-000002 "100 UNITS DSTH & 8 UNITS DS SEMI-S AT NUSA UTAMA" (S P SETIA): a later phase cannot reuse that
   project's lead; it gets its own (rule 10).
5. New lead for a dealer: step 1 searches the 6,850 dev debtors by name or code, 20 at a time; nothing loads the
   whole list.

## Edge cases

- Lead without customer (old rows) picked on Register: Q3.
- Lead already linked: not offered (open leads only); forced through the API -> 409 (unchanged).
- Salesperson vs staff: the submit-only salesperson has no lead rights today: Q4.
- Lead's assigned salesperson vs the session user: Q5.
- AI extract with a customer name: ignored for Customer (rule 8).
- Customer not in AutoCount yet: under Q2 (a) the lead waits until AutoCount has the debtor (your #1957 Q4 ruling:
  "that requires AutoCount").

## Questions (recommendation first)

1. Register needs a lead? (a) required on Register; Edit optional for old projects; Customer follows the lead
   read-only; no lead -> "Create lead" in the picker. (b) Lead optional; picking one locks Customer, no lead -> Customer
   picker. Rec (a): "so we select lead only ... govern the project registration process with lead creation".
2. Customer on a new lead: (a) required, step 1, search only (also answers #1957 Q6: no screen a salesperson uses
   creates a customer); (b) step 1 but optional ("Not known yet"); (c) required, keep "Create customer" as a
   prospect. Rec (a): with (b) a lead can reach Register with no customer; (c) reopens the AutoCount back door.
3. An OLD lead with no customer picked on Register: (a) the Customer picker unlocks for that lead; Register saves the
   pick on the project AND fills the lead's empty customer (never overwrites); (b) blocked: "This lead has no
   customer" until it is set on the lead page; (c) unlock, project only. Rec (a): no dead end, and the lead ends up
   governing anyway.
4. Submit-only salesperson (#1953): (a) this lane leaves their form as today (Customer picker, no Lead); a follow-up
   lane gives salespeople their own leads (a permission change, security review); (b) this lane grants salespeople
   lead create + own-lead view and requires Lead for them too. Rec (a): keeps this lane free of RBAC changes, and
   #1953 is waiting to merge on the same form.
5. Salesperson on Register: picking a lead (a) fills Salesperson with the lead's assigned salesperson when the user
   may change it, as Qualify already does (`project_lead_service.py:1010`); (b) keeps the signed-in user. Rec (a).

Mock: the wizard's first step is new, so one Lavish mock follows this card (`documentation/mockups/LEAD-GOVERNS-REGISTER/`).
No migration expected. Size stays M.
