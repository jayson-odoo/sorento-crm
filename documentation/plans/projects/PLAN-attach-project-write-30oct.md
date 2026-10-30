# PLAN: attachment writes respect project edit rights (ATTACH-PROJECT-WRITE)

Status: review done, reviewer READY + security-reviewer findings fixed (small fix track: no migration; one UI change, below)

## Gap

Found by PS-REGISTER-CHECK-FIRST's security review on #1991, pre-existing on main.
`sorento_crm_backend/app/api/v1/resources/attachments.py`:

- `POST /` (upload) checks only `resource.attachments.upload`, never the right to work the
  `entity_id` project.
- `PUT /{id}` accepts `entity_type` / `entity_id`, so a file can be re-pointed onto, or off,
  any project.
- `POST /{id}/archive` and `PUT /{id}/restore` need only a signed-in user.
- `DELETE /{id}`, `POST /bulk-archive`, `POST /bulk-delete` check the attachment slug only.

Effect: any staff user can attach, re-point or restore a file onto another salesperson's
project (which satisfies #1991's Spec In document gate) or archive / delete it to block a move.

Scope addition (crew, from #1991's browser pass): `_find_filename_collision` scopes only by
`directory_id`. Project documents upload with no folder, so a same-named file on ANY other
project collides, and `on_conflict=replace` overwrites the OTHER project's file.

## Fix

Reuse `project_service.assert_can_edit_project` (`app/services/project_service.py:435`), the
same check `change_status` runs (`project_service.py:1453`). Edit right, not
`assert_can_write_project`: a pending registration still takes its documents (the approver fixes
it up before Approve, R8), and `change_status` does the same.

- One helper in `attachments.py`: when `entity_type == "project"` and `entity_id` is set,
  load the project (404 if missing) and assert the edit right with the caller's slugs.
- Upload: the target entity. Edit: the row's current entity AND the requested one when
  `entity_type` / `entity_id` are sent. Archive, restore, delete, bulk archive, bulk delete:
  every row's entity.
- Archive takes `resource.attachments.delete` (as bulk archive already does); restore takes the
  same slug, since it undoes an archive. No new slug, so no migration and no role reseed.
- FE (crew ruling on the slug ask): Drive row actions, the attachment record actions and the
  attachment detail modal hide Move to trash, Restore and Permanently delete without
  `resource.attachments.delete`; Drive's bulk Restore hides too. Nobody sees a button the
  server refuses. Users without the slug lose Move to trash / Restore.
- Collision: when `entity_type` + `entity_id` are given, only files on that same entity
  collide (upload and the `collision-check` read).

Security review round (all fixed in this lane): `bulk-move` plus folder delete / restore /
permanent-delete reached another project's file (now checked, `directories.py`); bulk attachment
type, bulk company (`attachment_ids`) and bulk access levels now checked; a plain Files upload
no longer collides with a project document; the existing-row check reads the project outside the
company scope and the draft filter, and a file on a deleted project is not locked. Helpers live in
`app/services/attachment_entity_access.py`.

Follow-ups (not in this lane): the `attachment.set_company` deferred action
(`record_actions.py`) and `bulk-company` with `directory_ids` can still move a project file to
another company; `reorder` and `resubmit` take no entity check (sort order, webhook re-fire).

Other entity types with an existing edit helper (not changed here, listed for follow-up):
`project_task_service.assert_can_edit_task` (`project_task_service.py:82`),
`project_lead_service.assert_can_edit_lead` (`project_lead_service.py:431`). No upload path
in the FE files attachments under `project_task` / `project_lead` today.

## Tests (red first)

`sorento_crm_backend/tests/test_attachment_project_write.py`: outsider refused / owner allowed
on upload, edit (into and out of a project), archive, restore, delete; collision does not cross
projects, and a cross-project Replace leaves the other project's file untouched.
