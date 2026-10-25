# PLAN: Project registration from the portal (PROJECT-REG-PORTAL)

Status: built, owner hand test passed 25 Oct ("1849 can merge"); awaiting crew merge. Rework per owner ruling 25 Oct 17:50 (registrations live in projects, no registration table). Track: full (migration alters projects, new permission). Size L.
Card (settled): `CARD-project-registration-portal-25oct.md` v4 + owner final 13:03. UAC:
`project-registration-portal-acceptance-criteria.md`. Mock: `mockups/project-registration-portal-v4.html`.
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`.

## Owner final (25 Oct 13:03)

1. Sales Agent shows the person's NAME, not the code.
2. Every possible duplicate is a hyperlink to that project (CRM).
3. + 4. Customer = dropdown (debtor pick). Distributor is NOT a debtor: typed text. PPF drawn on Approve. A possible
   duplicate never blocks: Project Sales Admin decides. Q4 (a): no new "whose project" screen.

## REWORK (owner ruling 25 Oct 17:50 + answers): registrations are projects

"The project registered should go to project instead of registration, we don't need another table for registration,
then the sales admin just approve from there." Answers: no code before approval; pending AND rejected projects are SHOWN
(board, list, counts) with a status pill, not hidden; Approve / Reject + Edit in the project detail header. Everything
below marked SUPERSEDED is replaced by R1-R14; the rest (legacy fields, AI Extract, semantic duplicates shown to
everyone, exact-duplicate refusal with link, portal Date, rate limits, debtor-pick customer, reject reason + resubmit,
PPF for staff too, approvers = admin + Project Sales Manager + Project Sales Coordinator) stands.

- **R1 Storage.** No `projects.project_registrations` table. A portal registration IS a `projects.projects` row.
  `projects.projects` gains `approval_state` (NULL for staff-registered projects; `draft` | `pending` | `rejected` |
  `approved` for portal ones), `reject_reason`, `submitted_at`, `decided_at`, `decided_by`; `project_code` becomes
  nullable. `projects.sales_profile` gains the portal-only legacy fields: `contact_id`, `sales_agent_id`,
  `distributor_name`, `customer_id`, `customer_name`, `your_ref`, `type_of_building`, `developer_name`,
  `main_contractor_name`, `architect_name` (plus `state`, `mukim` from D12).
- **R2 Code.** NULL until Approve; every screen shows "Awaiting approval" where the code would be (one FE helper, one
  BE helper for messages: never "None"). Approve draws the PPF from the `project` rule (D6).
- **R3 Registration lock.** `uq_projects_company_developer_title` becomes a PARTIAL unique index over rows whose
  `approval_state` IS NULL or `approved`, so pending / rejected / draft rows neither collide nor block. The exact
  duplicate on Approve still hits it: 409 `project_registration_exact_duplicate` with `details.existing_project`.
- **R4 "Approved only" filter** (one helper, e.g. `approved_projects(query)`), applied to INTERNAL paths: the clash
  check, the staleness sweep, status moves (a pending / rejected project cannot be moved through the funnel; only
  Approve gives it its first stage), embeddings + possible duplicates (only approved projects are candidates and
  embedded), portal and staff project pickers + their server validators (sample request, sponsorship, complaints,
  purchase request, PO intake / schedule uploads), lead linking / qualify, every WRITE on a project (quotations, sample
  POs, PO intake, tasks, schedules, sales orders, stakeholders: 409 `project_not_approved`), entity resolver + MCP /
  analytics read tools, the forecast / conversion / per-salesperson reports and their AI proxies (FLAGGED to the owner:
  a pending estimate is not pipeline yet; the board and list DO show them, R6).
- **R5 Portal.** Unchanged UX (SubmissionForm kind `project_registration`, legacy fields, AI Extract, Date, debtor
  pick, rate limits). Save draft creates the project row with `approval_state = draft` (NOT shown in the CRM; flagged);
  Submit -> `pending`; a rejected one is editable and resubmits to `pending` (reason cleared). Owner of the row = the
  contact's linked CRM user (else NULL until Approve). Possible duplicates (approved projects, semantic) shown as code +
  title.
- **R6 Pipeline board and list.** Pending and rejected projects SHOW: the board gets two lanes before the stages,
  "Awaiting approval" and "Rejected" (no drag in or out; counts = their cards); the grid's Stage column shows an
  "Awaiting approval" / "Rejected" pill and the code column "Awaiting approval"; a status filter can pick them. Drafts
  never show.
- **R7 Project detail header.** For a pending project, holders of `projects.registrations.approve` see **Approve** (the
  header's primary slot) and **Reject** (reason dialog), and Edit (the existing edit page) beside them. Read-only under
  the header: Date, Sales agent (name), Distributor, Customer, Your ref; "Possible duplicate:" links; for rejected: the
  reason. Approve needs a developer party (the edit form shows "Typed: <developer_name>" under Developer while unset).
- **R8 Edit rights.** Approvers may edit a pending project (`can_edit_project` + `serialize_projects.can_edit`);
  nobody moves it through stages before Approve.
- **R9 Approve** (`POST /api/v1/project-sales/projects/{id}/approve`, row lock): developer party required (422), draw
  the PPF, first stage from the graph, template tasks, `approval_state = approved`, decided_*; owner rule as before
  (applicant, else approver; another owner needs manage); exact duplicate -> 409 with the existing project; refused
  attempts draw no number (SAVEPOINT). Notifies the salesperson.
- **R10 Reject** (`POST .../{id}/reject`, reason required, row lock): `approval_state = rejected`; notifies the
  salesperson; the project stays visible (R6) until resubmitted from the portal.
- **R11 Removed**: the Registrations menu, list and review pages, `ProjectForm` review mode, the registrations router
  and model.
- **R12 Migration** (`prreg_0001` rewritten in place, still one head): alter `projects.projects` (nullable code, the
  new columns, the partial index), add the `sales_profile` columns, keep lookup sets, permission + grants, numbering
  UPDATE; downgrade deletes portal rows that have no code (draft / pending / rejected) before restoring NOT NULL
  (documented data loss of unapproved registrations), restores the full index, PRJ- rule + counter.
- **R13 Dev copy**: crew-migration SQL for the new columns / index; `DROP TABLE projects.project_registrations` held
  for the owner (destructive).
- **R14 Tests**: the registration tests are rewritten against projects; red first.

## Decisions (captain) (D3 storage, D5 review mode, D7 kwarg path and the CRM routes in the API contract are SUPERSEDED by R1-R14)

- **D1 Portal = the generic submission kind.** `project_registration` joins the generic portal submission plumbing
  (`BE/services/portal_service.py` `PortalService` + `BE/api/v1/public/portal.py` `/submissions/{kind}` routes) so the
  existing `SubmissionForm` (FIELDS map) and `PortalLanding` render it with no new portal component. A new tuple
  `GENERIC_SUBMISSION_TYPES = SUPPORTED_TYPES + ("project_registration",)` is what the routes and the service accept;
  `SUPPORTED_TYPES` stays the always-visible base (`portal_form_visibility_service.py:60`), so the kind is visible only
  when granted (`GRANTABLE_PORTAL_FORM_TYPES`). No revision adapter: the kind has no Revise (policy fails closed).
- **D2 Statuses**: draft, pending, approved, rejected. `draft` and `rejected` are editable by the contact; submit from
  either -> pending. Approve / reject only from pending.
- **D3 Fields stored as text** exactly as the legacy form: title, distributor_name, customer_id + customer_name (debtor
  pick, existing `debtor-async`), type_of_building (lookup set `project_building_type`), state (lookup set
  `my_state`), mukim, your_ref, developer_name, main_contractor_name, architect_name. sales_agent_id auto. Two lookup
  sets seeded by the migration (client-editable, existing `lookup-select` widget).
- **D4 Sales agent**: the first active agent of the contact by code (`agents_for_contact`,
  `BE/services/sales/portal_agent.py:24`); shown as `person_label or description or sales_agent`. A contact with no
  active agent cannot create or submit: 403 `NOT_A_SALES_AGENT` (same code the opportunity form uses).
- **D5 CRM review = `ProjectForm` mode `review`** (`FE app/(protected)/project-sales/_shared/components/ProjectForm.tsx`):
  prefilled from the registration (title; developer / architect / contractor party matched by exact case-insensitive
  name among parties of that type, else empty with the typed name shown as a hint; project type matched by name from
  type_of_building; state; mukim; owner = the CRM user linked to the contact if any). The legacy-only fields (Date,
  Sales agent name, Distributor, Customer, Your ref) render read-only under the page header. The foot CTA is
  **Approve**; **Reject** opens a reason dialog. The clash panel is replaced in this mode by the "Possible duplicate"
  line (links). Developer is required on Approve (the admin resolves the typed name to a party, as staff do).
- **D6 PPF = project code, drawn on Approve.** Add `{mm}` (zero-padded month) to `NumberingService` prefix formatting
  (`BE/services/numbering_service.py:76-83`). Seed `PROJECT_NUMBERING` becomes `PPF{yy}{mm}`, 3 digits, monthly reset.
  The migration updates the existing `doc_type='project'` rule ONLY while it still holds the shipped default
  (`prefix_template='PRJ-'`), so a customised rule is left alone. Existing PRJ codes are untouched. Staff
  registrations draw PPF too (one register, one series).
- **D7 Never block on duplicates from the queue.** `register_project(..., skip_clash_check=True)` (new kwarg, default
  False: staff direct registration keeps its lock unchanged). The DB identity index
  `uq_projects_company_developer_title` (`models/projects.py:312-319`) still refuses an EXACT same developer + same
  normalised title: Approve maps that IntegrityError to 409 `project_registration_exact_duplicate` naming the project
  ("Change the title, e.g. add the phase"). Flagged in the PR.
- **D8 Possible duplicates (audit round 3: SEMANTIC ONLY, no hard-coded or fuzzy matching)** =
  `find_possible_duplicates(db, *, company_id, title, developer_name, state, mukim, limit=5) -> list[{project_id,
  project_code, title}]`: the projects whose stored embedding has cosine >= `REGISTRATION_SEMANTIC_THRESHOLD` (0.80,
  to be calibrated on the live titles, crew-data-request) against the embedding of `title | developer | state, mukim`,
  same company only, strongest first. No lot/PT regex, no trigram spelling match, no phase-sibling filter. Any
  embedding failure (no key, timeout) drops the signal silently (30 s back-off), never errors. Query vectors are cached
  by text; the CRM list embeds its page in one call with a 3 s timeout. Shown to everyone, portal included (owner ruling
  2, 25 Oct 16:00: code + title in the portal, links in the CRM); never blocks Approve.
- **D9 Embeddings**: add source type `project` to the embedding worker (`_canonical_for_source`,
  `BE/services/embedding_worker.py:94`) and the change listener (`embedding_change_listener.py:186-208`) with canonical
  text `title | developer name | state, mukim`; a backfill command for existing projects. The in-request query embedding
  uses `_embed_text_chunks` (`:616`).
- **D10 Permission** `projects.registrations.approve` (registry + migration grants it to the superadmin/admin roles
  plus the existing roles named in the migration constant `APPROVER_ROLE_NAMES` = Project Sales Manager and Project
  Sales Coordinator, owner ruling 25 Oct 16:35). Gates the menu item, list, detail, approve, reject.
- **D11 Notifications** (NPA pattern, `new_product_application_service.py:1007-1072`): submit -> approve holders,
  IN-APP ONLY (audit round 3: no email per submit); approved / rejected -> the contact's linked CRM user, in-app + email.
- **D15 Audit round 3 (crew, 25 Oct)**: portal customer lookup scoped server-side to the agent's own debtors
  (`/lookups/debtors?kind=project_registration`) and pick-only; rate limits per contact (create / update / submit 30
  per hour, AI extract 10 per 10 minutes, 429 `RATE_LIMITED`, fail open); non-string field values 422; notification
  titles one line; review mode shows only the legacy fields; portal shows Date; the exact-duplicate 409 carries
  `details.existing_project` and the review links to it (owner ruling 1); downgrade restores the PRJ- rule and its
  counter.
- **D12 Project fields**: `projects.sales_profile` gains `state` + `mukim` (nullable); exposed on
  ProjectRegisterRequest / ProjectUpdateRequest / ProjectResponse and in `ProjectForm` "Details" for create / edit / review.
- **D13 AI**: `FORM_SCHEMAS["portal.project_registration"]` with the D3 fields; SubmissionForm's existing AI Extract
  button + `AIExtractDialog` need no change beyond the kind's FIELDS.
- **D14 Distributor**: typed text. Projects already have a `trading_house` party type
  (`BE/services/project_reference_service.py:25-31`); a pick from it is the obvious follow-up, flagged in the PR, not built.

## API contract

Portal (existing generic routes, kind = `project_registration`):
- `GET /api/v1/public/portal/submissions?type=project_registration&q=` -> `{items: [summary]}`; summary = the generic
  summary keys plus `status` (`draft|pending|approved|rejected`), `title`, `developer_name`, `ppf_no` (approved only).
- `GET /submissions/project_registration/{id}` -> generic detail; `fields` = D3 keys; extra keys `status`,
  `reference` (= ppf_no once approved, else null), `sales_agent_name`, `reject_reason`, `possible_duplicates`
  ([{project_code, title}], no ids or holders in the portal), `is_draft` true for draft and rejected.
- `POST /submissions/project_registration` / `PUT .../{id}` body `{fields}`: create / update a draft (or a rejected one).
- `POST .../{id}/submit` body optional `{fields}`: validates title, state, developer_name required (422 with
  `detail` = CSV of missing field names, as other kinds), -> pending.
- `DELETE .../{id}`: drafts only.

CRM (`/api/v1/projects/registrations`, permission `projects.registrations.approve`):
- `GET /` DataGrid params (`page, limit, sort, dir, query`) + `status` (default `pending`; `all` for every status) ->
  `ListResponse[RegistrationRow]`: id, submitted_at, title, developer_name, state, sales_agent_name, status,
  possible_duplicates [{project_id, project_code, title}], project_id, project_code.
- `GET /{id}` -> RegistrationDetail: every D3 field, sales_agent_name, status, reject_reason, submitted_at,
  decided_at, decided_by_name, applicant_user_id (linked CRM user), project_id, project_code,
  possible_duplicates [{project_id, project_code, title}], prefill: {developer_party_id, architect_party_id,
  main_contractor_party_id, type_id} (D5 matches, null when none).
- `POST /{id}/approve` body = ProjectRegisterRequest fields (title, developer_party_id REQUIRED, type_id,
  template_id, owner_user_id, admin_ref, details..., brand_ids, state, mukim) -> RegistrationDetail (status approved,
  project_code = PPF). 409 `project_registration_not_pending`, 409 `project_registration_exact_duplicate`, 422 missing
  developer.
- `POST /{id}/reject` body `{reason}` (non-blank) -> RegistrationDetail (rejected).

## Slices (one lane, commits on this branch)

1. Phase 1 FE: portal kind (kinds list, labels, FIELDS, landing), CRM list + review (ProjectForm review mode), State +
   Mukim on ProjectForm, service + hooks against the contract (no backend yet).
2. Phase 2 tester: red pytest + vitest from the UAC. Coder: model + migration, numbering `{mm}`, portal kind, CRM
   API, duplicates, embeddings source type, notifications, AI schema; green.
3. Calibration of D8's meaning bar on live titles via crew-data-request (masked output only).
4. Phase 3: reviewer + security-reviewer (portal ingest + new permission) + browser pass 1280 / 375.
