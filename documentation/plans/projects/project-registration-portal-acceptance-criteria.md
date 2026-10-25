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
- A12 Detail of a pending registration whose title shares lot + mukim with an existing project shows
  `possible_duplicates: [{project_code, title}]` (no project id, no holder).
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
  `project_registration_exact_duplicate` naming that project's code; nothing is created; the registration stays pending.
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

## D. Possible duplicates

- D1 Same lot + mukim: registration title "... DI ATAS LOT 9001, MUKIM TEBRAU ..." vs project title
  "KILANG ALPHA LOT 9001 MUKIM TEBRAU" -> named. "PT 9001" and "Lot No. 9001" read as 9001.
- D2 Same lot, different mukim -> not named by the lot signal.
- D3 Phase siblings: "TAMAN DELTA FASA 5" vs an existing "TAMAN DELTA FASA 4" on the same lot -> not named.
- D4 Spelling: "Setia Alam Ph 3B" vs existing "Setia Alam Phase 3B" -> named.
- D5 Meaning: with the embedding call stubbed to return vectors of cosine >= 0.80 for a project -> named; < 0.80 ->
  not named; the embedding call raising -> no error, other signals still apply.
- D6 Another company's project is never named. At most 5, strongest first (lot, then meaning, then spelling), no repeats.

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
