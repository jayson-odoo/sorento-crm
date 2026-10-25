# UAC: Project registration from the portal (PROJECT-REG-PORTAL)

Plan: `PLAN-project-registration-portal-25oct.md` (decisions D1-D14, API contract). Every case below is a test.
Fixtures are invented (no real names); developer / title shapes follow the card's fake examples.

## A. Portal access and the form

- A1 A contact WITHOUT the `project_registration` grant: `GET /submissions?type=project_registration` -> 403
  `FORM_TYPE_NOT_VISIBLE`; the kind is not in `/me` visible kinds. Granting it (segment or override) makes it visible.
- A2 `project_registration` is in `GRANTABLE_PORTAL_FORM_TYPES` and NOT in `SUPPORTED_TYPES` (not visible to every contact).
- A3 A granted contact with no active sales agent: create -> 403 `NOT_A_SALES_AGENT`.
- A4 Create a draft with `{fields}` -> 200, status `draft`, `is_draft` true, `sales_agent_name` = the agent's
  `person_label` (fallback `description`, then the code), `reference` null.
- A5 Unknown keys in `fields` are ignored; the stored fields are exactly: title, distributor_name, customer_id,
  customer_name, type_of_building, state, mukim, your_ref, developer_name, main_contractor_name, architect_name.
- A6 `customer_id` must be one of the agent's own debtors (the same debtor lookup the sponsorship form uses), else 422.
- A7 Another contact's registration id -> 404 on get / update / submit / delete.
- A8 Submit with title, state or developer_name blank -> 422, `detail` lists the missing field names; nothing changes.
- A9 Submit a complete draft -> status `pending`, `submitted_at` set, `is_draft` false; update now -> 422 (locked).
- A10 Delete a draft -> 204; delete a pending one -> 422.
- A11 The list (`GET /submissions?type=project_registration`) returns only the contact's own rows, newest first, `q`
  matching title / developer_name; each row carries status and, when approved, `ppf_no`.
- A12 Detail of a pending registration with a meaning match (cosine >= 0.80) to an existing project shows
  `possible_duplicates: [{project_code, title}]` (no project id, no holder); a lot + mukim match WITHOUT a meaning
  match names nothing (audit round 3).
- A13 AI extract: `FORM_SCHEMAS["portal.project_registration"]` exists and lists the A5 fields minus customer_id;
  `/ai-extract` with that form key is refused (403) for a contact without the grant.

## B. CRM queue and review

- B1 Without `projects.registrations.approve`: list / detail / approve / reject -> 403; the menu item is hidden.
- B2 The list defaults to pending rows only; `status=all` returns every status; `query` searches title, developer_name,
  distributor_name; DataGrid paging and sorting by submitted_at work.
- B3 Each row carries `sales_agent_name` (a name, never only the code) and `possible_duplicates`
  [{project_id, project_code, title}]; the FE renders each as a link to `/project-sales/<project_id>` showing
  "<code> <title>".
- B4 Detail returns `prefill.developer_party_id` when a developer party's name equals developer_name ignoring case and
  surrounding spaces, else null (same for architect, main contractor; `type_id` from type_of_building vs project type
  names).
- B5 Approve with a developer party -> 200: a project exists with the registration's title, the given developer,
  owner = owner_user_id, `sales_profile.state` / `mukim` set, code `PPF<yy><mm><nnn>` from the project numbering rule;
  the registration is `approved` with `project_id`, `decided_at`, `decided_by`; its portal detail now shows
  `reference` = that code.
- B6 Approve while a BLOCKING spelling clash exists (same developer, open project, title score >= 0.70) still succeeds
  (no 409): duplicates never block from the queue.
- B7 Approve when an open project already has EXACTLY the same developer and normalised title -> 409
  `project_registration_exact_duplicate` naming that project's code and carrying `details.existing_project`
  {project_id, project_code, title}; the review shows "Already registered as <code> <title>" linking to it (owner
  ruling 1); nothing is created; the registration stays pending.
- B8 Approve without developer_party_id -> 422. Approve or reject a non-pending registration -> 409
  `project_registration_not_pending`.
- B9 Reject with a blank reason -> 422; with a reason -> status `rejected`, reason stored; the contact's portal detail
  shows `reject_reason` and is editable again (`is_draft` true); resubmitting returns it to pending and clears
  reject_reason.
- B10 Staff direct registration (`POST /api/v1/projects/`) is unchanged: a blocking clash still returns 409
  `project_already_registered`.

## C. PPF numbering

- C1 `NumberingService` formats `{mm}` as the zero-padded month: rule `PPF{yy}{mm}`, 3 digits, monthly reset, on
  2026-05-07 with next_value 65 -> `PPF2605065`; the first draw in a new month restarts at start_value.
- C2 The migration changes the `project` rule to `PPF{yy}{mm}` / 3 digits / monthly only when its prefix_template is
  `PRJ-`; a rule with another prefix is left as is. Existing project codes are untouched.
