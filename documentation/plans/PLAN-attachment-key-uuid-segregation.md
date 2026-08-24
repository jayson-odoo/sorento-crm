# PLAN - Attachment storage keys: uuid-segregation, filename-independent

**Status:** Phase 1 (upload uuid key + column flips) + Phase 2 (copy-only migration) IMPLEMENTED
+ tested (staging + pytest). Phase 0 audit script done. Pending: run audit + migration on PROD,
flip remaining read-only FE display surfaces, `/code-review`, PR. Supersedes
[`PLAN-attachment-rename-storage-sync.md`](PLAN-attachment-rename-storage-sync.md).
(Decisions from session 2026-06-15.)

### Implemented (2026-06-15)
- Upload key `{entity_type}/{attachment_id}/{original_filename}` (generic); promotion/portal unchanged.
- Column flips: rename edits `stored_filename`; download `Content-Disposition` + n8n webhook use
  `stored_filename`; folder dup-check on `stored_filename`; `original_filename` immutable (removed
  from `AttachmentUpdate`); `AttachmentCreate` honors caller `id`.
- `scripts/migrate_attachment_keys_to_uuid.py` - copy-only (**old objects KEPT**), idempotent,
  dry-run default. Verified on staging: dry-run→WOULD_MIGRATE, apply→MIGRATED (new uuid key, old
  retained), re-run→SKIP. `scripts/audit_attachment_key_collisions.py` - read-only.
- FE Files panel (`AttachmentsInFolderPanel`) display + rename + download → `stored_filename`.
- Tests: `tests/test_attachment_keys.py`, `tests/test_attachment_rename.py` (15 pass).

### Follow-ups (not blocking core)
- **Other FE surfaces still show `original_filename`** (PromotionAttachmentsList, AttachmentDetailModal,
  AttachmentBrowser, DraggableAttachmentsTable, etc.). They match the user-facing name until a row is
  renamed, then go stale. Flip user-facing displays to `stored_filename || original_filename`.
- **Stock-list upload path** (`attachments.py` ~`:902`) left flat (singleton "latest" overwrite is
  intentional). Decide whether to exclude its 1 row from the migration or accept relocation.

## Context / problem

Storage object keys for generic resource attachments are **derived from the filename**:

| Upload path | Key built | Collision-safe? |
|---|---|---|
| Portal submission (`public/portal.py:777`) | `portal/{contact_id}/{uuid4}{ext}` | ✅ uuid dir **+ uuid filename** |
| Promotion (`attachments.py:632`) | `promotion/{entity_id}/{stored_filename}` | ✅ scoped by promotion id |
| **Generic resource (`attachments.py:634,886`)** | `{entity_type}/{stored_filename}` | ❌ **flat - no scope** |

The upload-time dup check `_find_filename_collision` is scoped to
`(directory_id, lower(original_filename))` - **folder-local** - but the key carries **no
folder/id component**. So:

- Same folder, same name → blocked (409 / auto "- copy"). Safe.
- **Different folder, same attachment-type, same name → not blocked → identical key →
  `put_object` silently overwrites the first object.** Both DB rows then point at one object.
  Data loss, no warning, no unique constraint.

`stored_filename`-in-key also made rename fragile (the now-superseded plan moved the object on
every rename). Both problems share one root cause: **the human name lives in the object key.**

### Decision (owner, 2026-06-15)

> Make resource/promotion keys uuid-segregated like portal submissions. Once the key is
> independent of the filename, rename is a pure DB label change (no R2 API), and cross-folder
> name clashes can't collide. Downloads already serve the human name via Content-Disposition,
> so an opaque key costs users nothing.

## Column semantics (CANONICAL - note: inverts the pre-2026-06-15 code usage)

| Column | Meaning | Mutable? | Drives |
|---|---|---|---|
| **`original_filename`** | The **first** filename at upload (sanitized). The immutable historical name. | **No** - frozen at upload | **The object key basename.** |
| **`stored_filename`** | The **current user-facing** name. What the UI shows; what the user renames. ("stored" = the name as currently stored in our record.) | **Yes** - rename edits this | UI display, download `Content-Disposition`, n8n webhook `attachment_filename`. |

