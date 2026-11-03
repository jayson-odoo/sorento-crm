# PLAN: IMAGE-UNIFY - one image rendition service, one image component

Status: P0 done; owner answered Q1-Q5 (3 Nov 14:35, recorded below); re-planned. P1 design settled,
P1 code that does not depend on #2126 is built (crew answer 3 Nov: P1 stacks on #2133):
`print_box_px` / `print_scale`, `single_flight`, `cache_control` on both backends,
`new_upload_storage_key`; `tests/test_image_unify_p1.py` 27 red on main, green here, 8 of 8
kill mutations red. The rest of P1 (rendition service on `_downscale`, cache removal, the 7
upload sites, BE guard) starts when #2126 merges. P2 after P1 and #2101 (PRICETAG-SELF-APPROVAL) merge. P4 closed
with no PR (Q2). Track: LEAD, phased.

UAC: `image-unify-acceptance-criteria.md`. Behaviour card: `behaviour-card-image-unify.md`.

## Owner rulings (3 Nov 14:35)

| Q | Ruling | Effect on the plan |
| --- | --- | --- |
| Q1 print size | "should be same size as what's designed": each photo's print copy is sized to the IMAGE LAYER's designed box (width x height mm at 300 DPI), never upscaled, aspect kept, fitted as the layer draws today (cover / contain / stretch, crop) | P2: print copy per layer box, not per tag or sheet |
| Q2 chatbot | Unchanged, originals | P4 closed, no PR |
| Q3 attachment preview | SAME AS TODAY, the original ("the attachment is the most stable so far"). Resource Attachments (thumb in grid, original on open) is the stable reference | P3 does not change the preview; it moves onto the shared component only with identical behaviour |
| Q4 prod backfill | NO backfill. Medium made at upload for new files and on demand the first time an old photo is opened; on-demand must be fast and safe: one generation per file under concurrency, cached after | P1: no backfill script; single-flight on-demand path |
| Q5 sign page | YES: every line's picture, 320 px thumbs loaded as the customer scrolls, no 60 cap; security review of the signed links | P3 |

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

One module (file name kept, so imports stay):

```
RENDITIONS = {"thumb": 320, "medium": 1024}
rendition_key(original_key, size) -> "<key>.thumb.jpg" | "<key>.medium.jpg"
downscale(raw, box, quality, max_pixels) -> RenderedImage | None   # the #2126 _downscale, moved here; upright + draft always on
store_renditions(backend, provider, original_key, content, mime) -> thumb CDN base URL | None   # upload path
ensure_renditions(rows, size, release=None, wait_seconds=RENDITION_WAIT_SECONDS) -> {attachment_id: key}   # on-demand, single-flight
rendition_urls(rows, size, ...) -> {attachment_id: signed url}   # ensure + sign; thumb | medium | original; storage_router only
print_box_px(width_mm, height_mm, dpi=300) -> (w_px, h_px)
print_scale(src_w, src_h, box_px, fit, crop) -> float <= 1   # see "Print copy" below
```

- **Upload:** the 7 `store_thumbnail` call sites call `store_renditions` (one decode: medium from
  the original, thumb from the medium). `store_thumbnail` stays as an alias for one release so an
  in-flight merge does not break, then goes. A failed rendition never fails the upload.
- **Read:** everything signs via `storage_router.resolve_signed_url` and its cache. Caches 2, 3 and 4
  in the table above go.
- **No new column.** Keys are derived. Existence is known from the single-flight memo below.
- **Cache-Control:** rendition uploads send `public, max-age=31536000, immutable`. `upload_file` on
  both backends gains an optional `cache_control` argument; originals unchanged.
- **Overwrites:** the promotion route and the CMYK script call `store_renditions` after they replace
  an original; new promotion uploads get an attachment-id segment in the key like every other
  entity (`attachments.py:1032` pattern).
- **No backfill (Q4).** `scripts/backfill_attachment_thumbnails.py` stays as it is (existing ops
  tool, not run by this lane); no rendition backfill is written.
- **Guard (BE):** a test that greps `app/` for `Image.open(` outside `image_thumbnailer.py`
  (allow-list: PDF/flyer readers that need full pixels, named in the test with a reason each).

### On-demand path (Q4): one generation per file, cached after

Old files get their medium (and a missing thumb) the first time a screen asks. This runs in the
API request path, so it must be bounded.

