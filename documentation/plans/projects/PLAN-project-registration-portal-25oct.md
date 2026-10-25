# PLAN: Project registration from the portal (PROJECT-REG-PORTAL)

Status: built, reviewer READY, security findings fixed, browser pass done; awaiting owner hand test (PR #1849). Track: full (one additive migration, new permission). Size L.
Card (settled): `CARD-project-registration-portal-25oct.md` v4 + owner final 13:03. UAC:
`project-registration-portal-acceptance-criteria.md`. Mock: `mockups/project-registration-portal-v4.html`.
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`.

## Owner final (25 Oct 13:03)

1. Sales Agent shows the person's NAME, not the code.
2. Every possible duplicate is a hyperlink to that project (CRM).
3. + 4. Customer = dropdown (debtor pick). Distributor is NOT a debtor: typed text. PPF drawn on Approve. A possible
   duplicate never blocks: Project Sales Admin decides. Q4 (a): no new "whose project" screen.

## Decisions (captain)

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
- **D8 Possible duplicates** = `find_possible_duplicates(db, *, company_id, title, developer_name, state, mukim,
  limit=5) -> list[{project_id, project_code, title}]`, ordered strongest first, union of:
  1. lot/PT + mukim: lot numbers parsed from both titles (`LOT|PT` + optional `NO.` + digits) and the same mukim
     (registration mukim or parsed `MUKIM <name>`; project `sales_profile.mukim` or parsed);
  2. spelling: `find_clashes(..., include_other_developers=True)` surface candidates;
  3. meaning: cosine >= `REGISTRATION_SEMANTIC_THRESHOLD` (0.80, calibrated in Phase 2) between the embedding of
     `title | developer | state, mukim` and stored project embeddings (`source_type="project"` on the existing
     pgvector pipeline). Any embedding failure (no key, timeout) drops this signal silently, never errors.

  A candidate whose phase designators differ (`are_sibling_developments`) is dropped. Projects of the registration's
  company only. Computed at read time (list and detail), never stored.
- **D9 Embeddings**: add source type `project` to the embedding worker (`_canonical_for_source`,
  `BE/services/embedding_worker.py:94`) and the change listener (`embedding_change_listener.py:186-208`) with canonical
  text `title | developer name | state, mukim`; a backfill command for existing projects. The in-request query embedding
  uses `_embed_text_chunks` (`:616`).
- **D10 Permission** `projects.registrations.approve` (registry + migration grants it to every role whose name is
  "Project Sales Admin" case-insensitively, plus the superadmin/admin roles, following `sr_0001`'s grant pattern).
  Gates the menu item, list, detail, approve, reject.
- **D11 Notifications** (NPA pattern, `new_product_application_service.py:1007-1072`): submit -> approve holders,
  in-app + email; approved / rejected -> the contact's linked CRM user if any.
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
