# PLAN - Attachment rename: storage-provider sync, `stored_filename` as source of truth

**Status:** ⛔ SUPERSEDED (2026-06-15) by [`PLAN-attachment-key-uuid-segregation.md`](PLAN-attachment-key-uuid-segregation.md).

This plan synced the R2 object on rename because the object key was *derived from the
filename* (`{entity_type}/{stored_filename}`). That treated the symptom. The root cause is
**name-in-key** - which also creates a cross-folder collision risk (two files, same
attachment-type + same name, different folders → identical key → silent clobber). Portal
submissions already avoid this entirely (`portal/{contact}/{uuid}{ext}` - key independent of
name). The superseding plan makes resource/promotion keys uuid-segregated too; once the key
no longer contains the name, **rename becomes DB-only and needs no R2 API at all**.

What was kept from this work: the `copy_file` storage primitive + `copy_object_verified` /
`delete_object_best_effort` helpers (the relocation migration reuses them) and
`sanitize_storage_filename`. What was reverted: the R2-sync branch in `update_attachment`
(now DB-only) and the schema comment.

---

_Original plan retained below for history._

**Original Status:** Implemented + verified against staging R2 (2026-06-15). Backfill script written, NOT executed.

## Local staging isolation (how this was tested without touching prod)

Local + prod share one Cloudflare R2 account. A **separate staging bucket** `sorento-crm-staging`
(same account/keys, free) isolates all rename copy/delete ops from prod data. Local
`sorento_crm_backend/.env` is switched to it:

```
# Prod (restore before deploy): R2_BUCKET_NAME=sorento-crm  R2_CDN_DOMAIN=cdn-sorento.com
R2_BUCKET_NAME=sorento-crm-staging
R2_CDN_DOMAIN=pub-31d7796b071d463c933d3df27da7dfc3.r2.dev   # free r2.dev public dev URL
```

`extract_key` is host-agnostic so the r2.dev domain works for reads; copy/verify/delete hit the
origin endpoint (account_id + bucket), exercising the **real Cloudflare API** against staging.

**⚠️ Restore the two prod lines before any deploy** - shipping with the staging bucket would point
prod at the wrong store.

Verified against staging:
- raw `R2Service` smoke: upload → `copy_file` → verify → download → delete (real API). ✅
- full `update_attachment` against real local DB + real staging bucket: object moved old→new,
  `stored_filename`/`file_path` rewritten to r2.dev URL, old object deleted, collision SQL clean. ✅
- pytest `tests/test_attachment_rename.py` (11 cases, storage mocked) green. ✅

## Context / problem

Attachment files (resource, product, promotion - all rows in the single `attachments`
table; product/promotion are FK join tables) are served from the CDN at a key derived from
`stored_filename`:

- Upload builds the object key as `promotion/{entity_id}/{stored_filename}` or
  `{entity_type}/{stored_filename}` (`attachments.py` upload handler).
- DB `file_path` = `cdn_base_url(provider, key)` - a stable, non-signed CDN URL whose path
  segment is that key.
- Reads (preview/download/presigned) recover the key via `storage_router.extract_key(file_path)`.

**Rename today is DB-only and does the wrong column.** `PUT /attachments/{id}` →
`AttachmentService.update_attachment` only `setattr`s `original_filename` (the editable display
name). The schema even documents this (`AttachmentUpdate.original_filename`):

```
# Updating this does NOT touch S3 - the underlying object key (stored_filename / file_path)
# is immutable so existing CDN URLs keep resolving.
```

Result: after a rename, `original_filename` changes but `stored_filename` / `file_path` /
the real R2 object do not. Any flow that (re)builds a CDN URL from the *renamed* name, or any
row whose `stored_filename` ↔ object key has drifted, fetches `https://<cdn>/<stale-or-wrong
key>` → **404, file won't retrieve**.

### Decision (owner, 2026-06-15)

> "`stored_filename` is the single source of truth. Rename must be synchronized to the R2
> storage provider as well."

So a rename must rename the **object on the storage provider** and update `stored_filename`
+ `file_path` to match. `original_filename` remains the human-typed display label.

This also makes two already-merged-locally changes correct and consistent (see *Related*):
display + AND-search now key off `stored_filename`, which becomes the canonical current name.

## Decisions (locked)

| Question | Decision |
|---|---|
| Collision: object already exists at new key | **Reject HTTP 409** (mirror upload collision). Never clobber. |
| Repair existing drifted rows | **Add an idempotent backfill script** - write only. **Do NOT execute** (owner is connected to live storage). |
| `stored_filename` vs `original_filename` | `stored_filename` = SoT + object key basename. `original_filename` = display label, kept in sync to the typed name. |
| Object stores have no native rename | **Server-side `copy_object` (new key) → verify → delete old.** R2 is S3-compatible; no byte download. |

## Design

### 1. Storage layer - server-side copy + a rename helper

`S3Service` / `R2Service` each gain:

```python
def copy_file(self, old_key: str, new_key: str) -> None:
    self.<client>.copy_object(
        Bucket=self.bucket_name,
        CopySource={"Bucket": self.bucket_name, "Key": old_key.lstrip("/")},
        Key=new_key.lstrip("/"),
    )
```

`storage_router.py` gains:

```python
def rename_object(provider: str, old_key: str, new_key: str) -> None:
    """Server-side rename: copy old->new, verify new exists, delete old.
    Raises on copy or verify failure (DB is NOT mutated by the caller in that case).
    Delete failure is logged best-effort (orphan object, not fatal)."""
    backend = get_backend(provider)
    if old_key == new_key:
        return
    if backend.file_exists(new_key):
        raise AppException(409, "A file already exists at the target name.")  # collision
    backend.copy_file(old_key, new_key)
    if not backend.file_exists(new_key):
        raise AppException(500, "Storage copy could not be verified.")
    try:
        backend.delete_file(old_key)
    except Exception as e:
        logger.warning("rename_object: copied %s->%s but delete of old failed: %s", old_key, new_key, e)
```

