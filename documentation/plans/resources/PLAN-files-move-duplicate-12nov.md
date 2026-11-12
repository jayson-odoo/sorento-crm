# PLAN: Files move / upload name clash (FILES-MOVE-DUPLICATE)

Status: Build, hand-test round 2 (track: standard; no migration; RBAC touched by Replace, so security-reviewer runs)

## Problem (production, 12 Nov)

Resources > Files "Move to..." or drag: `PUT /api/v1/resource-management/attachments/{id}` with
`{"directory_id": ...}` returned 500. Cause: `UniqueViolation` on
`ux_attachments_dir_lower_filename_active` (migration `198_attachments_dirname_unique.py:21`), a
partial unique index on `(directory_id, lower(original_filename)) WHERE directory_id IS NOT NULL
AND is_deleted = false`. The model did not declare it, so no test schema had it.

## Owner rulings (12 Nov, via crew)

- The index stays on `original_filename` (a visible-name index was proposed and stopped).
- A clash offers **Rename / Replace / Skip** for that file; the rest of the batch moves.
- Rename in the clash dialog sets the new name as the visible AND original name, DB only. The
  stored object is keyed `{type}/{attachment id}/{original name}` and read back from `file_path`
  (`attachments.py:658-675`, `storage_router.py:220`), so no object is copied and no URL changes.
- Replace sends the file already in the folder to Trash; its links stay on it (restore to undo).
- Suggested name `name (1).jpg`, bumped until free in the target folder.
- The general Rename (outside a clash) still edits only the visible name.

## Rules

1. Single move (PUT): check the target folder for the same original name before writing; still
   catch the `IntegrityError` of a race. Clash = 409 `ATTACHMENT_MOVE_NAME_CLASH`, plain message
   (`photo.jpg already exists in Folder B.`, or, when the other file was renamed,
   `holiday.jpg cannot be moved into Folder B: photo.jpg there has the same original file name.`)
   and `details` (file and folder name, the other file's visible name, a suggested name). No
   other file's id is returned.
2. `on_conflict=replace` needs `resource.attachments.delete` and write access to the file being
   replaced. `on_conflict=rename` needs `stored_filename`.
3. Bulk move: each row under its own savepoint; clashing files stay put and come back in
   `not_moved` with the same message and details.
4. Upload into a folder: the same original-name check before the bytes go to storage; a backstop
   catch in `create_attachment`; "Create copy" picks a name free on both names.
5. Frontend: "Move to..." and drag both go through `useMoveFiles` (one bulk-move call, then the
   dialog per clash), and one notice: `N moved. 1 not moved: <reason>`.

## Tests

- `sorento_crm_backend/tests/test_attachment_folder_name_clash.py` (22)
- `sorento_crm_frontend/.../attachment-directories/components/driveMoveSummary.test.ts`,
  `useMoveFiles.test.tsx`
- Three older fixtures seeded same-original twins in one folder (impossible in prod); fixed.

## Hand test round 2 (owner, 12 Nov 14:16)

Windows-style conflict handling:
- `POST /bulk-move` with `check_only: true` returns every conflict (folder + same-batch twins)
  and writes nothing. The client asks about all of them first.
- One window, "1 of N", with "Do this for the remaining N-1 conflicts": Skip / Replace /
  Rename for all (Rename picks a free "name (1)" per file; the New name box is for the current
  file only and hides when the box is ticked).
- Cancel, the X and Esc cancel the whole move: no write call is made.
- Then one `POST /bulk-move` with `resolutions` {id: {action, name?}}; one summary
  "N moved, R renamed, P replaced. S skipped: ...".
- Folders cannot clash (no name rule on `attachment_directories`); Files has no Duplicate action.
- Title padding keeps long names clear of the close X.
