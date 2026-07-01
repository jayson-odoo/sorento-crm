# PLAN — Attachment grid thumbnails

**Status:** Phase 2 done + browser-verified (branch `perf/attachment-grid-thumbnails`).
Backfill running over all 3140 existing image rows (idempotent). Live check:
every grid `<img>` now loads a `.thumb.jpg` at `naturalWidth ≤ 320` (was ≤4500)
with **0** per-image `/preview-url` round-trips (was one per image). Tests green:
8 pytest (thumbnailer) + 5 vitest (DriveImageThumbnail) + attachment regressions.

## Problem (measured, not assumed)

Files → grid view scrolls sluggishly on normal (Windows) machines. Root cause
confirmed by driving Playwright + inspecting a user screen-recording:

- Grid renders `<img>` at a **114×114px** box.
- Actual stored images are **full-resolution originals** — sampled naturals:
  `4500×4500` (20 MP), `3084×4764`, `2776×4388`, `2834×3407`, ...
- One 4500×4500 image decodes to ~**81 MB** raw bitmap in RAM + a large GPU
  texture. 91 such cards on one page = **GBs of decode memory** + heavy
  compositor load → scroll jank + input lag.

Ruled out (all measured smooth): React re-render, dnd-kit, selection toggle,
IntersectionObserver. `0` long tasks, `17ms` p95 frame gap at 50 cards. The
jank is **raster/decode of oversized bitmaps**, not JS.

Secondary: each image also does a per-thumbnail `GET /preview-url` round-trip
before the `<img>` even starts, so thumbnails appear seconds behind the scroll
under the browser's 6-connection cap.

## Fix (decision: generate on upload + backfill)

Produce a small (~320px longest edge) JPEG thumbnail per image, stored as its
own object alongside the original, and serve THAT to the grid. Provider-agnostic
(S3+CloudFront and R2+CDN), CDN-cacheable, zero per-request cost. Matches the
existing `image_normalizer` upload-boundary pattern.

### Data model
- New column `attachments.thumbnail_path TEXT NULL` — stores the **CDN base URL**
  of the thumbnail object (unsigned, like `file_path`; signed on read). NULL =
  no thumbnail (non-image, or pre-backfill). Provider is the row's existing
  `storage_provider` — the thumb always lives in the same bucket as the original.
- Alembic migration `255_attachment_thumbnail_path` (down_revision `254_audit_trace_id`).

### Thumbnail generation (new `app/services/image_thumbnailer.py`)
- `generate_thumbnail(content: bytes, mime: str|None, *, max_edge=320, quality=80) -> bytes|None`
  - Returns a JPEG thumbnail (RGB, `Image.thumbnail` preserves aspect) or `None`
    when the bytes are not a decodable raster image (non-image files, PDFs, etc.).
  - Best-effort: any decode/encode failure returns `None` (never blocks upload).
  - Reuses Pillow (already a dep via image_normalizer).
- Thumb object key = `{original_key}.thumb.jpg` (deterministic, collision-free —
  original keys are already uuid-segregated).

### Upload wiring (`app/api/v1/resources/attachments.py :: create_attachment`)
Shared local helper `_maybe_store_thumbnail(backend, provider, s3_key, content, mime) -> str|None`:
- `gen = generate_thumbnail(content, mime)`; if None → return None.
- `backend.upload_file(gen, f"{s3_key}.thumb.jpg", content_type="image/jpeg")`.
- return `cdn_base_url(provider, thumb_key)`.
- Best-effort: wrap in try/except → warn + return None (a failed thumb must
  never fail the upload; grid falls back to original).

Call sites (both set `thumbnail_path`):
1. **Create** branch → set on `AttachmentCreate`.
2. **Replace-in-place** branch → set `existing_to_replace.thumbnail_path` (and
   overwrite the thumb object at the same `{key}.thumb.jpg`).

(Stock-list `.xlsx` path is not an image → no thumb. Bulk-import: audit whether
it routes through `create_attachment`; if it has its own upload, wire the same
helper. Backfill covers anything missed regardless.)