> The old code had these two reversed for several concerns (key from `stored_filename`, rename
> edited `original_filename`, download + webhook used `original_filename`). Phase 1 flips them
> to the table above.

## Decisions (locked)

| Question | Decision |
|---|---|
| New key scheme | **`{entity_type}/{attachment_id}/{original_filename}`.** uuid dir = collision-proof; basename = the **immutable** `original_filename` (never re-keyed). (`attachment_id` = row PK uuid.) |
| Key basis | **`original_filename`** (immutable), NOT `stored_filename`. So the key is fixed for the object's life. |
| Key vs directory | **Key is directory-INDEPENDENT.** `directory_id` is DB-only folder organization; the key has no directory segment. Moving a file between folders (`bulk_move` / `directory_id` edit) is DB-only - never moves the object. **Never recompute the key from any mutable field** (directory, entity_type, stored_filename); `file_path` is the frozen source of truth, read back via `extract_key`. The `{entity_type}` prefix is cosmetic, frozen at upload. |
| Rename | **DB-only.** Edits **`stored_filename`** only; `original_filename` + key frozen. Never moves the object, never hits n8n. |
| Download filename | **`stored_filename`** (user-facing). Flip `Content-Disposition` from `original_filename` (`attachments.py:1116`). |
| n8n webhook `attachment_filename` | **`stored_filename`** (`attachment_webhook_helper.py:80`). At upload `stored==original`, so the downstream record tallies at creation. |
| Rename → n8n resync | **No.** Webhook fires at **upload only**. Post-upload renames do NOT propagate; downstream record keeps the upload-time name (accepted drift). |
| Promotion keys | Already scoped by `entity_id`; **leave as-is.** |
| Portal keys | Already uuid - **untouched.** |
| Existing flat-key rows | One-time **relocate migration** (copy→verify→delete into uuid keys). Idempotent; **audit first**. |

## Phase 0 - read-only collision audit (DO FIRST, before any migration)

`scripts/audit_attachment_key_collisions.py` - write-only, zero mutations:

- Group non-deleted attachments by `extract_key(file_path)`.
- Report keys shared by >1 live row (**active clobbers** - already-corrupted data), and the
  count of rows on the flat `{type}/{name}` scheme (migration blast radius).
- Owner runs against prod. This tells us whether any object is *already* doubly-claimed before
  we relocate (those need manual disambiguation - a relocate can't un-merge two rows that
  already share one object).

## Phase 1 - forward-fix the upload path + column flips (stop the bleed)

Generic resource upload must put the uuid in the key, with the **immutable
`original_filename`** as basename. Because upload writes to storage **before** the row is
flushed, pre-generate the id:

```python
attachment_id = str(uuid.uuid4())
original_filename = sanitize_storage_filename(upload_filename)   # immutable, = key basename
stored_filename  = original_filename                             # display, user-renameable later
# ... promotion path unchanged ...
else:
    s3_file_path = f"{final_entity_type}/{attachment_id}/{original_filename}"
# create row with the SAME id:
attachment_data = AttachmentCreate(id=attachment_id, ...)        # honor caller-supplied id
```

Column-flip changes (the inversion in the semantics table):
1. **Key basename** → `original_filename` (was `stored_filename`): `attachments.py:632/634/886`.
2. **Rename edits `stored_filename`** (was `original_filename`): `resources_service.update_attachment`
   + the FE rename dialog field + `AttachmentUpdate`. `original_filename` becomes read-only.
3. **Download `Content-Disposition`** → `stored_filename` (was `original_filename`): `attachments.py:1116`.
4. **n8n webhook `attachment_filename`** → `stored_filename` (was `original_filename`):
   `attachment_webhook_helper.py:80`.
5. **Folder dup-check** (`_find_filename_collision` / `_next_copy_name`) → key off `stored_filename`
   (the user-facing name) since that's what "duplicate name in this folder" means to a user;
   `original_filename`/key uniqueness is already guaranteed by the uuid dir.

