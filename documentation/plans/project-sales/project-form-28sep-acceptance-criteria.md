# UAC: project form page for register and edit, salesperson pick, lead link (#1339)

Plan: `PLAN-project-form-28sep.md`. One AC per behaviour. "Form" means the shared `ProjectForm`.

## Routes and entry points

- AC-PF001. `/project-sales/new` renders the form in create mode, title "Register a project",
  crumbs, one Back to the pipeline, and no subtitle under the title.
- AC-PF002. `/project-sales/<id>/edit` renders the same form in edit mode, title "Edit project",
  with every field filled from the project, and no subtitle.
- AC-PF003. On the pipeline, Start > Register a project navigates to `/project-sales/new`; no
  dialog opens.
- AC-PF004. `RegisterProjectDialog` is deleted; nothing imports it.
- AC-PF005. On the project Overview, the gear menu carries Edit project (first item), which
  navigates to `/project-sales/<id>/edit`. The header still has exactly one primary action (the
  status move).
- AC-PF006. Edit project is absent from the gear when the viewer cannot edit the project.
- AC-PF007. Each form page has exactly one primary CTA: Register project (create) or Save changes
  (edit). Cancel returns to where the user came from (pipeline on create, the project on edit).
- AC-PF008. The create page is gated on `projects.projects.edit` (the grant the register endpoint
  needs); the edit page on `projects.projects.edit`, and a project the viewer cannot edit renders a
  read-only notice with no form.

## Fields (every select is `SearchableSelect`, the multi-select is `SearchableMultiSelect`, optional ones clearable)

- AC-PF010. Project title: required text; submit is disabled while empty.
- AC-PF011. Developer: party select (developers), clearable.
- AC-PF012. Registered company / SPV: text.
- AC-PF013. Location: text.
- AC-PF014. Address: multi-line text; also shown on the Overview "The development" card.
- AC-PF015. Project type: select, clearable; changing it clears Template.
- AC-PF016. Template: select, shown once a type is chosen, clearable.
- AC-PF017. Filing reference: text, max 64; saved on create and on edit.
- AC-PF018. Estimated sales value (RM): number >= 0.
- AC-PF019. Launch date: shown when the type derives delivery from launch.
- AC-PF020. Expected delivery from and to: one date range control, shown when the type does not
  derive delivery from launch.
- AC-PF021. Brands: multi-select of brands; saved as `brand_ids` on create and on edit; edit mode
  starts with the project's brands selected.
- AC-PF022. Architect: party select (architects), clearable.
- AC-PF023. Main contractor: party select (main contractors), clearable.
- AC-PF024. Create sends every filled field in one POST and lands on the new project's Overview.
- AC-PF025. Edit sends the changed form in one PUT and lands back on the project's Overview with
  the new values; clearing an optional field saves it empty.

## Duplicate Check and progressive Details

- AC-PF030. Check beside Project title runs the duplicate check on demand only (no request while
  typing), off below 4 characters; no match says so inline; a match renders the clash panel with
  Ask to join and Dispute.
- AC-PF031. A blocking match turns the CTA into "Blocked by an existing project" and disables it;
  submit re-runs the check as a guard.
- AC-PF032. In edit mode Check excludes the project itself (the server's update clash check already
  does); a rename that collides is refused with the server's message.
- AC-PF033. Create mode opens on Who and what with Details collapsed; Details opens by itself once
  developer, type, title (settled) and template (when the type has templates) are filled, once; a
  section the user toggled by hand is never moved.
- AC-PF034. Edit mode opens with every section expanded.

## Salesperson

- AC-PF040. Salesperson is a user select defaulting to the current user on create and to the
  current owner on edit.
- AC-PF041. A user holding `projects.projects.manage` can pick another salesperson on create; the
  project is registered with that owner.
- AC-PF042. A user without manage sees the salesperson select disabled; the server still refuses an
  owner other than the caller on register (403 `project_owner_assign_forbidden`).
- AC-PF043. On edit, only a manage holder can change the salesperson; others get 403
  `project_owner_reassign_forbidden` from the server and a disabled select in the UI.

## Lead link

- AC-PF050. Lead is a searchable select of open leads (server search on title or lead code),
  clearable, on create and on edit; edit mode shows the linked lead even though it is no longer open.
- AC-PF051. Create with a lead: the project carries `lead_id`; the lead is marked as Qualify marks
  it (outcome qualified, `qualified_at` stamped once, status on the qualified rung).
- AC-PF052. Edit to link a lead: same marking as AC-PF051.
- AC-PF053. Linking a lead that another project already carries is refused with 409
  `lead_already_linked`, naming the other project's code and title; nothing is saved.
- AC-PF054. Linking a disqualified lead is refused with 422 `lead_not_linkable`.
- AC-PF055. Linking needs the same lead right as Qualify: the lead's owner or a manage holder;
  otherwise 403 `lead_not_editable`.
- AC-PF056. Unlink on edit (lead cleared) sets `lead_id` to null. When no other project carries the
  lead, the lead goes back to open on its initial rung with `qualified_at` cleared (plan Q1).
- AC-PF057. Swapping to a different lead unlinks the old one (AC-PF056) and links the new one
  (AC-PF052) in one save.
- AC-PF058. Re-saving with the same lead is a no-op for the lead.
- AC-PF059. Qualify on a lead is unchanged (still creates a new project, still allows several).
- AC-PF060. The Overview "Where this came from" shows the linked lead after create and after edit,
  and "Registered directly" after unlink.

## Permissions

- AC-PF070. PUT by the owner, an approved collaborator or a manage holder succeeds; anybody else
  gets 403 `project_not_editable`, unchanged.

## Layout

- AC-PF080. Create page, edit page and Overview are usable and not clipped at 375px and 1280px, no
  horizontal page scroll.
