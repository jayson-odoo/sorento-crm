# PLAN: attachment delete follows `resource.attachments.delete`

Status: round 2 (FE gate) in build (small fix track: under 300 lines, no migration, permission gate on one route plus the controls that call it)

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
  (`ProjectDocumentsPanel.tsx:184`), so a project editor whose role lacks
  `resource.attachments.delete` now gets a 403 toast there. That tab's upload already needs
  `resource.attachments.upload`, so this matches. Hiding the button by permission is an FE
  follow-up, not this lane.

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
