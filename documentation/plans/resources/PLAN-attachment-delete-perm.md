# PLAN: attachment delete follows `resource.attachments.delete`

Status: round 3 (grant migration) in build. Track: started as small fix; round 3 adds a data migration, so it is no longer the small fix track (reviewer + security reviewer + browser pass all run).

## Journey

A user deletes one file from the shared attachment library (`DELETE
/api/v1/resource-management/attachments/{attachment_id}`). Today that route depends only on
`get_current_user` (`sorento_crm_backend/app/api/v1/resources/attachments.py:1588-1603`), while
the bulk archive route next to it already requires `resource.attachments.delete`
(`attachments.py:1642-1645`). Single delete should follow the same permission, through the same
shared `require_permission` dependency (`app/dependencies.py:414`).

## Change

- `attachments.py` single delete: `Depends(get_current_user)` becomes
  `Depends(require_permission("resource.attachments.delete"))`. The slug already exists
  (`app/rbac/permission_registry.py:333`, `_crud("resource", "attachments", ...)`), so no
  registry or migration change. superadmin and admin keep their bypass inside
  `check_user_has_permission`.

## Callers affected

- Files screen single delete (`sorento_crm_frontend/app/(protected)/resource-management/attachments/services/attachmentService.ts:413`).
- Project Documents tab delete (`sorento_crm_frontend/app/(protected)/project-sales/_shared/services/projectDocumentService.ts:128`)
  calls the same route. Its trash button checks only `project.can_edit`
  (`ProjectDocumentsPanel.tsx:184`). The role that uses it daily keeps delete through the
  round 3 grant, and the icon now also requires the slug, so a project editor without it is
  not offered a delete that would answer 403.

## Round 2: the UI follows the permission (crew, after the role audit)

Never a stuck UI: a caller without `resource.attachments.delete` is not offered permanent delete
of a trashed file, so there is no 403 toast and no dead click. `useHasPermission` hides:

- the Trash row context-menu "Permanently delete" (`DriveRowActions.tsx`, fed by
  `AttachmentsInFolderPanel.tsx`);
- the "Permanently Delete" button in `AttachmentDetailModal.tsx`;
- the "Permanently delete" record action in `attachments/actions.tsx` (detail page + browser).

"Move to trash" is the archive route and is not gated by this slug, so it stays. Bulk permanent
delete stays on `resource.attachments.bulk_delete`. The Project Documents tab is ON HOLD for the
owner's call on `project.customer.service`.

## Round 3: project.customer.service keeps delete (owner ruling 20 Oct 2026)

The role audit on the prod copy showed `project.customer.service` (9 staff users) deletes
project documents through this route from the Project Documents tab. The owner ruled the role
keeps delete by holding `resource.attachments.delete` (full library delete, chosen over a
project-scoped rule). `alembic/versions/adp_0001_pcs_attach_delete.py` inserts that one
role-permission link when the role and the permission both exist and the link is missing;
downgrade removes only that link. guest losing Trash "Permanently delete" is accepted.

Test: `tests/test_migration_adp_0001_pcs_attach_delete.py` (link present after upgrade, no
duplicate on re-run, existing link untouched, bystander untouched, downgrade scoped, no-op
without the role, no app imports).

## Out of scope (named, not built)

- Single archive / restore routes (`attachments.py:1606-1639`) are also session-only. Not in
  this lane's ask; raise separately if wanted.
- Bulk hard delete stays on `resource.attachments.bulk_delete`.

## Acceptance criteria

- AC-1: a signed-in user whose roles do not grant `resource.attachments.delete` gets 403 on
  single delete, and the attachment row is still there.
- AC-2: a signed-in user whose role grants `resource.attachments.delete` deletes the file (200,
  row gone).

## Tests

`sorento_crm_backend/tests/test_attachment_single_delete_perm.py`: AC-1 written first (red on
main), AC-2 alongside.
