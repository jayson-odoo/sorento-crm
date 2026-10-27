# PLAN: PORTAL-P2-ONLY-THEIRS, "only theirs" on the server (27 Oct 2026)

Status: Review passed (reviewer READY, security-reviewer READY, 27 Oct). Awaiting CI and the owner hand-test. PR #1911.
Track: full (RBAC change), security review required. Lane PORTAL-P2-ONLY-THEIRS.

Source brief: `documentation/plans/portal/PLAN-portal-unify-scout-27oct.md` (PR #1894), section
"Lane briefs" -> P2. That brief is the contract; this file records the lane's own decisions.

## Goal

A salesperson signed in to the CRM sees only their own and collaborator projects, and the records
under them, enforced on the server. P2 grants nothing: it adds `*.view_own` slugs (granted to no
role) and narrows what a holder of only `view_own` sees. Holders of `view`, admin and superadmin
are unchanged.

## Rule

LIMITED in a module = holds its `view_own`, not its `view`. Admin and superadmin are never limited
(`get_user_permission_slugs` hands them every slug). "Me" = user id + `users.respond_contact_id` +
the active sales agents linked to that contact (`sales.portal_agent.agents_for_contact`).

| Module | Slug | Theirs |
| --- | --- | --- |
| Projects and every child | `projects.projects.view_own` | owner, collaborator, or portal registration by their contact |
| Opportunities | `sales.opportunities.view_own` | sales agent is one of theirs |
| Sample requests | `projects.sample_requests.view_own` | salesperson is them, or contact is theirs |
| NPA | `procurement.new_product_applications.view_own` | applicant is them, or contact is theirs |
| Conversations inbox | `sla_management.conversations.view_own` | contacts linked to their agents' customers |

## Owner / crew rulings (27 Oct)

- Q1 (a): one guard on the project-sales router resolving the first URL id to its project, fail
  closed, plus explicit list filters.
- Q2 (a, pending owner, built on the recommendation): only the brief's project screens open to
  `view_own`; cross-project views (forecast, stock debt, order inquiries, leads, allocations,
  fulfilment planning, divergences, `/my-tasks`) stay `view`-only, so a limited user gets 403.
- Q3 (a, pending owner): conversation notes, replies and templates only on their own contacts.
- Q4 (a, pending owner): pickers offer only their own customers, agents and projects.
- Q5 (a): today's 403 for a sample request / NPA creator without `view` is untouched.

## Design

- `app/services/own_scope.py`: `is_limited`, `me`, one SQL clause per model.
- `app/api/v1/projects/_own_scope.py`: router-level dependency on `/api/v1/project-sales`. For a
  limited user: first path id must be in `_ANCHORS` (project, quotation, quotation version, sample,
  PO, PO version, delivery schedule, schedule version, delivery phase, sales order; sample requests
  answer by their own row rule) and resolve to a project in scope, else 404; later ids must be in
  `_NESTED` (each loaded by its route under the parent); id-less routes only from `_ID_LESS` or
  `_REFERENCE`; anything else 403. Read routes under the anchors take `[view, view_own]`.
- Project list: `project_service.list_projects(visible_to=...)`.
- Opportunities: the portal's agent-scoped service calls (`get_opportunity_for_agent_or_404`,
  `customer_options(sales_agent_id=...)`); create/update refused onto a foreign agent.
- Sample requests / NPA: `Actor.own_only` + `own_contact_id`; foreign row 404 for limited users.
- Conversations: `list_conversations(contact_ids=...)` and a `_contact_in_scope` dependency on
  every `{contact_ref}` route; `agent_contact_ids` extracted from the portal Conversations query so
  both answer the same question.
- Cross-cutting: project activity panel `can_view`, assistant `_probe_project`.
- Migration `pp2_0001_view_own_perms`: insert-only, five slugs, no grant.

## Found, not fixed here (pre-existing, reported on the PR)

- The generic Activities routes never enforce `ActivitiesAdapter.permission_view`; any signed-in
  user reads any project's activity (closed for limited users only).
- Attachment fetch by id needs login only.

## Acceptance criteria

See `portal-p2-only-theirs-acceptance-criteria.md`.
