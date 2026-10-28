# UAC: Register a project v2 (PROJECT-REGISTER-V2)

Plan: `PLAN-project-register-v2-28oct.md`. Card: `CARD-project-register-v2-28oct.md` v1.2 (owner answers 28 Oct).
Mock: `documentation/mockups/project-register-v2/index.html` v1.2. Every case below is a test (pytest for BE, vitest
for FE) unless marked BROWSER. Fixtures are invented (Sales A / Sales B / Manager M, CONTOH names); never seed off
existing rows (CI DB is empty). Paths: FE = `sorento_crm_frontend/app/(protected)/project-sales`,
BE = `sorento_crm_backend/app`.

## A. Register form: order, Customer, Lead

- A1 The first field of "Who and what" is "Project title *", a textarea (not an input). Developer, Project type and
  Template follow it.
- A2 Section "Salesperson and customer" holds Salesperson and "Customer *". Lead is in Details, labelled
  "Lead (optional)", and keeps its "Create lead '<text>'" row.
- A3 Customer is an async search over `GET /api/v1/order-management/customers/select?query=&limit=`; options read
  the customer NAME only (no debtor code). There is NO create row: a query with no match shows "No customers found"
  only.
- A4 Create mode: Register is disabled until the title and Customer are set (Lead no longer required). Edit mode:
  Customer is optional (older projects save without one).
- A5 API: `POST /api/v1/project-sales/projects/` without `customer_id` -> 422 code `project_customer_required`;
  an unknown or other-company customer id -> 422; a valid one is stored in `projects.sales_profile.customer_id` and
  returned on the project (id + code + name). `PUT` without `customer_id` keeps saving.
- A6 Registering with a lead still links it (`set_project_lead`), unchanged.

## B. Developer, Architect, Main contractor: search and create on the spot

- B1 All three are async searches on `GET /api/v1/project-sales/parties/?party_type=<type>&query=<text>` (no more
  "first 200" list): a party that sorts after the 200th is found by typing its name.
- B2 A user holding `projects.parties.edit` sees "Create developer|architect|main contractor '<text>'" when no option
  matches; one click calls `POST /api/v1/project-sales/parties/` with `{name, party_type}` and selects the new party.
- B3 Without `projects.parties.edit` there is no create row (and the POST stays 403).
- B4 Creating a name that already exists for that type (case and spacing ignored) returns the existing party; no
  second row is written.

## C. AI extract (text and photo)

- C1 Under the title, "Check" and "AI extract" sit side by side. AI extract opens the existing
  `AIExtractDialog` (lifted from `app/(auth)/portal/components/` to a shared place, portal behaviour unchanged). Its
  upload stage gains one source: "Project title" (checked by default when the title has text, shown read-only and
  clamped to 2 lines); the user never pastes the text again. Photos are optional, added in the existing drop area.
  Extract runs on the title, the photo(s), or both; AI Extract is disabled when neither is chosen.
- C2 `POST /api/v1/project-sales/projects/ai-extract` (multipart: `text`, `files[]`) needs `projects.projects.edit`
  (403 otherwise). It calls `AIExtractService.extract` with form key `portal.project_registration`; the text is
  passed as a `.txt` file. Max 12 files; png, jpg, jpeg, webp, pdf, txt only (others 422).
- C3 Response = one proposal per field: `developer`, `architect`, `main_contractor` (exact name match, case and
  spacing ignored, among parties of that type -> `{status: "match", id, name}`; else `{status: "new", name}`),
  `project_type` (name match -> match; else `not_found`), `state` (resolved through the `my_state` lookup; else
  `not_found`), `mukim` (text), `customer` (exactly one customer with that name -> match; else `not_found`, never
  `new`), `title` (text).
- C4 The endpoint writes nothing except the AI usage-log row: no project, party or customer row is created.
- C5 Per-user rate limit: the 11th call in 10 minutes -> 429.
- C6 Provider failure -> 502 with a plain message; the form keeps what the user typed.
- C7 The dialog's existing review table lists only proposals with status match or new; its one new extension is a
  status cell per field (pill "Match" or "New", no button). The existing per-field x removes a row. Not-found values
  are not listed and stay blank on the form.
- C8 "Confirm and prefill" (the dialog's existing confirm button): first creates every listed New developer / architect / main contractor through the B2 create (B4 dedupe
  applies), then fills the form with all listed values; a non-empty title is never overwritten. A user without
  `projects.parties.edit` sees New party rows but confirming skips them (field left blank). A customer is only filled on
  match and is never created. Nothing else is saved until Register.
- C9 Tests never call a real provider (patch `AIExtractService._resolve_provider` / stub `extract`).

## D. Duplicate found: Register interest instead of Register

- D1 The duplicate basis is unchanged (`BE/services/project_clash_service.py`).
- D2 When the Check returns a blocking candidate, the warning is ONE line "Project already registered: <code>
  <title>" (code links to the project, title clamped to one line); no owner, stage, similarity or row buttons. The
  footer keeps Cancel and its ONE primary reads "Register interest in <code>" (top blocking candidate), enabled; the
  text "Blocked by an existing project" no longer appears.
- D3 A non-blocking similar candidate shows as one line "Similar project: <code> <title>" with no action, and the
  button stays "Register project". The label "Dispute" is gone everywhere ("Register interest" in the Access card).