1. **Positive memo, per process.** `(provider, key, size) -> exists`, bounded dict. A hit skips
   storage entirely and goes straight to signing (which `storage_router` caches). Safe without a TTL:
   a rendition is only ever replaced by a regenerated one under the same key (overwrite rule above).
2. **Miss memo**, 10 min, for files that cannot be decoded or are over the pixel ceiling (moved from
   #2126's `_medium_cache`). A miss falls back to the thumb, then to a placeholder, never the original.
3. **Existence check** on a memo miss: `file_exists(rendition_key)`; present -> memo, done.
4. **Single-flight, in process:** a dict of `key -> threading.Event` under one lock. The first caller
   generates; concurrent callers in the same process wait on the event.
5. **Single-flight, across processes** (blue/green API, worker): `SET image-rendition:<provider>:<key>
   <owner> NX EX 120` in Redis (`REDIS_URL`, already used by RQ). The winner downloads the original
   once, writes thumb and medium, deletes the lock (only if it still owns it). A loser polls for the
   lock to clear (250 ms steps) inside its wait budget, then re-checks existence. Redis down:
   generate anyway. A duplicate write is identical bytes under the same key, so the worst case is
   wasted work, never a wrong picture.
6. **Bounded work:** generation runs on a process-wide pool of 2 threads (worst case 2 x ~160 MB for
   a 40 MP PNG), after the DB connection is handed back (`release`, as in #2126). A request waits at
   most `RENDITION_WAIT_SECONDS` (8 s) in total. Pictures not ready by then come back as their thumb
   URL; their generation keeps running and the next open gets the medium.
7. **Pixel ceiling** stays `_downscale`'s 40 MP (`product_image_service.py:82`). PNGs cannot
   draft-decode; over-ceiling files are logged by attachment id and miss-memoised.

### Print copy (Q1): sized to the image layer's designed box

The PDF prints each photo from a copy made in the worker before Chromium starts (#2126's manifest
flow, generalised from the spec sheet export to the tag-sheet export). The copy is per export, not
a stored rendition, because its size depends on the layer.

- Layer box at 300 DPI: `Bw = ceil(width_mm / 25.4 * 300)`, `Bh` likewise. The layer's `width_mm`,
  `height_mm`, `fit` (`cover | contain | stretch`) and normalised `cropRect` are what the designer
  and `TagSheetRenderer` already draw from (`KonvaTagLayer.tsx:123-126,471`, `lib/dealer-kit/image-crop.ts`).
- Source pixels the layer shows: `cw = W * crop.width`, `ch = H * crop.height` (whole image when no crop).
- Scale the renderer applies: cover `max(Bw/cw, Bh/ch)`; contain `min(Bw/cw, Bh/ch)`; stretch
  `max(Bw/cw, Bh/ch)` (the sharper axis). Print copy = original scaled by `min(1, scale)`: never
  upscaled, aspect kept. The crop is normalised, so it stays valid on the smaller copy.
- One photo used by several layers or tags in one export: the largest scale wins, one copy.
- A photo already within its box prints from the original; a failed copy prints from the original
  (never a blank), exactly as #2126's spec sheet export.
- Example: a product photo 4000 x 3000 in a 40 x 30 mm contain box -> box 473 x 355 px -> copy
  473 x 355; the 29 MB SRTBF11833 _2.png in the same box becomes a few tens of kB.
- **Spec sheet export uses the same rule** (it prints through the same `TagSheetRenderer` and
  layers). Today it caps at the PAGE's long edge at 200 DPI (`export_cap_px`); the layer rule at 300
  DPI is never softer for any layer and smaller for almost all. One rule for every printed page.

### Frontend

- `components/common/AttachmentImage.tsx` (P3): `<AttachmentImage thumbUrl mediumUrl url size="thumb|medium|original" />`,
  built from `DriveImageThumbnail` (lazy, `decoding="async"`, fallback down to the thumb, then a
  placeholder). It takes URLs the backend sends; it never builds one.
- Payloads that feed a picture carry `{thumb_url, medium_url, url}`; one serializer in the rendition
  service.
- Price Tag (P2): `tag_sheet_export_service.design_media` (`:430`) is already the ONE resolver behind
  the PDF payload, the portal preview and the CRM design preview, returning `images` (product
  photos by attachment id) and `assets`. It gains `size`: screens ask for medium, the PDF payload
  reads the print-copy manifest. `TagSheetRenderer` and `useHtmlImage` keep drawing whatever URL the
  map holds, so neither knows which size it got.
- Guard (FE, P3): ESLint `no-restricted-syntax` on JSX `img` in `app/(protected)/**`, `app/(auth)/**`,
  `components/**` with an allow-list of the non-stored sites above, plus a vitest that fails on a new
  `<img` outside the allow-list. The message points at `AttachmentImage`.

### Switches per phase

- **P2 Price Tag:** designer canvas + previews -> medium (product photos first,
  `dealer_kit/product_images.py:182`, then library assets `asset_service.py:250`); tag-sheet PDF and
  spec sheet PDF -> print copy per layer box.
- **P3:**
  - Resource Attachments: grid thumb and preview original stay exactly as today (Q3). `DriveImageThumbnail`
    becomes `AttachmentImage size="thumb"` and the preview modal `size="original"` only if every
    existing test and a browser pass show identical behaviour; otherwise they stay untouched and
    are allow-listed.
  - Sign page (Q5): every line's picture, 320 px thumb, lazy, no 60 cap. The page no longer inlines
    data URIs (cache 4 goes). Each picture is `GET /public/quotation-sign/{token}/pictures/{attachment_id}`,
    which checks the token, checks the attachment is a picture of THIS issue, runs the on-demand
    thumb path, and answers 302 to a short-lived signed URL. Lazy loading then drives generation:
    only pictures the customer scrolls to are made. Security review covers the route (token scope,
    attachment-belongs-to-issue, rate limit, link lifetime, no original ever reachable).
  - Catalogue photos grid and the rest of the inventory -> `AttachmentImage`.
- **P4:** closed, no PR (Q2).

## Phases and DoD

| Phase | Size | Starts when | Customer/dealer visible |
| --- | --- | --- | --- |
| P0 plan + card | - | done | no |
| P1 rendition service, on-demand single-flight, Cache-Control, overwrite fixes, BE guard | M | #2126 merged | no |
| P2 Price Tag designer/preview on medium, PDFs on layer-box print copies | M | P1 and #2101 merged | yes: dealers' printed tags, spec sheet PDF |
| P3 sign page, catalogue grid, rest, `AttachmentImage` + FE guard | S each | P1 merged | yes: customers see every picture on the sign page |
| P4 chatbot | - | closed (Q2) | no |

Done per phase: red-first tests and kill tests, reviewer, security review (signed URLs, cache
headers, Redis lock, public routes), crew perf + browser pass on a local prod-clone copy (bytes on
open, decoded memory, long tasks, first-open time with no renditions) before the owner hand test;
owner hand test for P2 and P3's sign page.

## Tests (P1 list for the tester)

1. `downscale` is the only resize: `generate_thumbnail` output equals `downscale(box=320, q=80)`.
2. Upright: an EXIF-rotated JPEG comes out with width/height swapped; transparent PNG flattens white.
3. `store_renditions` writes `<key>.medium.jpg` and `<key>.thumb.jpg` with `Cache-Control:
   public, max-age=31536000, immutable` and `image/jpeg`, decoding the original once (spy on
   `Image.open`); a non-image writes nothing and returns None; a storage failure does not fail the upload.
4. Every one of the 7 upload sites produces both renditions (parametrised).
5. On-demand: a missing medium is made once; the next call neither downloads the original nor calls
   `file_exists` (positive memo).
6. Single-flight in process: 8 threads asking for the same missing medium -> exactly one download
   and one upload; all 8 get the same URL.
7. Single-flight across processes: with the Redis lock held by another owner, the caller does not
   download, waits, and returns the URL once the object appears; when the budget lapses it returns
   the thumb URL. Redis unavailable -> generation still happens.
8. Budget: with generation slowed past `RENDITION_WAIT_SECONDS`, the call returns thumbs on time and
   the medium exists after the background work finishes.
9. Undecodable / over-ceiling original: miss-memoised for 10 min, falls back to the thumb, never the
   original URL.
10. `rendition_urls` signs only through `storage_router` (spy): no other signer is called.
11. Removing caches 2-4 does not change the spec sheet or sign page outputs (#2126 tests stay green).
12. Promotion re-upload of the same filename gets a new key; CMYK rewrite regenerates renditions.
13. BE guard: a planted `Image.open` in a new module fails it.
14. `print_scale` (lands in P1 as a pure function, used in P2): cover/contain/stretch, with and
    without crop, never above 1; table-driven from the examples above.
