# Behaviour card: Project registration from the portal (PROJECT-REG-PORTAL)

Status: card + mock filed for owner answers (25 Oct 2026). Nothing built. Size **L** (one additive
migration: a new request table, see "Data"); owner may re-size.
Mock: `mockups/project-registration-portal.html` (open in a browser; every element names its component + path).
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`.

## What exists today (research, file:line)

**Projects** (the record a registration must end in)
- `projects.projects` (`BE/models/projects.py:225-325`) + `projects.sales_profile` (`:328-362`) + `projects.brands` (`:365-388`).
- THE registration lock: unique `(company_id, developer_party_id, normalised_title)` NULLS NOT DISTINCT (`:312-319`).
- `register_project()` (`BE/services/project_service.py:70-195`) runs the fuzzy clash check FIRST (`find_clashes`,
  `BE/services/project_clash_service.py`, surface 0.55 / block 0.70 calibrated on the live titles, `:23-48`), returns
  409 `project_already_registered` naming the holder, and only then draws the code from `NumberingService`, sets
  the first stage from the status graph and instantiates the template's tasks (the "Next action" column).
  No override flag: the recourse is join / dispute (`ProjectTakeoverRequest`, `models/projects.py:452-482`).
- Staff register directly today: `POST /api/v1/projects/` (`BE/api/v1/projects/projects.py:201-255`) with
  `projects.projects.edit`; registering FOR someone else needs `projects.projects.manage` (`:212-219`).
  Live check while typing: `POST /projects/clash-preview` (`:67-97`), rendered by
  `FE/app/(protected)/project-sales/pipeline/components/ClashWarningPanel.tsx` inside `ProjectForm.tsx:369-377`.
- A lead's Qualify is the other door into `register_project` (`BE/services/project_lead_service.py:967-1014`).

**Sample request (SR-CORE, #1718)**
- Portal pages `FE/app/(auth)/portal/c/[slug]/sample_request/*`, form `FE/app/(auth)/portal/components/SampleRequestForm.tsx`,
  API `BE/api/v1/public/portal_sample_request.py` (mounted before the generic portal router, `public/__init__.py:64-68`).
- Gate: kind must be in `resolve_visible_form_types` (`BE/services/portal_form_visibility_service.py:102`); it is in
  `GRANTABLE_PORTAL_FORM_TYPES` (`BE/services/portal_service.py:95-102`), so it is opt-in per segment / contact.
- Salesperson = the CRM user whose `respond_contact_id` is the contact (`portal_sample_request.py:50-52`).
- No approve / reject / revise: Submitted -> Processing is the coordinator taking it; edits after submit are refused
  ("cancel and raise a new one", `BE/services/sample_request_service.py:386-391`). No notifications at all.
- `sample_request_require_project` (`BE/models/user.py:450-453`) is enforced on submit only
  (`sample_request_service.py:292-302`); the portal picker lists projects of the contact's companies
  (`projects_for_contact`, `BE/services/sponsorship_link_service.py:45-85`). **A project approved by this lane shows
  up in that picker with no change**, because it is created in the contact's company.

**New product application (NPA, #1769)** - the pattern this lane copies
- Portal pages `FE/app/(auth)/portal/new_product_application/*`, form `FE/app/(auth)/portal/components/NewProductApplicationForm.tsx:146`,
  API `BE/api/v1/public/portal_new_product_application.py` (record loaded by `(id, contact_id)`, `:62-68`; applicant =
  linked CRM user, `:56-59`).
- Statuses draft -> submitted -> approved | rejected, cancelled (`BE/models/new_product_application.py:47`, CHECK `:110-113`).
  Editable in draft / rejected, locked in submitted / approved: `assert_unlocked` (`BE/services/new_product_application_service.py:144-156`).
  `submit :349`, `approve :375`, `reject :387` (reason required), `revise :410` (back to draft, clears the decision),
  `cancel :440`. Routes `BE/api/v1/procurement/new_product_applications.py:183-213`.
- This is the #1698 quotation-approval pattern (`BE/services/project_quotation_approval_service.py:227,436,463,507`),
  NOT the purchase-requisition code (a staff PR is never locked; PR revise is portal-only through
  `portal_revision_service.py:1502`). Copying NPA keeps "approved = locked + Revise" without the PR revision engine.
- Notifications (`new_product_application_service.py:1007-1072`): submitted -> holders of the approve slug (in-app +
  email); rejected / completed -> the applicant. Known gap: a portal contact with no linked CRM user gets nothing.
- Numbering `NPA-000001` per company under an advisory lock (`models/new_product_application.py:197-228`).
- Staff review screens: `FE/app/(protected)/procurement-management/new-product-applications/*`
  (`NewProductApplicationsList.tsx`, `NewProductApplicationDetail.tsx:373-375` lock + Revise).

## What ships

One record, **Project registration** `REG-000001`, raised by a salesperson in the portal (and, see Q4, optionally from the
CRM). A sales manager checks it in **Project Sales > Registrations**; Approve calls the existing `register_project()`
so the project lands in Pipeline exactly as a staff registration would (code PRJ-xxxx, first stage, template tasks).

## Rules

1. **Fields the salesperson fills, each mapped to the Projects list.**

   | Portal field | Required on submit | Lands in | Projects list column |
   |---|---|---|---|
   | Project title | yes | `projects.title` | Project |
   | Developer (pick from developer parties; see Q2 for "not in list") | yes | `projects.developer_party_id` | Developer |
   | Project type | no | `projects.type_id` | (filter) |
   | Location | yes | `sales_profile.location` | (detail) |
   | Site address | no | `sales_profile.address` | (detail) |
   | Estimated sales value (RM) | no | `sales_profile.estimated_sales_value` | Estimated |
   | Brands to push | no | `projects.brands` | Brands |
   | Launch date, expected delivery | no | `sales_profile.launch_date / expected_delivery_*` | (detail) |
   | Architect, main contractor (pick) | no | `sales_profile.*_party_id` | (detail) |
   | Note to the checker (how you heard, stage on site) | no | request only, copied to the project activity on approve | - |
   | Salesperson | automatic | `projects.owner_user_id` = the contact's linked CRM user | Owner |
   | Code | on approve | `NumberingService` (PRJ-xxxx) | Code |
   | Stage / Outcome | on approve | first rung of the graph / `open` | Stage / Outcome |
   | Template | checker sets on approve | `projects.template_id` -> template tasks | Next action |

   Required = title + developer + location: the three a checker needs to tell two developments apart. Everything else
   follows `ProjectRegisterRequest`'s rule that demanding all details up front is how duplicates get created
   (`BE/schemas/projects.py:192-198`).
2. **Duplicate hint while typing (portal).** After the title is typed the form calls the same matcher as
   `/clash-preview` and shows "Looks like PRJ-0143 Setia Alam Phase 3B (registered)". Code + title + stage only;
   the holder's name is NOT shown in the portal (Q3). A likely duplicate does not stop the submit: the checker decides.
3. **Statuses**: Draft -> Submitted -> Approved | Rejected; Cancelled from Draft / Submitted. Copy of NPA:
   editable in Draft / Rejected, locked in Submitted / Approved (`assert_unlocked`). **Revise** (salesperson or checker)
   takes a Submitted request back to Draft. An Approved request is final and links to its project: Revise on an
   approved registration would orphan a live project, so changes after approval are made on the project itself.
4. **Checking = the CRM review screen.** Shows the request in the paper-like layout plus a **Possible duplicates** panel
   (`ClashWarningPanel`, same candidates and thresholds as staff registration, every developer included). The checker
   can correct the developer / title / type and set the template before deciding.
   - **Approve**: calls `register_project(owner = applicant)`. A blocking clash (>= 0.70 under the same developer, open)
     disables Approve with the existing 409 message, so a duplicate can never be approved.
   - **Reject**: reason required (e.g. "Already registered as PRJ-0143, ask to join it"). Back to the salesperson, who
     may edit and resubmit.
   - **Revise**: back to Draft (as above).
5. **Who checks**: holders of `projects.projects.manage` (Q1 rec), the permission that already gates registering a
   project for someone else (`projects.py:212-219`). The applicant cannot approve their own request even if they hold it.
6. **Who can submit**: portal contacts granted the new kind `project_registration` (opt-in in
   `GRANTABLE_PORTAL_FORM_TYPES`, like SR and NPA) AND linked to an active CRM user. A contact with no linked user
   gets "Your portal access is not linked to a salesperson account. Ask the admin to link it." and cannot submit
   (closes the NPA gap where nobody is notified).
7. **Company**: the project is registered in the contact's company (`contact_company_ids`). A contact in two companies
   picks one (SearchableSelect); one company = no field.
8. **Notifications** (NPA pattern, in-app + email): Submitted / Revised -> `projects.projects.manage` holders; Approved
   ("REG-000004 approved as PRJ-0151") and Rejected (with reason) -> the applicant.
9. **What the salesperson sees afterwards**: the portal landing's kind selector gains "Project registration"; each row
   shows REG no, title, developer, status pill; Approved rows show the project code; Rejected rows show the reason.
   The approved project then appears in the Sample request project picker (no change to SR), so
   `sample_request_require_project = ON` becomes usable for portal salespeople.

## Examples

Titles are the real ones quoted in `BE/services/project_clash_service.py:28-38` (the live corpus the matcher was
calibrated on); developers and people are placeholders until the crew-data-request rows arrive (PR #1849).

| # | Input | Result |
|---|---|---|
| A | Salesperson A, portal. "Setia Alam Ph 3B", developer = the developer of the registered "Setia Alam Phase 3B", location Shah Alam | While typing: hint "Looks like PRJ-xxxx Setia Alam Phase 3B". Submit allowed -> REG-000001 Submitted. Checker sees score 0.76 BLOCKING (same developer, open); Approve disabled with the 409 text. Checker rejects: "Already registered as PRJ-xxxx, ask Sales manager to add you as collaborator" |
| B | Salesperson B, portal. "Kami Residence", developer X, location Cheras. Registered: "The Wyn Residence" (0.667) | Hint shows The Wyn Residence as context. Checker sees it below the block bar, Approve enabled. Approve -> PRJ-xxxx, stage = first rung, Owner = Salesperson B; REG-000002 Approved, locked, links to the project. B gets "REG-000002 approved as PRJ-xxxx" |
| C | Salesperson A, portal. "Subang Helicopter Centre", developer = holder of "Helicopter Centre in Subang" but that project is LOST | 0.893 shown, not blocking (lost projects may be re-tendered, `ClashCandidate` docstring `project_clash_service.py:66-73`). Approve allowed |
| D | Salesperson C submits "Tropicana Aman Phase 2", then notices the developer is wrong | Submitted = locked. C taps Revise -> Draft, fixes developer, resubmits. Checker notification says "revised" |
| E | Salesperson B, Sample request with `sample_request_require_project` ON, REG-000002 still Submitted | Project picker does not list it yet; submit refused "Pick the project" (today's rule). After approval it is listed |

## Edge cases

- Two salespeople submit the same development before either is approved: both reach the queue; the first approval
  registers it, the second now shows a BLOCKING candidate and cannot be approved (reject with the join hint).
- A clash appears between submit and approve (staff registered it meanwhile): same as above, Approve is checked live.
- Checker edits the developer to one that makes it a duplicate: Approve disabled immediately (live re-check).
- Numbering rule for projects missing: Approve shows the existing 422 `project_numbering_rule_missing`; the request
  stays Submitted.
- Delete: a Draft is deleted with the deferred countdown (`record_actions.py`, as NPA); submitted / approved cannot be
  deleted, only cancelled (submitted) or kept (approved).
- No UUIDs shown anywhere; developer / parties render by name.

## Data (additive migration, schema `projects`)

`project_registration_requests`: id, company_id, request_no (REG-000001 per company, NPA's numbering copied), status
(CHECK draft|submitted|approved|rejected|cancelled), source (portal|staff), contact_id, applicant_user_id, title,
developer_party_id, type_id, location, address, estimated_sales_value, launch_date, expected_delivery_from/to,
architect_party_id, main_contractor_party_id, brand_ids (uuid[]), note, template_id (checker), project_id (set on
approve), submitted_at, decided_at, decided_by, reject_reason, timestamps. Nothing existing is altered; no new
permission if Q1 = (a). New portal kind `project_registration` added to `GRANTABLE_PORTAL_FORM_TYPES` and
`FE/lib/portal-form-kinds.ts`.

Considered and not recommended: storing the request as a **Lead** (`ProjectLead`) with source = portal and using
Qualify as Approve, which needs no new table. Leads are non-exclusive sightings owned by the salesperson who qualifies
them themselves, with no lock, no reject-to-applicant loop and no Revise; bending them into an approval queue changes
a live funnel staff use daily. See Q5.

## Questions (recommendation first)

1. **Who checks?** (a) holders of `projects.projects.manage` (sales managers); (b) a new permission
   `projects.registrations.approve` given to a named role (e.g. project sales admin). **Rec (a)**: manage already means
   "may register a project for someone else", which is exactly what approving does; no new grant to maintain.
2. **Developer not in the list.** (a) salesperson may type a new developer name; the checker must pick an existing party
   or create it under Parties before Approve; (b) developer must be picked, else "Ask the sales admin to add the developer
   first". **Rec (a)**: new developments often come with a developer nobody has keyed yet, and (b) stops the form at the
   moment the salesperson has the information; the lock still runs because Approve needs a real party.
3. **Duplicate hint in the portal.** (a) show code + title + stage of a likely duplicate, no holder name; (b) show nothing
   in the portal, only the checker sees it; (c) also show the holder. **Rec (a)**: saves a pointless submit, and keeps
   who-holds-what inside the CRM (staff already see it, UAC J).
4. **Staff registering in the CRM.** (a) unchanged: staff with `projects.projects.edit` keep registering directly (they
   already get the clash check inline); the queue is for portal submissions only; (b) route staff registrations
   through the same check too. **Rec (a)**: the requirement is the portal; (b) would slow every staff registration and
   is a separate policy decision.
5. **Record shape.** (a) a new Project registration request (table above, NPA pattern, size L); (b) reuse Leads with
   source = portal and Qualify as Approve (no table, but leads gain a manager-only qualify path and a reject loop).
   **Rec (a)**: matches the SR / NPA flow the salespeople already know, and leaves the leads funnel alone.
