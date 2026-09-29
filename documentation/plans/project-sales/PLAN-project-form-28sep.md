# PLAN: project form page for register and edit, salesperson pick, lead link (#1339)

Status: Track: full (FE and BE, over 300 changed lines with tests; no migration, no auth/RBAC
change: the existing `projects.projects.manage` rule is kept as is). In build on PR for branch
`feat/project-sales-project-form`. Base: origin/main `d79b46c5ea2b000dcdc4e1fef1a722d17b07b84e`.
UAC: `project-form-28sep-acceptance-criteria.md`
Issue: #1339.

## Owner's words (28 Sep, 18:2x MYT, verbatim)

"we need to make the linking to lead possible, need to make the editing possible also instead of
API, I think we should just have an edit project page, btw I don't like that we use a modal dialog
for create project, and form view for edit, we should standardise to use form view, so yeah we need
project form view and register / edit also use that, yeah we should let admin choose salesperson,
3 - we should be able to select the lead in creation and edition as well"

## Journey

A sales admin works the pipeline (`/project-sales/pipeline`) on behalf of the salespeople. They
press Start, Register a project, and land on a full page (not a dialog). They fill the identifying
fields (developer, type, title, template), press Check to see whether the development is already
held, and the Details section opens by itself. They pick the salesperson the project belongs to,
pick the lead it came from, fill brands, location and expected delivery, and press Register
project. They land on the new project's Overview, where "Where this came from" shows the lead.

Later they open the project, choose Edit project from the gear menu, and get the same page in edit
mode with every field filled in. They change fields, unlink or swap the lead, and press Save.

## Routes (confirmed against the app router)

The router has no `pipeline/[projectId]` segment. The project detail lives at
`app/(protected)/project-sales/[projectId]/page.tsx` (URL `/project-sales/<id>`), so the form lives
beside it:

- Create: `app/(protected)/project-sales/new/page.tsx` -> `/project-sales/new`. A static segment
  wins over the `[projectId]` dynamic sibling in Next's router, as `pipeline`, `leads` etc. already
  do.
- Edit: `app/(protected)/project-sales/[projectId]/edit/page.tsx` -> `/project-sales/<id>/edit`.

## What exists (verified in code at the base sha)

- `PUT /projects/{id}` (`app/api/v1/projects/projects.py` `update_project`) takes every field the
  form needs except `lead_id`; `ProjectUpdateRequest` (`app/schemas/projects.py`) has no `lead_id`.
- `POST /projects/` (`register_project`) accepts `owner_user_id`; someone else as owner needs
  `projects.projects.manage` (403 `project_owner_assign_forbidden`). `update_project` in the service
  refuses an owner change without manage (403 `project_owner_reassign_forbidden`). Both kept.
- `ProjectRegisterRequest` has no `admin_ref` (filing reference) and no `lead_id`.
- `qualify_lead` (`app/services/project_lead_service.py`) sets `project.lead_id`, then marks the
  lead: `outcome = qualified`, `qualified_at` stamped once, status to the `qualified` rung. The
  qualify route also requires `assert_can_edit_lead` (lead owner or manage).
- The only UI for these fields is `RegisterProjectDialog.tsx` (create only; sends no brands or
  owner). PR #1336 round 2 added the on-demand Check and a progressive Details section to that
  dialog; this lane moves both to the page and deletes the dialog.
- Overview "Where this came from" already renders the linked lead (code, source, raised date).

## Decisions

- D1. One `ProjectForm` component, `mode: 'create' | 'edit'`, used by both pages. Sections: "Who
  and what" (developer, type, title with Check, template), "Details" (registered company / SPV,
  location, address, filing reference, estimated sales value, launch date or expected delivery
  range, brands, architect, main contractor), "Salesperson and lead" (salesperson, lead). In create
  mode Details opens by itself once Who and what is filled (the portal price tag form's
  `openSectionOnce`); in edit mode every section starts open because every field already has a
  value to review. (Phase 2: the coder moved filing reference, value and delivery into Who and
  what to satisfy four tests that read them with Details folded; the captain kept this layout and
  fixed the tests to open Details first instead.)