- Apply key change to both generic-resource builders (`attachments.py:634` and stock-list `:886`).
- Confirm `AttachmentCreate` / create service persists a caller-supplied `id` (add field if absent).
- **Ships in the same PR as the migration** - otherwise new uploads keep minting flat keys.

> Interim state: the already-reverted rename is DB-only but still edits `original_filename`
> under the OLD semantics. Phase 1 flips it to `stored_filename`. Harmless until then.

## Phase 2 - relocate migration for existing rows

`scripts/migrate_attachment_keys_to_uuid.py`, idempotent, `--dry-run` default / `--apply`
guarded - reuses the kept primitives (`copy_object_verified`, `delete_object_best_effort`):

1. Select non-deleted attachments whose key is the flat `{type}/{name}` form (skip portal,
   skip promotion `{...}/{entity_id}/...`, skip rows already `{type}/{uuid}/{name}`).
2. `new_key = f"{entity_type}/{att.id}/{att.original_filename}"` (immutable basename; equals
   `basename(old_key)` for un-renamed rows, but use `original_filename` so a row renamed under
   the old code still relocates to its original name).
3. `copy_object_verified(provider, old_key, new_key)` → set `file_path = cdn_base_url(provider,
   new_key)` → commit → `delete_object_best_effort(provider, old_key)`.
4. **Skip / flag** any row whose `old_key` is shared by another live row (from Phase 0) - those
   are pre-existing clobbers needing manual review, not safe to auto-relocate.
5. Re-runnable: a row already on the uuid scheme is a no-op.

## Tests

- pytest (storage mocked): upload builds `{type}/{id}/{name}`; two same-name uploads in
  different folders → **distinct keys** (regression for the clobber); rename stays DB-only
  (already covered in `test_attachment_rename.py`); migration relocates a flat-key row and
  skips a uuid-scheme row.
- Verify against staging bucket (the `sorento-crm-staging` isolation from the superseded plan):
  upload two clashing names → two objects; run migration dry-run then apply on a seeded row.

## Risks / out of scope

- **Old CDN/cached links break** to relocated objects (old key deleted). App self-heals - 
  signed URLs minted from `file_path` on read; n8n gets fresh URLs on resubmit. Externally
  pasted old links do not. Accepted (same trade-off as any re-key).
- Anything hardcoding `{type}/{name}` keys must resolve via `file_path` instead. Audit grep
  before applying.
- Pre-existing clobbers (Phase 0 finds shared keys) are **not** fixed by relocation - flagged
  for manual disambiguation.
- Promotion/portal keys unchanged.

## File-by-file change list

1. `scripts/audit_attachment_key_collisions.py` - new, read-only (Phase 0). **Done.**
2. `app/api/v1/resources/attachments.py` (Phase 1) - uuid in key for both generic-resource
   builders with `original_filename` basename; pre-generate `attachment_id`; flip
   `Content-Disposition` (`:1116`) to `stored_filename`; flip `_find_filename_collision` /
   `_next_copy_name` to `stored_filename`.
3. `app/services/attachment_webhook_helper.py:80` - `attachment_filename` → `stored_filename`.
4. `app/services/resources_service.py` - `update_attachment` edits `stored_filename` (not
   `original_filename`); `original_filename` becomes read-only.
5. `app/schemas/resources.py` / create service - honor caller-supplied `id`; mark
   `original_filename` immutable; rename targets `stored_filename`.
6. FE rename dialog - submit `stored_filename`, not `original_filename`.
7. `scripts/migrate_attachment_keys_to_uuid.py` - new, idempotent relocate (Phase 2).
8. `tests/test_attachment_keys.py` - new (upload key shape, cross-folder clobber regression,
   download/webhook use `stored_filename`, migration relocate + idempotency).
9. Already done: rename reverted to DB-only (`resources_service.py`), schema comment, kept
   storage primitives in `storage_router.py` + `{s3,r2}_service.copy_file`.
