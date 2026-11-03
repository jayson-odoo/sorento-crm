# PLAN: IMAGE-UNIFY - one image rendition service, one image component

Status: P0 (plan + behaviour card) written, waiting on owner answers (Q1-Q5 in
`behaviour-card-image-unify.md`). Track: LEAD, phased. P1 starts after #2126 merges. P2 after
#2101 (PRICETAG-SELF-APPROVAL) merges.

UAC: `image-unify-acceptance-criteria.md`. Behaviour card: `behaviour-card-image-unify.md`.

## Journey

Owner, 3 Nov 14:25: "Is #2126 using the same methodology as resource attachments and price tag
designer to retrieve and render images? Need to be unified so in future won't kena this again."

#2126 fixed one screen (the quotation spec sheet tab froze the browser on 165 MB of originals).
The same pattern - a screen asking for the ORIGINAL of a stored photo and painting it into a
small box - still lives on the Price Tag designer, preview and PDF, the attachment preview and a
dozen smaller sites. The journey: whoever builds the next screen that shows a stored photo has
exactly one way to do it, and that way sends a picture sized for the box.

## What exists today (verified against #2126 head 2875866ce6 and main 36bd6e6909)

### Backend: three resize routines, four caches

| What | Where | Notes |
| --- | --- | --- |
| Resize 1 | `image_thumbnailer.generate_thumbnail` (#2126 `app/services/image_thumbnailer.py:50`) | 320 px, q80, upright, white-flattened (the #2126 fix) |
| Resize 2 | `product_image_service._downscale` (#2126 `product_image_service.py:410`) | Same steps as resize 1 plus `max_pixels` guard and a `box` parameter. Used for the 240 px document copy, the 1024 px medium and the export cap |
| Resize 3 | `project_spec_sheet_service.prepare_export_images` (#2126 `:693`) | Calls resize 2 at the page cap (`export_cap_px`, `:679`, `EXPORT_DPI = 200` at `:56`) |
| Cache 1 (the one to keep) | `storage_router._signed_cache` (#2126 `storage_router.py:249`) | Thread-safe, TTL = a sixth of the URL life, bounded |
| Cache 2 | `product_image_service._url_cache` (`:322`) | Re-caches what cache 1 already caches |
| Cache 3 | `product_image_service._medium_cache` (`:485`) | Caches signed medium URL and 10 min miss |
| Cache 4 | `project_quotation_document_service._SIGN_PICTURES` (main `:1817`) | Data-URI cache for the sign page |

Naming: thumb = `<key>.thumb.jpg` stored in `attachments.thumbnail_path` (`app/models/resources.py:171`);
medium = `<key>.medium.jpg`, no column, existence checked with `file_exists` (`product_image_service.py:488,533`).

`store_thumbnail` is called from 7 upload sites: `entity_attachment_service.py:678`,
`catalogue_photo_service.py:176`, `form_comment_service.py:389`, `dealer_kit/asset_service.py:182`,
`tasks/import_tasks.py:957`, `public/portal.py:1732`, `product_image_service.py:620` (sign-page
fill-in). The single-file route in `attachments.py` reaches it through `entity_attachment_service`.

Old rows: `scripts/backfill_attachment_thumbnails.py` (manual, loads all rows at once, no throttle,
thumb only).

Uploads set `ContentType` only, no `CacheControl` (`r2_service.py:100,123`).

### Who asks for the original today

- Price Tag: `dealer_kit/product_images.py:182` (comment: "the FULL image ... printed tag at
  300dpi") and `dealer_kit/asset_service.py:250` sign `file_path`. Designer canvas loads them via
  `useHtmlImage.ts:34`; `TagSheetRenderer.tsx` `<img>` at :367 :481 :747 :812 :877, not lazy;
  Chromium prints them uncapped (`tasks/dealer_kit_export_tasks.py:213`, A4).
- Attachment preview: `attachments.py:668` signs the original; `AttachmentPreviewModal.tsx:433`.
- Chatbot/WhatsApp: `external/presigned_url.py:154`, `public/file_links.py` `_handout`.

### Frontend stored-image `<img>` sites (P3 inventory)

`DriveImageThumbnail.tsx:105` (lazy + fallback; the base for the shared component),
`AttachmentPreviewModal.tsx:433`, `QuotationSignScopes.tsx:101`, `CataloguePhotosGrid.tsx:79`,
`QuotationLinePhoto.tsx:69`, `QuotationLineFileCell.tsx:134,251`, `ShipmentLinePhotosCell.tsx:143`,
`ProductPhotoPopover.tsx:71`, `ProductCombosSection.tsx:366`, `TileGrid.tsx:67`,
`ProductPickerDialog.tsx:112,505`, `BrochureImageDialog.tsx:111`, `BrochureImagePicker.tsx:208`,
`AssetPickerDialog.tsx:160,218`, `ProductDataReviewDialog.tsx:172`, `ChatTranscript.tsx:380`,
`RespondChatList.tsx:389`, `TurnAttachments.tsx:79`, `POCrossCheckViewer.tsx:116`,
`POIntakeDocumentViewer.tsx:133`. Not stored images (left alone): local blob/data previews
(`AttachmentDropzone`, `AIExtractDialog`, `SharedConversationComposer`, `ChatbotConsole:699`,
`SignaturePad`), logos, flags, Metronic demo pages.

### Three things the crew comparison did not list

1. #2126 itself carries two copies of the same resize steps (`generate_thumbnail` and `_downscale`).
   P1 keeps `_downscale`'s signature (it has `box`, `max_pixels`, `draft`) and makes
   `generate_thumbnail` a one-line call to it.
2. Immutable caching needs immutable keys, and two writers break that: promotion uploads key by
   filename (`attachments.py:1030`, `promotion/{entity_id}/{original_filename}`), so a re-upload of
   the same name overwrites the object; `scripts/backfill_cmyk_attachments_to_rgb.py:111` rewrites
   originals in place. Both must regenerate renditions when they overwrite (P1), or a stale
   thumb/medium is served for a year from the CDN.
3. R2 grid thumbs are served UNSIGNED from the public CDN domain (`attachments.py:583-586`), on
   purpose (cache-stable URL). Keep as is; the security review in P1 states it explicitly. Note the
   consequence for caching: a signed URL changes every signature, so the browser cache only reuses
   a picture while `storage_router`'s cache hands back the same URL (10 min at the default hour).
   Long Cache-Control mainly helps the CDN edge and the unsigned R2 thumbs.

## Target

### Backend (P1): `image_thumbnailer.py` becomes the rendition service

One module, renamed in docstring only (file name kept, so imports stay):

```
RENDITIONS = {"thumb": 320, "medium": 1024}
rendition_key(original_key, size) -> "<key>.thumb.jpg" | "<key>.medium.jpg"
downscale(raw, box, quality, max_pixels) -> RenderedImage | None   # the #2126 _downscale, moved here; upright + draft always on
store_renditions(backend, provider, original_key, content, mime) -> thumb CDN base URL | None
rendition_url(row, size, expires_in) -> signed url    # thumb | medium | original; through storage_router.resolve_signed_url only
ensure_rendition(row, size) -> key | None             # on-demand fallback: make + store if missing, 10 min miss memo
print_copy(raw, unit_mm, dpi) -> RenderedImage | None # cap = ceil(long edge mm / 25.4 * dpi); within cap -> None (print original)
```

- Upload: the 7 `store_thumbnail` call sites call `store_renditions` (thumb + medium in one decode).
  `store_thumbnail` stays as an alias for one release so an in-flight merge does not break, then
  goes. A failed rendition never fails the upload (unchanged rule).
- Read: everything signs via `storage_router.resolve_signed_url` and its cache. Caches 2, 3 and 4
  go; cache 3's miss memo moves into `ensure_rendition` (one dict, bounded, same 10 min).
- Medium: no new column. The key is derived; `ensure_rendition` checks `file_exists` only on a
  memo miss. A column is not justified until a measured `file_exists` cost shows up (trigger named
  here).
- Cache-Control: rendition uploads send `public, max-age=31536000, immutable`. `upload_file` on
  both backends gains an optional `cache_control` argument; originals unchanged.
- Overwrites: the promotion route and the CMYK script call `store_renditions` after they replace an
  original, and new promotion uploads get an attachment-id segment in the key like every other
  entity (`attachments.py:1032` pattern).
- Backfill: `scripts/backfill_attachment_renditions.py` replaces the thumb backfill. Keyset-paged
  (id order, page 200), resumable via `--after <id>`, `--sleep` between files (default 0.2 s),
  `--limit`, `--dry-run`, one file decoded at a time, per-row try/except, summary line. Idempotent:
  skips a rendition whose object exists. Runs on the dev copy first, numbers posted on the PR, then
  owner decides the prod run (Q4).
- Guard (BE): a test that greps `app/` for `Image.open(` outside `image_thumbnailer.py` (allow-list:
  PDF/flyer readers that need full pixels, named in the test with a reason each).

### Frontend (P3, shared component lands with P2 since the designer needs it)

- `components/common/AttachmentImage.tsx`: `<AttachmentImage attachment size="thumb|medium|original" />`
  from `DriveImageThumbnail`: `loading="lazy"`, `decoding="async"`, fallback to the next size up on
  error, then to a placeholder. Takes the URLs the backend sends; it does not build URLs.
- Backend payloads that feed a picture carry `{thumb_url, medium_url, url}` (url = original) where
  today they carry one `url`. One shared serializer in the rendition service.
- `TagSheetRenderer` gets a rendition map (`attachment_id -> url`) built by the payload builder, so
  screen = medium and PDF = print copy, without the renderer knowing which.
- Guard (FE): an ESLint `no-restricted-syntax` rule on JSXOpeningElement `img` in
  `app/(protected)/**`, `app/(auth)/**`, `components/**` with an allow-list file for the non-stored
  sites above; plus a vitest that fails on a new `<img` outside the allow-list. The message points at
  `AttachmentImage`.

### Switches per phase

- P2 Price Tag: designer canvas + preview -> medium; tag-sheet PDF -> print copy made in the worker
  before Chromium starts (same flow as #2126's spec sheet export, generalised: manifest beside the
  export, missing entries print the original). DPI and unit per Q1.
- P3: attachment preview -> medium with "Open original" for zoom/download (Q3); sign page ->
  shared component (Q5); catalogue grid and the rest of the inventory -> `AttachmentImage`.
- P4 chatbot: per Q2 (recommendation: no change).

## Phases and DoD

| Phase | Size | Starts when | Customer/dealer visible |
| --- | --- | --- | --- |
| P0 plan + card | - | now | no |
| P1 rendition service, backfill, Cache-Control, guards | M | #2126 merged | no (renditions appear in storage only) |
| P2 Price Tag on renditions | M | P1 merged, #2101 merged, Q1 answered | yes: dealers' printed tags (Q1) |
| P3 preview, sign page, catalogue grid, rest | S each | P1 merged | sign page (Q5) |
| P4 chatbot | S or none | Q2 answered | customers, only if Q2 is (b)/(c) |

Done per phase: red-first tests and kill tests, reviewer, security review (signed URLs, cache
headers, public routes), crew perf + browser pass on a local prod-clone copy (bytes on open,
decoded memory, long tasks) before the owner hand test; owner hand test for P2 and any
customer-visible change.

## Tests (P1 list for the tester)

1. `downscale` is the only resize: `generate_thumbnail` output equals `downscale(box=320, q=80)`.
2. Upright: an EXIF-rotated JPEG comes out with width/height swapped; transparent PNG flattens white.
3. `store_renditions` writes `<key>.thumb.jpg` and `<key>.medium.jpg` with `Cache-Control:
   public, max-age=31536000, immutable` and `image/jpeg`; a non-image writes nothing and returns None.
4. Every one of the 7 upload sites produces both renditions (parametrised).
5. `ensure_rendition` makes a missing medium once; a second call does not download the original;
   an undecodable original is memoised as a miss for 10 min.
6. `rendition_url` signs through `storage_router` (spy): no other signer is called.
7. Removing caches 2-4 does not change the spec sheet or sign page outputs (the #2126 tests stay green).
8. Promotion re-upload of the same filename gets a new key; CMYK rewrite regenerates renditions.
9. Backfill: dry-run writes nothing; a run with `--limit 3` then a resume with `--after` finishes the
   rest with no file processed twice; a broken file is counted failed and the run continues.
10. Guard tests: a planted `Image.open` in a new module fails the BE guard; a planted `<img src={x.url}>`
    in a new component fails the FE guard.
