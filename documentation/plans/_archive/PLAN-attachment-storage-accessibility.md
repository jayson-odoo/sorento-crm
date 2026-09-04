# PLAN - Attachment Storage Accessibility Audit + Cleanup Filters

**Status:** Phase 2 complete - BE + FE wired, 12 pytest + 6 vitest green, type-check clean, browser-verified end-to-end (Files storage_status=missing → 313 rows; Promotions attachment_state=unlinked_or_trashed → 20 rows; both hit the backend with the right param, no console errors). Audit handler ran live against R2+S3 (3279 accessible / 313 missing). Ready for review + deploy.
**Branch:** `feat/attachment-storage-audit` (isolated worktree off `main`; deliberately excludes the in-flight attachment key-rename work)
**Date:** 2026-06-16

## Problem

~258 attachments have a `file_path` whose object is **missing from object storage** (404 via CDN). Confirmed by direct bucket scans: 234 are gone from both R2 (`sorento-crm`) and S3 (`sorento-demo-bucket`); only ~24 promotion PDFs still exist in S3. Bulk loss is `product_photos` (uploaded directly to R2, never to S3). DB rows still point at dead keys, so the UI shows broken images/links.

The user wants to **clean up**, in prod:
1. Find attachments whose bytes are not accessible via storage → **trash** them (soft delete - existing `is_deleted` behaviour).
2. Then find promotions that are **unlinked** or **linked to a trashed attachment** → **hard delete** them (existing promotion delete behaviour).

This feature builds the **detection + filters**. The deletes themselves use existing UI actions (attachment soft-delete/archive, promotion hard-delete). No new destructive code paths.

## Decisions (locked with user)

- **Detection:** stored flag, populated by the existing **DB-driven scheduled-task system** (`scheduled_tasks` table + APScheduler heartbeat in the worker). Not a live per-request check. Cheap: lists each bucket once/day (~4 Class A ops), diffs in memory.
- **Attachment delete = soft** (existing `is_deleted` / archive). **Promotion delete = hard** (existing cascade delete). This feature does not delete anything itself.
- **Promotion delete-candidates:** `unlinked` (no `promotion_attachments`) OR `linked_to_trashed` (≥1 linkage to an `is_deleted=true` attachment). Expose a union value too.
- **Isolation:** separate worktree/branch; pure diff; deploys independently of the key-rename work.

## Non-goals

- No change to the storage key scheme (that's the separate key-rename work).
- No automatic deletion / no S3→R2 restore here.
- No real-time storage checks on list load.

## Design

### 1. Schema (migration `234_attachment_storage_status`)

Add to `attachments`:
- `storage_status` `VARCHAR(20)` NOT NULL `server_default 'unchecked'` - one of `accessible | missing | unchecked`.
- `storage_checked_at` `TIMESTAMP` NULL - last audit time.
- Index `ix_attachments_storage_status` on `storage_status`.

Model: `app/models/resources.py` `Attachment`. Schema: `app/schemas/resources.py` `AttachmentBase`/`AttachmentResponse` expose both (read-only).

### 2. Scheduled audit handler `attachment_storage_audit`

New `app/services/attachment_storage_audit_service.py`, registered in `app/scheduler/task_scheduler.py` `register_task_handlers()` as `attachment_storage_audit`. Seed a `scheduled_tasks` row (interval 1 day) in the migration.

Algorithm:
1. For each provider in {`r2`, `s3`} that has ≥1 non-deleted attachment: `get_backend(provider)`, paginate `list_objects_v2` over `backend.bucket_name`, collect the full key set (decoded).
2. Stream non-deleted attachments; derive key via `storage_router.extract_key(file_path)`; `storage_status = accessible if key in provider_set else missing`; set `storage_checked_at = now`.
3. Bulk-update in batches. Return `{scanned, accessible, missing, by_provider}`.

Notes: keys are matched **exactly** as stored (decoded path). Skips `is_deleted=true` rows (don't audit trash). Provider taken from the row's `storage_provider`.

### 3. Attachment list filter

`GET /api/v1/resource-management/attachments` (`app/api/v1/resources/attachments.py`) + `resources_service.list_attachments()`: add `storage_status: Optional[str]` → `q.filter(Attachment.storage_status == value)` when set.

### 4. Promotion filter

`GET /api/v1/marketing/promotions` (`app/api/v1/marketing/promotions.py`) + `marketing_service.list_promotions()`: add `attachment_state: Optional[str]`:
- `unlinked` → `~exists(PromotionAttachment.promotion_id == Promotion.id)`
- `linked_to_trashed` → `exists(join PromotionAttachment→Attachment where Attachment.is_deleted == true)`
- `unlinked_or_trashed` → OR of the two (the delete-candidate set)

### 5. Frontend

- **Files page** `AttachmentsInFolderPanel.tsx`: add "Storage status" Select (All / Accessible / Missing / Unchecked) in the Filters popover; thread through `attachmentService` + `useAttachments`; include in active-filter count + clear-all.
- **Promotions** `PromotionsList.tsx`: add "Attachment state" Select (All / Unlinked / Linked to trashed / Unlinked or trashed) in the quick-filters popover; thread through `promotionService.getPromotions`.

### 6. Tests (Phase 2)

- **pytest:** audit service marks accessible vs missing against a fake backend (monkeypatched `get_backend`); attachment list `storage_status` filter; promotion `attachment_state` filter (unlinked / linked_to_trashed / union) over seeded rows.
- **vitest:** Files filter control + Promotions filter control render all options and call the service with the right param.
- **playwright (MCP):** Files page → set Storage=Missing → grid filters; Promotions → set Attachment state=Unlinked or trashed → grid filters. Verify the right `/api/v1/*` query param.

## Files touched

Backend: `alembic/versions/234_*.py`, `app/models/resources.py`, `app/schemas/resources.py`, `app/services/attachment_storage_audit_service.py` (new), `app/scheduler/task_scheduler.py`, `app/api/v1/resources/attachments.py`, `app/services/resources_service.py`, `app/api/v1/marketing/promotions.py`, `app/services/marketing_service.py`, tests under `tests/`.

Frontend: `AttachmentsInFolderPanel.tsx`, `attachments/services/attachmentService.ts`, `attachments/hooks/useAttachments.ts`, `marketing-management/promotions/components/PromotionsList.tsx`, `promotions/services/promotionService.ts`, vitest specs.

## Deploy

Standalone. Migration `234` adds columns + seeds the task (idempotent `ON CONFLICT DO NOTHING`). Worker container (`ENABLE_SCHEDULER=true`) picks up the new handler after image deploy + `alembic upgrade head`. First run stamps every row; thereafter daily. No data migration; existing rows start `unchecked` until first audit.