Add `copy_file` to the `StorageBackend` Protocol.

### 2. `update_attachment` - detect rename, sync storage

In `AttachmentService.update_attachment`, before the generic `setattr` loop, when
`original_filename` is present in `update_data` and differs from the current display name:

1. `new_stored = _sanitize_filename(new_display)` - reuse the exact sanitizer the upload path
   uses (`"".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip() or "file"`).
   Extract it into a shared helper so upload + rename can't drift.
2. `old_key = extract_key(attachment.file_path)`; `prefix, _ = old_key.rsplit("/", 1)`;
   `new_key = f"{prefix}/{new_stored}"`. (Preserves `promotion/{id}/…` and `{entity}/…` prefixes.)
3. If `new_key == old_key` → no storage work; still update `original_filename`.
4. `provider = normalize_provider(attachment.storage_provider)`.
5. **Collision pre-check** (also enforced inside `rename_object`): if `backend.file_exists(new_key)`
   OR another non-deleted `attachments` row's `file_path` resolves to `new_key` → raise 409
   `ATTACHMENT_FILENAME_COLLISION` with the same error shape upload uses.
6. **`storage_router.rename_object(provider, old_key, new_key)`** (copy → verify).
7. Set on the row: `stored_filename = new_stored`, `file_path = cdn_base_url(provider, new_key)`,
   `original_filename = new_display`.
8. `commit`. Then `rename_object`'s old-key delete already ran (step 6 deletes after verify) - 
   ordering note below.

**Ordering / partial-failure:** copy+verify happen *before* the DB commit; if they raise, the
request 500/409s and the DB is untouched (row still points at the live old object). The old-key
**delete** is the last step inside `rename_object` and is best-effort - a failed delete leaves an
orphan object but a valid DB pointer (new key), which is the safe direction. Never delete before
the new object is verified.

> Refinement to confirm in implementation: do the delete *after* the DB commit (so a crash between
> copy and commit leaves both objects + old pointer = still working), by splitting `rename_object`
> into `copy_verify()` then `delete_old()`. Will finalize during coding; the invariant is
> **DB never points at a missing object**.

### 3. Schema / API

No new endpoint. `PUT /attachments/{id}` already accepts `original_filename`. Update the field
comment in `AttachmentUpdate` (it currently claims storage is never touched). All three domains
(resource/product/promotion) rename through this one path because the file row lives only in
`attachments`.

## Backfill script (write only - DO NOT RUN)

`scripts/backfill_attachment_storage_keys.py`, idempotent, JOIN-style "repair where mismatch":

- For each non-deleted attachment: compute expected `key = extract_key(file_path)`; verify
  `backend.file_exists(key)`.
- Report (default `--dry-run`) rows where: object missing at `key`, OR `stored_filename` ≠ the
  last segment of `key`, OR `file_path` host/provider mismatch.
- With `--apply` (guarded, off by default): where the *intended* object exists under a derivable
  alternate key (e.g. keyed by `original_filename`), copy→verify→repair `stored_filename`/`file_path`.
- **Never executed in this task.** Owner runs it deliberately against live storage with `--dry-run`
  first. Script prints a summary and makes zero writes without `--apply`.

## Tests (pytest, storage mocked - no real S3/R2)

- `rename` happy path: provider=r2 and provider=s3 → `copy_file` called with right keys, row
  fields updated, old delete called. (boto client mocked.)
- `rename` collision → `file_exists(new_key)` True → 409, no copy, no DB change.
- `rename` copy-verify failure → second `file_exists` False → 500, DB untouched.
- no-op: new display sanitizes to same `stored_filename` → no storage calls, `original_filename`
  still updated.
- key derivation preserves `promotion/{id}/…` prefix.
- non-rename update (e.g. `description`, `directory_id`) → no storage calls (regression guard).

## Related (already changed locally, consistent with this plan)

- MCP `_resource_attachments` presenter → File Name shows `stored_filename` first.
- Backend `_and_probe_attachment` → filename-only AND-search over `stored_filename`, coverage-max.
- Both assume `stored_filename` = current canonical name - which this feature makes true.

## Risks / out of scope

- **Old CDN/cached links break** to the renamed object (old key deleted). Accepted per owner - 
  that is the point. Signed URLs are minted on read from the new key, so app flows self-heal;
  externally-pasted old URLs do not.
- Cross-provider rename not needed (rename stays on the row's own provider). Provider migration
  remains `scripts/migrate_attachments_to_r2.py`'s job.
- Concurrent rename of the same row: last-writer-wins; out of scope (no row lock added now).
- `.xlsm`→`.xlsx` macro-strip rename on upload is a separate path; unaffected.

## File-by-file change list (for implementation)

1. `app/services/s3_service.py` - `copy_file`.
2. `app/services/r2_service.py` - `copy_file`.
3. `app/services/storage_router.py` - `StorageBackend.copy_file` Protocol method; `rename_object` (or `copy_verify`+`delete_old`).
4. `app/services/resources_service.py` - rename detection + storage sync in `update_attachment`; shared `_sanitize_filename` helper.
5. `app/api/v1/resources/attachments.py` - extract sanitizer to shared helper (upload reuses it); 409 collision shape.
6. `app/schemas/resources.py` - correct the `original_filename` field comment.
7. `scripts/backfill_attachment_storage_keys.py` - new, write-only, not executed.
8. `tests/test_attachment_rename.py` - new, storage mocked.