- D2. One primary CTA per page: Register project (create) or Save changes (edit), at the foot of
  the form. The page header carries the title, the crumbs and Back only; no subtitle.
- D3. Salesperson is a `SearchableSelect` of active users (`services/userSelectService`),
  defaulting to the current user on create. A user without `projects.projects.manage` sees it
  disabled (they can only register for themselves, and the server says the same). The backend rule
  is unchanged.
- D4. Lead is a server-searched `SearchableSelect` of open leads (`GET /api/v1/project-sales/leads?outcome=open`),
  clearable, on both modes. In edit mode the current lead is passed as `selectedOption` so it shows
  although it is no longer open.
- D5. Backend: `lead_id` on `ProjectRegisterRequest` and `ProjectUpdateRequest`. One service
  function `link_lead(db, project, lead_id, actor, permissions)` in `project_lead_service`:
  - refuses (409 `lead_already_linked`) when another project already carries that `lead_id`, with
    the other project's code and title in the message;
  - refuses (422 `lead_not_linkable`) a disqualified lead;
  - requires `assert_can_edit_lead` (same as Qualify);
  - sets `project.lead_id` and marks the lead exactly as Qualify does, via one shared helper
    `_mark_qualified(db, lead)` that `qualify_lead` now calls too (no behaviour change to Qualify).
- D6. Unlink (`lead_id: null` on update) clears `project.lead_id`. If no other project still
  carries that lead, the lead goes back to open on its initial rung and `qualified_at` is cleared,
  so the unlinked lead is pickable again and the conversion metric does not count a conversion that
  was undone. See Q1. Reopening needs the lead right (owner or manage); an editor without it
  detaches the lead and leaves its state alone (review round 1, security L1).
- D7. Filing reference (`admin_ref`) joins the register request so the create page can set it.
- D8. Edit permission unchanged: owner, approved collaborator, or manage (`assert_can_edit_project`).
  The edit page renders a read-only refusal when `can_edit` is false; the gear's Edit project entry
  shows only when `can_edit`.
- D9. Overview gets Edit project as the first item of the existing gear menu, never a second
  primary. Address joins "The development" card so every form field has a read counterpart.
- D10. No migration: `projects.lead_id` already exists.

## Slices (one PR)

1. Plan + UAC (this commit).
2. Backend: tests first (link, unlink, already-linked refusal, disqualified refusal, owner pick
   under manage, edit permission), then `lead_id` / `admin_ref` on the requests, `link_lead`,
   `_mark_qualified`, route wiring.
3. Frontend: tests first (form both modes, lead picker, salesperson rule, pipeline CTA route,
   Overview Edit action), then `ProjectForm`, the two pages, pipeline CTA, gear entry, delete
   `RegisterProjectDialog`.
4. Browser pass 1280 and 375 on the create page, edit page and Overview; merge origin/main; final
   push.

## Open questions (for the owner)

- Q1. Unlinking a lead: this plan puts the lead back to open (initial rung, `qualified_at` cleared)
  when no other project still points at it, so it can be picked again. The alternative is to leave
  the lead qualified. Which one?
- Q2. The already-linked refusal applies to the form's link only. Qualify still lets one lead
  produce several projects (AC-O5, a masterplan with phases). Keep that difference?
- Q3. Sales admin and `projects.projects.manage`: no migration in the repo grants
  `projects.projects.manage` to "Project Sales Coordinator" (the sales admin role in production per
  migration 311; "Project Sales Manager" locally). Migration 330 only sweeps roles that already hold
  it. If the production sales admin role does not hold it, picking another salesperson is refused
  (403 `project_owner_assign_forbidden`) and the fix is a role grant, not a code change. This lane
  does not loosen the check.
- Q4. Permission for the link: Qualify needs `projects.projects.create`; registering a project and
  therefore linking a lead through the form needs `projects.projects.edit` (the register route's
  existing gate). Both still need the lead right. Keep, or require `.create` for the form link too?