- D4 "Register interest" opens a dialog titled "Register interest in <code>" with a required textarea "How and when
  did you find this project?"; submit creates the existing takeover request with `kind = "dispute"`; success
  navigates to the project.
- D5 The server lock is unchanged: a direct `POST /projects/` on a blocking clash still returns 409
  `project_already_registered`.
- D6 Existing request rules hold: no interest in your own project, no second open interest by the same user, none on
  an unapproved project.
- D7 Naming a different developer clears the match and the button returns to "Register project".

## E. Interested people and reassign

- E1 The project's Access card shows "Interested": every pending interest (requester name, date, note), to every user
  who can view the project.
- E2 Holders of `projects.projects.manage` see "Reassign to <name>" and "Dismiss" per row; nobody else does (the owner
  included). A non-manager calling the decide endpoint on an interest -> 403.
- E3 Reassign to X (approve that interest): owner becomes X, the previous owner becomes a collaborator, the request is
  `approved` with decided_by / decided_at; other pending interests stay listed.
- E4 Dismiss (reject): the request is `rejected` and leaves the Interested list.
- E5 The Reassign dialog lists interested people first (with their date), then everyone else; picking an interested
  person runs E3, picking anyone else keeps today's reassign.
- E6 E3 writes an activity-feed line "Reassigned from <A> to <B>" and the owner change is in the audit log.
- E7 A user who holds only `projects.projects.view_own` and has a pending interest can open that project.

## F. Notifications

- F1 A new interest notifies the project owner and every active holder of `projects.projects.manage`, never the
  requester.
- F2 E3 notifies the new owner and the previous owner.
- F3 `MANAGEMENT_PERMISSION` is `projects.projects.manage`; `management_user_ids` returns an active user whose role
  grants it (the existing floor-breach, staleness and PO-mismatch alerts now reach managers).

## G. Brands removed everywhere (no migration)

- G1 The project response has no `brands` / `brand_ids`; `brand_ids` sent on register, update, approve or lead
  qualify is ignored and writes no `projects.brands` row.
- G2 The project list ignores `brand_id`; clash candidates carry no `brands`.
- G3 FE: no Brands field (create and edit), no Overview line, no list column, no board badges, no clash badges, no
  brand filter param.
- G4 Existing `projects.brands` rows are left untouched (no migration).
- G5 MCP project tools still pass their tests with brands gone.

## H. Long titles

- H1 `components/common/TruncatedTextCell.tsx` gains `lines` (1 default, 2): the text clamps to that many lines with
  the full text as hover title; an eye button "Show full title" appears only when the text is clamped and opens a
  dialog with the full text.
- H2 The project detail header renders the title through it with `lines={2}` in every status.
- H3 Also clamped: the "Already registered as" link and possible-duplicate links on the detail page, the project
  crumbs on the schedule review and PO intake confirm pages, the 7 child-page project lines, the quotation document
  heading and the lead heading (2 lines), and every project picker trigger (`truncateTriggerLabel`).
- H4 BROWSER at 1280 and 375: a 60-word title takes at most 2 lines in the header; no horizontal scroll.

## I. Lead wizard buyer step (only if the owner answers card Q6 = a)

- I1 The Create lead wizard's Buyer select is search-only over existing customers; there is no "new customer" path,
  and the lead create API refuses `new_customer` with 422.

## J. Salesperson: Save draft and Submit for approval (owner Q7 = b)

- J1 A user holding `projects.registrations.submit` but not `projects.projects.edit` can open `/project-sales/new`;
  the footer shows Cancel, "Save draft" and the primary "Submit for approval". A user with neither: page denied and
  `POST /projects/` -> 403.
- J1b The Projects page (one page for everyone; its view_own gate comes from #1944) shows the "Register a project"
  entry to holders of edit OR the submit slug; for a submit-only user it is the only Start menu entry. The edit page
  (`[projectId]/edit/page.tsx:21`) opens for edit OR the submit slug; the server lets a submit-only user edit ONLY
  their own draft or rejected registration (anything else -> 403).
- J2 Save draft: the project is stored with `approval_state = 'draft'`, no code, owner = the user,
  `sales_profile.contact_id` = the user's `respond_contact_id`; NO notification of any kind is created. Required
  fields are not enforced on a draft (title only).
- J3 The draft is visible (list with a "Draft" pill, detail, edit) to its owner only; another salesperson and staff
  lists do not show it; `GET /projects/<id>` by anyone else -> 404.
- J4 Submit (new or from a draft): `approval_state = 'pending'`, `submitted_at` set, decided_* and reject_reason
  cleared; required fields enforced (A5); exactly the portal's "submitted" notice: an in-app notification of type
  `project_registration_submitted` to every active holder of `projects.registrations.approve` in the company except
  the submitter, with no email delivery row and no WhatsApp.
- J5 Resubmit a rejected one (Edit then Submit for approval): state `resubmitted`, notice type
  `project_registration_resubmitted` to the same recipients, in-app only.
- J6 Approve / reject of a CRM-submitted project: an in-app notification AND an email `notification_deliveries` row
  to the salesperson (resolved through the contact; when the user has no linked contact, through the owner).
- J7 Parity: for the same project data, the notifications created through the CRM path equal the portal path's
  (type, title, link, recipients, channels).
- J8 The portal path's notifications are unchanged (existing tests stay green).
