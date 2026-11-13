# PLAN: sample request v2, slice 2: the limited salesperson's form (lane SAMPLE-REQUEST-V2)

Status: Review done (reviewer READY round 3, security READY round 2; cloud browser pass as a limited salesperson done, evidence `evidence-sample-request-v2/slice2-*`). Waiting on the owner's hand test. Slice 1 (PR #2338) is green on CI and frozen; this branch stacks on it.
Track: full (auth / own-scope surface: My Requests routes).

Owner Q1 (a), 11 Nov: the salesperson who sees only their own sample requests gets the same experience
as the staff form (ship to = a project party, registration contacts, guided sections, Preview then
Submit, back to where they started). External portal contacts keep today's form.

## What is true today (read in this lane)

- A limited salesperson's new / edit form is the PORTAL form
  (`project-sales/sample-requests/components/SampleRequestForm.tsx:124-169` ->
  `app/(auth)/portal/components/SampleRequestForm.tsx`) under `MyRequestClientProvider`, whose fetch only
  allows `/api/v1/public/portal/*` (rewritten) and `/api/v1/my-requests/*`
  (`services/myRequestsSubmissionClient.ts:149-163`).
- The server mounts the same sample request routes twice: the public portal with a portal token, and
  `/api/v1/my-requests` signed in with the CRM session (`app/api/v1/my_requests.py:147-314`,
  `app/api/v1/public/portal_sample_request.py:86` `register_sample_request_routes`). Both create with
  `source="portal"` and `salesperson_id=_linked_user_id(...)` (`portal_sample_request.py:194-202`).
- Slice 1 makes the ship-to party staff-only: `_apply_ship_to` returns early for `source != "staff"`, and
  `PORTAL_HIDDEN` drops `ship_to_party_id` / `ship_to_role` from portal responses.

## Approach (to confirm before code)

1. **Server: tell the two callers apart by the dependency, not by the row.** The My Requests token
   dependency already resolves a CRM user; `register_sample_request_routes` gets a flag (or the
   dependency exposes `token.user_id`) so the My Requests mount passes `actor_user_id` + that user's
   permission slugs into `create_draft` / `update_draft`, and `_apply_ship_to` runs for a row whose
   caller is a signed-in CRM user. The public portal mount stays exactly as slice 1 (ignored).
2. **Server: party and contact lookups for My Requests**, own-scope checked like the project itself
   (`own_scope.project_in_scope`): `GET /my-requests/sample-request/projects/{id}/parties` and
   `GET /my-requests/sample-request/parties/{id}/contacts`, returning what the staff endpoints return
   for that user's grants (phone only with `projects.parties.view`). No new route on the public portal.
3. **Frontend:** the limited salesperson renders the same staff form component with a client that
   points its four calls (parties, party search, contacts, save) at My Requests; no second form.
4. Tests red first: My Requests caller links / picks / contacts with the same gates as slice 1; an
   external portal token still cannot; a project outside the salesperson's own scope answers as unknown.

Question for the owner: none (Q1 answered). Security review mandatory (own-scope, ingest).

## As built (decisions, review round 1)

- Step 2 (My Requests party / contact routes) was NOT built: the CRM routes already answer a limited
  salesperson by their own grants and own project scope (`GET /projects/{id}/parties` behind
  `get_project_or_404(viewer_user_id)`, `GET /parties` and `GET /parties/{id}/contacts` behind
  `projects.parties.view` or `projects.registrations.submit`, fields trimmed without the view grant;
  `POST /parties` needs `projects.parties.edit`). The seeded salesperson role holds
  `projects.projects.view_own` + `projects.registrations.submit`, so the form works for it. A custom
  role holding ONLY the sample request grants cannot read parties and so cannot submit; trigger to
  revisit: such a role appears in use.
- Projects: the salesperson's form searches projects with the CRM project search (own-scope guarded),
  not the company-wide portal lookup, and every My Requests create / update runs the own-project
  check (security B1: the ship-to party would otherwise read another salesperson's project site
  address back).
- A salesperson's own request opened from its row or its edit link: a draft is the guided form, a
  submitted one the read-only view (review B1 / N1). The cached request is dropped after each save
  and refetched on open (S2); a failed load shows Try again (S3).
- Out of scope, recommended follow-up: the My Requests `/lookups/projects` (shared by other forms)
  still lists company-wide projects for a limited salesperson.