### Read / serve
Add signed `thumbnail_url` to the **drive-list** response so the grid needs
**zero** extra round-trip (kills both problems in one move):
- In `get_drive_contents`, for each file row: if `thumbnail_path` present, set
  `row["thumbnail_url"] = resolve_signed_url(thumbnail_path, provider=...)`.
  Signing is ~1.4ms each server-side (measured) → ~130ms for 91 rows, acceptable
  for a listing. Absent → omit (grid falls back to the existing per-image flow).
- Extend `/preview-url` with `?variant=thumb` (signs `thumbnail_path`, falls back
  to `file_path`) for any non-list consumer / detail use. Low priority but cheap.
- `DriveFileItem` (FE type) + `AttachmentResponse` (BE schema) gain
  `thumbnail_path` / `thumbnail_url` optional fields.

### Backfill (`scripts/backfill_attachment_thumbnails.py`)
- Scan `attachments` where `mime_type LIKE 'image/%' AND thumbnail_path IS NULL
  AND is_deleted = false`.
- For each: `download_file(extract_key(file_path))` → `generate_thumbnail` →
  `upload_file(...".thumb.jpg")` → set `thumbnail_path = cdn_base_url(...)`.
- Idempotent: skip rows already carrying `thumbnail_path` whose thumb object
  exists (JOIN-based "set where missing"). Re-runnable. Per-row try/except so one
  bad image doesn't abort the batch. Logs a dropped-count summary (no silent cap).

### Frontend
- `DriveImageThumbnail` accepts optional `thumbnailUrl`. When present: render it
  directly (still `loading="lazy"` + IntersectionObserver gate) and **skip**
  `getAttachmentPreviewUrl`. Add `decoding="async"` on the `<img>`. When absent:
  current behaviour (IO → preview-url of original) unchanged — safe fallback.
- `DriveGridView` / `DriveCard` pass `item.thumbnail_url` through.

## Tests (land in this phase)
- **pytest**: `generate_thumbnail` (image → small JPEG w/ max edge ≤320 & aspect
  kept; non-image → None; corrupt → None). `create_attachment` for an image sets
  `thumbnail_path` + uploads a `.thumb.jpg` object (mock backend). `get_drive_contents`
  returns `thumbnail_url` for image rows. `/preview-url?variant=thumb`.
- **vitest**: `DriveImageThumbnail` with `thumbnailUrl` renders `<img src>`
  pointing at the thumb and does NOT call the preview-url service; without it,
  falls back to the fetch path. `decoding="async"` present.
- **playwright/MCP**: grid loads; assert grid `<img>` `src` resolves to a
  `.thumb.jpg` object and `naturalWidth` ≤ ~320 for image cards (the regression
  guard for the whole fix).

## Verification target (the UAC line that matters)
After backfill, grid image `<img>.naturalWidth ≤ 320` for every image card
(was up to 4500). Scroll long tasks stay 0; decode memory drops ~1500×.

## Risk / rollback
- Additive column + additive object keys; no destructive change. Rollback =
  drop column + ignore `.thumb.jpg` objects (orphan bytes, harmless).
- Local dev has no CloudFront key → signing returns raw URL (same as today's
  `file_path`); thumbnail generation + dimensions still unit-verifiable.

## Self-grill (open assumptions)
1. **Why store, not on-the-fly?** Decided: on-demand still decodes the 20MP
   original server-side on first hit (moves the memory spike, adds CPU). Stored
   variant converges to the same but with zero per-request cost. ✅
2. **Thumb of a thumb / re-upload?** Key is deterministic `{key}.thumb.jpg`;
   replace overwrites in place. No orphans. ✅
3. **Non-square aspect at 114px square box?** `object-cover` already crops;
   `Image.thumbnail` keeps aspect so no distortion. ✅
4. **320px enough for retina at 114px?** 114 * 2 (dpr) ≈ 228 < 320 → sharp. ✅
5. **List signing cost** ~130ms/91 rows blocks the async loop briefly — a
   listing, acceptable; revisit with a threadpool if page-size 1000 is common.
