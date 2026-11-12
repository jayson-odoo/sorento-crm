# PLAN: Files move / rename / upload name clash (FILES-MOVE-DUPLICATE)

Status: Build (track: standard, migration replaces one index; red-first + kill test, reviewer, browser pass)

## Problem (production, 12 Nov)

Resources > Files "Move to..." or drag: `PUT /api/v1/resource-management/attachments/{id}` with
`{"directory_id": ...}` returned 500. Cause: `UniqueViolation` on
`ux_attachments_dir_lower_filename_active` (migration `198_attachments_dirname_unique.py:21`), a
partial unique index on `(directory_id, lower(original_filename)) WHERE directory_id IS NOT NULL
AND is_deleted = false`.

Second half (owner, 12 Nov): "it is judged by original filename right, I tried to rename also
cannot". The index is on `original_filename`, which is immutable and hidden
(`app/schemas/resources.py:218-223`); Rename edits `stored_filename`, the visible name. So a
rename cannot clear the clash and the user is stuck. The upload guard already judges the visible
name (`app/api/v1/resources/attachments.py:147-195`, `lower(stored_filename)`), so upload and the
index disagree too.

## Rules

1. Per folder, active files (`is_deleted = false`, `directory_id` set) have unique visible names,
   case-insensitive: `(directory_id, lower(stored_filename))`. `original_filename` no longer
   takes part.
2. Move (single PUT), bulk move, rename and upload into a folder all check the visible name before
   writing and still catch the `IntegrityError` (two parallel moves). A clash is a 409 with a plain
   message: `<name> already exists in <folder>.` No DB text, no 500.
3. Bulk move: one bad file never fails the batch. The others move; the response names each file
   not moved. The UI shows one summary: `N moved. 1 not moved: <name> already exists in <folder>.`
   Drag shows the same message.
4. No auto-rename, no overwrite on move or rename (owner may ask for "Keep both" later).

## Migration

New revision drops `ux_attachments_dir_lower_filename_active` and creates
`ux_attachments_dir_lower_stored_name_active` on `(directory_id, lower(stored_filename))`, same
partial predicate. Existing duplicates on the visible name: pending a crew data request (count on
the dev prod copy); handling to be decided with the owner before the migration lands.

## Files

- `sorento_crm_backend/app/services/resources_service.py` (`update_attachment`, `bulk_move`)
- `sorento_crm_backend/app/api/v1/resources/attachments.py` (upload insert catch, bulk move response)
- `sorento_crm_backend/app/schemas/resources.py` (`AttachmentsBulkMoveResponse.not_moved`)
- `sorento_crm_backend/app/models/resources.py` (declare the index)
- `sorento_crm_backend/alembic/versions/<new>.py`
- FE: `AttachmentsInFolderPanel.tsx` `performMove`, `AttachmentDirectoriesView.tsx` drag,
  `attachmentService.ts` bulk move type, a pure summary helper with a vitest.

## Tests (red first)

- PUT move into a folder holding the same visible name (any case) -> 409, plain message names file
  and folder, row unchanged.
- Rename to a name that exists in the same folder -> 409.
- Rename then move succeeds (the owner's stuck case: same original name, different visible name).
- Bulk move of 3 where 1 clashes -> 200, 2 moved, `not_moved` names the third.
- Bulk move where two movers share a name -> first moves, second named.
- Upload into a folder where the visible name clashes on another entity (index-only clash) -> 409,
  not 500.
- Vitest: move summary text.

## Standing rules that apply

- One bad line never fails a whole batch: the batch goes through and the skipped line is named.
- Plain business words only; no internal ids.
- Nothing hangs: every save ends in content or an error.