- C3 A fresh seed (`seed_numbering_rule`) creates the PPF rule.
- C4 A rejected or still-pending registration draws no number (the rule's next_value is unchanged).

## D. Possible duplicates (semantic only, audit round 3)

- D1 Only a meaning match names a project: lot + mukim, spelling-near or identical titles without a meaning match
  name nothing; `parse_lot_numbers`, `parse_mukim`, `lot_pattern` and the spelling matcher are not used.
- D2 A phase sibling WITH a meaning match is named (no hard-coded phase filter).
- D3 (merged into D1)
- D4 (merged into D1)
- D5 Meaning: with the embedding call stubbed to return cosine >= 0.80 for a project -> named; < 0.80 -> not named;
  the embedding call raising -> no error, nothing named, not retried per row.
- D6 Another company's project is never named. At most 5, strongest first, no repeats.

## E. Project fields

- E1 `POST /api/v1/projects/` and `PATCH` accept `state` and `mukim`; `GET` returns them (response_model declares them).
- E2 ProjectForm shows State (SearchableSelect over the `my_state` lookup set, clearable) and Mukim (text) in Details,
  in create, edit and review.

## F. Notifications

- F1 Submit notifies every holder of `projects.registrations.approve` (in-app), excluding the applicant user.
- F2 Approve and reject notify the contact's linked CRM user; no linked user -> no error, nobody notified.

## G. Frontend

- G1 Portal: the kind label "Project Registration" appears in the landing selector only when granted; the form shows
  exactly the legacy fields in this order: Project title, Distributor name, Sales agent (read-only, the name),
  Customer name (debtor dropdown), Type of building, State, Mukim, Your ref, Developer, Main contractor, Architect; the
  existing AI Extract button is present.
- G2 CRM list: columns Date, Project title, Developer, State, Sales agent, Possible duplicate (links), Status; fixed
  layout, resizable, long text truncated with a title.
- G3 CRM review: ProjectForm prefilled; Date, Sales agent, Distributor, Customer, Your ref read-only under the header;
  "Possible duplicate:" line with links; foot CTA Approve; Reject opens a reason dialog; Approve with no developer shows
  the field error; a 409 exact duplicate shows its message. No clash Join / Dispute panel in review mode.
- G4 Usable and unclipped at 375 and 1280.

## RW. Rework: registrations are projects (owner 25 Oct 17:50; PLAN R1-R14). Supersedes B1-B5 (queue + review), G2, G3.

- RW1 Portal save creates a `projects.projects` row with `approval_state = draft`, `project_code` NULL, the legacy fields
  on the row / its sales_profile; there is no `projects.project_registrations` table after the migration.
- RW2 Submit -> `pending` with `submitted_at`; the A-section rules (visibility, agent, debtor pick, required fields,
  types, title cap, rate limits, ownership 404) all still hold on the new storage.
- RW3 `GET /api/v1/project-sales/projects/` returns pending and rejected portal projects (with `approval_state`,
  `project_code` null) and never drafts; `approval_state=pending|rejected|approved` filters work; a picker filter
  (e.g. `approved_only=true`) returns approved and staff projects only.
- RW4 Two pending projects with the same title and no developer party both exist (no unique violation); a pending one
  never blocks a staff registration of the same title and developer, and is never a clash candidate.
- RW5 `POST .../{id}/approve` by a holder of `projects.registrations.approve` (Coordinator role, no manage): needs a
  developer party (422 without), draws `PPF<yy><mm><nnn>`, sets the first stage, template tasks, `approval_state =
  approved`, decided_*; the portal detail now shows that code. Without the permission -> 403. Not pending -> 409.
- RW6 Approve when an approved project has exactly the same developer + normalised title -> 409
  `project_registration_exact_duplicate` with `details.existing_project`; nothing changes; no number drawn.
- RW7 `POST .../{id}/reject` needs a non-blank reason (422); -> `rejected`; still listed (RW3); the portal shows the
  reason and lets the salesperson edit and resubmit (-> pending, reason cleared).
- RW8 A pending or rejected project: status move -> 409 `project_not_approved`; quotation / sample PO / PO intake /
  task / schedule / sales order / stakeholder writes -> 409 `project_not_approved`; not offered by the portal or staff
  project pickers and refused by their validators; not resolved by the entity resolver; not in forecast / conversion /
  per-salesperson reports; not embedded; never a possible-duplicate candidate; not in the staleness sweep.
- RW9 An approver may edit a pending project (PUT) and pick the developer party; the owner (linked user) may too;
  others get 403.
- RW10 No message, title or label anywhere reads "None" for a missing code (helper renders "Awaiting approval").
- RW11 Migration: upgrade on a DB that has staff projects keeps them intact (approval_state NULL, codes kept); the
  partial index exists; downgrade removes code-less portal rows, restores NOT NULL, the full index and the PRJ- rule
  + counter.
- RW12 FE board: lanes "Awaiting approval" and "Rejected" before the stages with their counts; cards show "Awaiting
  approval" instead of a code; no drag into or out of those lanes. Grid: Stage pill and code text as above.
- RW13 FE detail: a pending project shows Approve (primary) + Reject (reason dialog) for approvers only, Edit beside
  them, the read-only legacy metadata (Date, Sales agent name, Distributor, Customer, Your ref), possible-duplicate
  links; the 409 exact duplicate shows "Already registered as <code> <title>" as a link; rejected shows the reason.
- RW14 FE: no Registrations menu item or pages remain; ProjectForm has no review mode; the edit form shows
  "Typed: <developer_name>" under Developer while no party is picked.
