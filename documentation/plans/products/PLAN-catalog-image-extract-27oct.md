# PLAN: Catalogue image extraction (CATALOG-IMAGES)

Status: Build (mock v2 approved 27 Oct 19:19). Track: full.
Lane moved local 27 Oct (CATALOG-IMAGES-L, same PR #1923, branch claude/catalog-images-9kwphh).
Track: full (new upload/ingest surface, migration for the extraction rows, master-data writes).

Owner ask (27 Oct 2026, verbatim): "i got this code that reads pdf like [catalogue page] and turns it into
images with their proximity product code as the file name, i want to generalize this and have this
capability in our system". The owner's script is reproduced at the bottom of this file.

## Journey

Upload a catalogue PDF. The system extracts each product photo, finds the product code(s) near it by
layout, and matches them against the product master. A review grid shows each photo with its thumbnail,
page, matched codes and confidence, plus an unmatched bucket. The user confirms, reassigns or skips each
photo. Confirmed photos attach to products as product images through the existing attachments model.
Re-uploading a newer catalogue never duplicates an image (hash) and lets the user replace the old one.

## Scout (measured, file:line)

**What already exists. Most of the pipeline does.** The Dealer Kit "flyer reading" already uploads a
catalogue PDF, reads it on the worker and matches its printed codes to the master. It deliberately
SKIPS product photos ("a product's picture comes from the product master at render time"). This lane
adds the step that takes those photos INTO the master.

| Need | Already in the code | Reuse? |
| --- | --- | --- |
| PDF library | `PyMuPDF>=1.24` `sorento_crm_backend/requirements.txt:44`, `pillow` `:28`, opencv `:45` | yes, no new dependency |
| PDF upload + refusals (not a PDF, encrypted, 0 pages) | `flyer_extraction.extract_flyer` `app/services/dealer_kit/flyer_extraction.py:248` | yes |
| Size limit | `MAX_UPLOAD_BYTES = 50 MB` `app/services/dealer_kit/flyer_reading_service.py:95`, `assert_within_limit` `:166`, `assert_pdf_mime` `:232` | yes, same 50 MB ceiling |
| Background job | own RQ queue `flyer_read` `flyer_reading_service.py:105`, 15 min timeout `:109`, staged bytes `:618`, task `app/tasks/flyer_read_tasks.py:69` | yes, same queue (no new worker config) |
| Placed images, cropped to the paper | `_visible_rect` / `_crop_of` `flyer_extraction.py:502,518`; full-bleed exemption `_covers_the_page` `:540` | yes |
| "This picture belongs to a code" (on it / beneath it / above it) | `_belongs_to_a_card` `flyer_extraction.py:554`; gaps `PHOTO_CODE_GAP_PT` `:104` | yes, inverted: today it drops these, this lane keeps them |
| Extract + CMYK to RGB + re-encode | `_artwork_image` `flyer_extraction.py:618` via `ensure_rgb_image` (`app/services/image_normalizer.py`) | yes, ALWAYS re-encode here (security: no original bytes stored) |
| Code finder | `CODE_PATTERN = ^(?:SRT|FG-)...` `flyer_extraction.py:72` | NO for this lane: supplier catalogues do not print SRT. Owner's broader shape `^[A-Z]{3,}\d{3,}[A-Z0-9\-]*$` finds candidates; the MASTER decides what is a code |
| Match codes to products in company scope (bulk, ORM so the company filter applies) | `_products_by_code` `app/services/dealer_kit/flyer_matching.py:283` | yes |
| "Did you mean" suggestion (pg_trgm, shown never applied) | `_suggestions` `flyer_matching.py:369`, floor 0.40 `:54` | yes |
| Supplier code -> our product | `supplier_product_code_alias` `app/models/scm.py:1352` | yes, one extra rung |
| Product image link | `product_attachments` `app/models/product.py:497` (`is_primary`, `sort_order`, unique (product, attachment) `:525`, one primary per product `:533`) | yes, the target table |
| The file row | `attachments` `app/models/resources.py:115` (`file_hash` sha256, `thumbnail_path`, `storage_provider`) | yes |
| Upload bytes + thumbnail | `storage_router` + `store_thumbnail` (as in `app/api/v1/resources/attachments.py:1000-1010`) | yes |
| Create the link | `ProductService.create_product_attachment` `app/services/product_service.py:3250` (idempotent on re-post) | yes |
| Which photo IS the product | `product_image_service._resolve` `app/services/product_image_service.py:216`; `choose` `:470` | read it, see trap below |
| Review UI | `app/(protected)/dealer-kit/flyer-readings/[readingId]/page.tsx`, `components/MatchReportSections.tsx`, `ReportSection.tsx`, `AdoptCodeDialog.tsx` | yes |
| Permissions precedent for a flyer step that writes the master | `_WRITE_THE_MASTER = master_data.products.edit` `app/api/v1/dealer_kit/flyer_readings.py:88` | yes |

**Trap found (drives question 3).** `product_image_service._resolve` (`:216-221`): a product with ONE
photo and no `is_primary` shows that photo automatically. 2,060 of 2,308 products with photos are in
that state (module docstring `:16`). Adding a second, unchosen photo flips the product to `NOT_CHOSEN`,
and the brochure tile, the project quotation and 3D generation then show NO picture. So a naive "attach
to gallery" quietly removes about 2,000 products' pictures from customer documents.

**Owner's script vs. what the system has learnt (why not port it 1:1).**
- `get_image_rects(xref)[0]` keeps only the first placement of a reused image. The flyer code walks
  `get_image_info` per placement, so a set photo placed twice is read twice.
- The script saves the raw, uncropped image. The flyer code crops bleed to the paper (AC-F2 there).
- Its regex is the only filter, so a heading like `ABC1234` becomes a product. Here the master decides.

## Behaviour card (rules)

- **R1 Photos.** Every image placed on a page is a candidate. Skipped: under 40pt on either side (icons,
  logos, badges: owner's threshold), full-page backgrounds (`_covers_the_page`), and banners across the
  top. Each kept photo is cropped to the visible area, converted to RGB and re-encoded with Pillow:
  PNG when it has transparency, JPEG q90 otherwise.
- **R2 Block.** A photo's block is the caption printed directly beneath it in its column (owner's rule:
  caption below the image centre, x within the image, nearest wins). Codes printed ON the photo also
  count. Every code-shaped token in that caption is a block code, in printed order.
- **R3 Match ladder**, first rung that answers wins, all in the active company:
  1. exact `products.product_code`;
  2. normalised (uppercase, spaces and dots dropped);
  3. suffix-tolerant, unique only: `SRTW5112` printed vs `SRTW5112-MW` in the master (or the other way
     round). Two candidates means no match plus a suggestion;
  4. `supplier_product_code_alias`;
  5. otherwise unmatched, with a pg_trgm suggestion shown, never applied.
  Confidence: High = rung 1. Medium = rungs 2-4. Low = suggestion only. None.
- **R4 Placeholders.** A token with underscores (`SRTWB_____`) is a placeholder, never matched, and is
  shown as such.
- **R5 Dedupe.** sha256 of the stored (re-encoded) bytes. A photo whose hash is already linked to the
  product reads "Already on file" and is pre-skipped. Re-reading the same PDF proposes nothing new.
- **R6 Nothing is written until Confirm.** Confirm acts on the ticked rows only. Skip is remembered for
  that reading.

## Examples (from the owner's example page as described in the brief; the real PDF is pending)

| # | On the page | Proposed |
| --- | --- | --- |
| E1 | One set photo above a caption with `SRTBF12613` (cabinet), `SRTWB...` (basin), `SRTW2600` (pop-up waste), dims, material, `LP: RM 999` | Photo -> `SRTBF12613`, High. `SRTWB...` and `SRTW2600` are listed as "also in this block" (Q2) |
| E2 | A caption whose basin code is the red placeholder `SRTWB_____` | Placeholder shown, never matched; the cabinet still names the photo |
| E3 | A block whose first code is not in the master | Goes to the Unmatched bucket with the nearest code as a suggestion; the user reassigns via the product search or skips |
| E4 | Two photos above one caption (front + open view) | Both proposed for the same code, as `SRTBF12613` and `SRTBF12613 (2)` |
| E5 | Brand logo, certification icons, page banner | Not shown at all (R1) |

## Questions for the owner (one crew-ask)

1. **Where it lives.** (a) As a "Product photos" section on the existing flyer reading review, reusing
   its upload, worker and matching. (b) A new standalone Products > Catalogue photos page. Rec (a):
   about two-thirds of the pipeline already ships there. A supplier catalogue is uploaded the same way.
2. **Multi-code block.** (a) The photo goes to the FIRST code only (the cabinet, as your script does),
   with the other codes shown as untick-by-default "also attach". (b) Attach to every code in the
   block. Rec (a): a set photo on the basin's own page is the wrong-product-photo risk
   `product_image_service` exists to stop.
3. **Main image vs gallery.** (a) Gallery. A product with no photo gets it as its picture, and a product
   whose single photo shows today has that old photo pinned as main, so no brochure or quotation
   changes. (b) The catalogue photo always becomes main. Rec (a), because of the 2,000-product trap.
4. **Who may confirm.** (a) Upload/review: `dealer_kit.page.edit`. Attach: also
   `master_data.products.edit` (the precedent for applying a printed size). (b) Only
   `master_data.products.edit` for everything. Rec (a).
5. **Newer catalogue, different photo.** (a) A "Replace" tick per row, default ON only when the old
   photo came from an earlier catalogue import (manual photos are never replaced). The old link is
   removed through the deferred-action unlink. (b) Always keep both. Rec (a).

## Owner answers (27 Oct ~19:15) and Lavish feedback on mock v1 (27 Oct 19:06)

- **Q1** Not on the flyer reading. It goes on the PRODUCT page, as one action in the existing Action
  dropdown. The flyer extraction and matching code is reused underneath.
- **Q2 (a)** The photo goes to the first code. The other block codes are "also attach" ticks, default off.
- **Q3** No main-photo choice or label anywhere: the photo is simply added as one of the product's photos.
  Today's display must not change: a product whose single photo shows automatically
  (`product_image_service.py:216`) keeps showing it. Done behind the scenes (the existing single photo
  is pinned when a second one arrives), with no new words in the UI.
- **Q4 (a)** Upload and review need `dealer_kit.page.edit`; Attach also needs `master_data.products.edit`.
- **Q5 (a)** A Replace tick per row, AND an image comparison: a likely duplicate of an existing photo
  (compared by the image, not only sha256) is flagged and the user picks "Keep both" or "Replace" per row.
- **Feedback F1** "Will this link to the attachments linking? Does it bypass the n8n sending route?":
  answered plainly in the mock v2 ask, with file:line.
- **Feedback F2** "Download all as ZIP" of the extracted photos, named by code, so the user can rearrange
  them outside.
- **Feedback F3** Reuse the existing folder and file function so the user can drop photos into folders.
- **Feedback F4** About a quarter of the photos were already uploaded by hand, so sha256 will not catch
  them (different bytes). Flag likely duplicates by comparing the images, show both thumbnails side by
  side as "Looks like an existing photo", user decides. Measure how many it flags on the real catalogue.

## Baseline on the real catalogue (27 Oct, read-only; PDF never in git)

`Sorento_Lite_DIY_CATALOG_UPDATE_22062026.pdf`, 32 pages, matched against the 15 Oct dev copy
(`sorento_cagent_stack`, read-only; it has no `supplier_product_code_alias`, so the alias rung is n/a).
Scratch evidence: `<scratchpad>/baseline/REPORT.md`, `REPORT2.md`.

| Run | Photos | First code exact | Suffix | Unmatched | No caption |
| --- | --- | --- | --- | --- | --- |
| Owner's script | 428 saved | 327 named | - | 101 UNMATCHED | - |
| R1-R3 with the owner's code regex | 462 | 265 | 18 | 73 | 106 |
| Fixed code rule + wrap join | 462 | 370 | 0 | 0 | 92 |
| ... + skip wide bands and inline (no-xref) images | 434 | 344 | 0 | 0 | 90 |

Findings that change the contract:
- The owner's regex misses this catalogue's DIY codes: under 3 digits or a hyphen in the prefix
  (`SRT73-*-DIY` p4, `SRT-FH12-*` p6, p13, p16), so those photos took the NEXT row's caption. Codes also
  wrap over two lines (`SRTKT1931SS` / `-BL-DIY`, p11), so the first line gave a truncated code.
- 14 full-width "feature" bands (p9, p10, p18, p21-p25: icons + text, e.g. "High Quality Material") are
  inline images with no xref, sitting mid-page, so the top-banner rule keeps them and the proximity rule
  hands them a product code. Skipping any placement at least 80% of the page wide removes exactly
  those and no product photo. The 3 narrow no-xref placements left (p15) are decorative too.
- The only non-code the new rule catches is `SUS304` (material, p11, p21); not in the master.
- 344 photos map to 161 products; 147 of them already have photos (92 have 1, 51 have 2, 4 have 3).
  Nothing matches by sha256 (0), as expected: the photos were uploaded by hand from other files.
- 121 photos share their first code with another photo on the same page (colour variants, hero shots
  taking a caption). The review grid is where a person sorts these out.
- E1 (multi-code block) and E2 (placeholder) do not occur in this DIY catalogue; they come from the
  owner's example page only.

Contract changes (rules R1, R2; tester adds red cases before the coder starts):
- Code-shaped token = owner's shape OR a hyphenated token containing a digit:
  `^[A-Z]{3,}\d{3,}[A-Z0-9\-]*$`, `^[A-Z][A-Z0-9]*\d[A-Z0-9]*(?:-[A-Z0-9]+)+$`,
  `^[A-Z]+(?:-[A-Z0-9]+)*-[A-Z0-9]*\d[A-Z0-9]*(?:-[A-Z0-9]+)*$`. `MDF18`, `ABC12`, dimensions and
  prices stay out.
- Wrap join: inside a caption block, a line whose first word starts with `-` is glued onto the previous
  line's last word.
- R1 also skips a placement at least 80% of the page wide anywhere on the page, and an inline image
  with no xref.

## F1 answer (for the owner)

Yes. Attach writes the same `product_attachments` link a hand link writes
(`ProductAttachmentService.create_product_attachment`, `product_service.py:3250`). The chatbot reads
that table (MCP `crm_master_product_attachments_list`, `sorento_crm_mcp/catalog.py:179` ->
`product_attachments.py:150` -> `product_service.py:2872`), so an attached photo is sendable by the bot
at once. Sending is unchanged: bot -> n8n sender -> Respond.io (`chatbot/turn/compose.py:1067`,
`chatbot/direct_ingress.py:330-373`). What it skips is n8n's INTAKE: a hand upload fires the n8n
"attachment uploaded" webhook (`resources/attachments.py:1096` -> `attachment_webhook_helper.py:40`),
and n8n's linking comes back through `/external/product-attachments` (`external/__init__.py:100`).
Here the review does that linking. The bot picks photos by the "Product Photos" attachment type
(`chatbot/lanes/business/answer.py:3878`), so catalogue photos are stored with that type.

## Build (mock v2 approved 27 Oct 19:19: reuse components, pagination, simple guided UI)

UAC: `catalog-image-extract-acceptance-criteria.md`. Q6-Q9 on the lead's recommendations; Q10 (b).

### Slices (one coder kept alive; tester writes each slice's red tests first)
- S0 Phase 1 FE against mocks (no BE): Actions item, upload dialog, review page.
- S1 pure modules green (red tests at a60ca09181, e8082d2d5b) + `dhash`.
- S2 migration, models, service, worker task, API (red tests from the tester first).
- S3 FE wired to the API; vitest for the touched hooks/components.
- S4 reviewer + security-reviewer (upload) + browser pass + hand test.

### Data (migration `cim_0001_catalogue_photos`, down_revision = main's head at build time)
- `catalogue_photo_readings`: id, company_id (scoped like `flyer_readings`), file_name, file_size,
  status (`queued | reading | ready | failed`), page_count, photo_count, error, pdf_attachment_id (FK
  attachments; the PDF is stored in the folder and the task reads it back), directory_id (FK the
  folder), created_by, created_at, updated_at.
- `catalogue_photos`: id, reading_id (FK cascade), page, position, attachment_id (FK attachments, the
  stored photo), sha256, dhash (16 hex), printed_code, block_codes (JSON list), placeholders (JSON list),
  product_id (FK products, nullable: proposed or picked), rung, confidence, suggestion,
  also_attach_product_ids (JSON list), duplicate_of_attachment_id (FK attachments, nullable),
  duplicate_distance, decision (`attach | skip | keep_both | replace`), attached_at.
- Default decision: `skip` when a look-alike exists (Q7 a), else `attach`.
- Tabs: duplicate = `duplicate_of_attachment_id IS NOT NULL`; ready = product set, no look-alike,
  decision `attach`; needs_product = no product, decision != `skip`; skipped = decision `skip` and no
  look-alike. To attach = product set, decision in (`attach`, `keep_both`, `replace`), not attached.

### API `/api/v1/master-data/catalogue-photo-readings`
- `POST` (multipart `file`): `dealer_kit.page.edit`. Size and mime through `assert_within_limit` /
  `assert_pdf_mime` (`flyer_reading_service.py:166,232`); refusals of `extract_flyer` for bad PDFs.
  Creates the folder + stores the PDF + a JobService job (as `products.py:389`) + enqueues on the
  `flyer_read` queue. 201 with the reading.
- `GET /{id}`: reading + `counts {ready, duplicate, needs_product, skipped, to_attach}` + directory id.
- `GET /{id}/photos?tab=&page=&limit=&sort=&dir=`: DataGrid list shape; sort keys `page` (default, then
  position), `printed_code`, `product_code`, `confidence`. Item: id, page, position, thumbnail_url,
  image_url, printed_code, block_codes, placeholders, product `{id, product_code}` | null, rung,
  confidence, suggestion, other_block_products `[{id, product_code}]`, also_attach_product_ids,
  duplicate `{attachment_id, thumbnail_url, distance}` | null, decision, attached_at.
- `PATCH /{id}/photos/{photo_id}` `{product_id?, decision?, also_attach_product_ids?}`: product must be
  in scope (404); `keep_both`/`replace` only with a look-alike (422); an attached row is 409.
- `POST /{id}/attach`: `dealer_kit.page.edit` AND `master_data.products.edit`. Per row: pin a lone
  auto-shown photo first (AC-14), skip when `already_on_file` (AC-16), `replace` unlinks the look-alike
  link only, then `ProductAttachmentService.create_product_attachment` (`product_service.py:3250`) for
  the product and each also-attach product; sets `attached_at`. Returns `{attached, replaced, skipped,
  products}`. Re-running adds nothing.
- ZIP: the existing `POST /resource-management/attachments/bulk-download` on the folder
  (`attachments.py:1366`); no new endpoint.

### Worker task (`flyer_read` queue)
`extract_catalog_photos` -> store each photo (re-encoded bytes, `store_thumbnail`, type "Product
Photos" when it exists, NO `create_and_send_webhook`) -> `match_codes` on all block codes (product =
first block code's match; other matched codes = also-attach choices) -> look-alike check: `dhash` of the
photo vs the dhash of each existing image linked to the proposed product (its thumbnail bytes through
`storage_router`), flagged at Hamming distance <= 10 -> rows. A failure sets status `failed` + error.

### FE (reuse only)
Actions item in `ProductsList.tsx:990-1039`; the existing upload dialog; review page
`/master-data-management/products/catalogue-photos/[id]` with `PageHeader`, `WizardSteps`
(`components/common/WizardSteps.tsx`), line `Tabs`, one `DataGrid` per tab (server-side, fixed layout,
resizable columns), `SearchableSelect` product picker, `Badge` confidence; "Download all as ZIP" opens
the existing `AttachmentBulkDownloadDialog`; "Open folder" links to the drive view.

## Phase 2 contract, answer-independent part (red tests written now, crew 27 Oct)

None of the five questions changes these. They are pure functions plus one read-only DB lookup, so they
stand whether the screen ends up on the flyer reading (Q1 a) or on its own page (Q1 b).

`app/services/dealer_kit/catalog_photos.py` (pure, no DB):

- `extract_catalog_photos(data: bytes) -> list[CatalogPhoto]`. Same refusals as `extract_flyer`
  (`flyer_extraction.py:248`): not a PDF -> `ValueError`, encrypted -> `EncryptedFlyerError`.
- `CatalogPhoto` (frozen dataclass): `page: int` (1-based); `rect: tuple[float, float, float, float]`
  (the visible placement on the page, in pt); `block_codes: list[str]` (every code-shaped token of the
  caption, printed order, placeholders excluded); `placeholders: list[str]` (R4 tokens of that caption);
  `image_bytes: bytes`; `mime: str` (`image/jpeg` or `image/png`); `sha256: str` (hex of `image_bytes`);
  `width: int`, `height: int` (pixels of `image_bytes`). Property `primary_code` = `block_codes[0]` or None.
- Code-shaped token: owner's shape `^[A-Z]{3,}\d{3,}[A-Z0-9\-]*$` on whitespace-split caption words,
  trailing `,;:.` stripped. Placeholder token: letters then a run of 3 or more underscores (`SRTWB_____`).
- R1: one `CatalogPhoto` per PLACEMENT (an image placed twice is two photos). Skipped: placement under
  40pt on either side; a placement covering the page (`_covers_the_page`); a banner (width >= 80% of the
  page, touching the top). Kept photos are cropped to the visible part of the page, RGB, re-encoded:
  PNG when the source has an soft mask, JPEG q90 otherwise. Never the source stream bytes.
- R2: the caption is chosen with the owner's rule (its first code line sits below the photo's centre,
  its x0 within [photo.x0 - 20, photo.x1], nearest by `(y0 - cy) + 0.5 * |x0 - photo.x0|`). A photo with
  no caption is still returned, with `block_codes == []` (it lands in the Unmatched bucket).
- Order: page, then top-to-bottom, then left-to-right.

`app/services/dealer_kit/catalog_photo_matching.py` (DB, read-only, ORM so company scope applies):

- `match_codes(db, codes: list[str]) -> dict[str, CodeMatch]`, one entry per input code.
- `CodeMatch` (frozen dataclass): `code` (as printed); `rung` in `exact | normalised | suffix | alias |
  none`; `product_id: str | None`; `product_code: str | None`; `confidence` in `high | medium | low |
  none` (exact = high; normalised/suffix/alias = medium; none with a suggestion = low; else none);
  `suggestion: str | None` (a product_code, only when `rung == "none"`, never applied).
- Rungs as R3. Suffix: unique only, either direction (`SRTW5112` printed vs `SRTW5112-MW` in the master,
  or the other way round); two candidates -> `none` with a suggestion. Alias: a
  `supplier_product_code_alias` row with this `supplier_code` and a non-null `product_id`, unique product.
  A product under another company never matches.
- `already_on_file(db, product_id: str, sha256: str) -> bool`: True when a `product_attachments` row of
  that product links an attachment whose `file_hash == sha256` (R5).

Lead rulings on the tester's questions (27 Oct): the caption is the whole text block that holds the
anchor line (codes mid-line and on later lines count, unlike the owner's first-code-only `anchors()`);
"nearest wins" applies among captions in the same x window; an alias row of another company never
matches (company scope, like products); normalising drops every space and dot (`"bf.126 13"` ->
`BF12613`); a row with `company_id = NULL` belongs to the active company, as in the flyer tests.

Tests: `tests/test_catalog_photo_extraction.py` (fixture PDFs built with PyMuPDF in the test, as
`tests/_flyer_pdf.py` does), `tests/test_catalog_photo_matching.py` (Postgres, `tests/_pg_fixture.py`).

## Owner's script (27 Oct, verbatim)

```python
import pymupdf, re, sys, os
CODE = re.compile(r"^[A-Z]{3,}\d{3,}[A-Z0-9\-]*$")   # e.g. SRTBF11834, SRTW5112-MW

def anchors(page):
    """First code of each product block = a code word whose block starts with it."""
    out=[]
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines",[]):
            t=" ".join(s["text"] for s in l["spans"]).strip()
            w=t.split()[0] if t else ""
            if CODE.match(w):
                out.append((w, pymupdf.Rect(l["bbox"])))
                break                     # only the first code line in a block
    return out

def match(img_rect, codes):
    cx=(img_rect.x0+img_rect.x1)/2; cy=(img_rect.y0+img_rect.y1)/2
    best=None
    for code,r in codes:
        if r.y0 < cy: continue                 # caption must sit below image centre
        if not (img_rect.x0-20 <= r.x0 <= img_rect.x1): continue
        d=(r.y0-cy)+abs(r.x0-img_rect.x0)*0.5
        if best is None or d<best[0]: best=(d,code)
    return best[1] if best else None

def run(pdf, outdir):
    os.makedirs(outdir, exist_ok=True)
    doc=pymupdf.open(pdf)
    for pno,page in enumerate(doc):
        codes=anchors(page)
        seen={}
        for xref,smask,*_ in page.get_images(full=True):
            rects=page.get_image_rects(xref)
            if not rects: continue
            r=rects[0]
            if r.width<40 or r.height<40: continue          # skip icons/logos
            code=match(r,codes) or f"p{pno+1}_x{xref}_UNMATCHED"
            pix=pymupdf.Pixmap(doc,xref)
            if pix.colorspace and pix.colorspace.n==4:      # CMYK -> RGB
                pix=pymupdf.Pixmap(pymupdf.csRGB, pix)
            if smask: pix=pymupdf.Pixmap(pix, pymupdf.Pixmap(doc,smask))  # keep transparency
            n=seen.get(code,0); seen[code]=n+1
            name=code if n==0 else f"{code}_{n+1}"
            pix.save(f"{outdir}/{name}.png")
            print(f"p{pno+1} xref{xref} {pix.width}x{pix.height} -> {name}.png")
if __name__=="__main__": run(sys.argv[1], sys.argv[2])
```

### Lead rulings on the S2 tester's questions (27 Oct)
- Task seam `process_catalogue_photo_reading(reading_id, _db=None)` as the flyer task; the route enqueues
  through `app.services.queue_service.enqueue_job` (looked up at call time), `queue_name="flyer_read"`,
  `args == (reading_id,)`.
- Bodies snake_case. Photos list `{"data": [...], "pagination": {"total": ...}}`. PATCH 200. Attach
  `products` = count of distinct products touched; `skipped` = rows not linked because the same bytes are
  already linked to that product (AC-16). Decision-`skip` rows are not counted there.
- Upload refusals happen in the request: non-PDF 400, encrypted 400, over 50 MB 413; no rows left.
- Every route, GETs included, needs `dealer_kit.page.edit` (owner Q4 a); Attach also needs
  `master_data.products.edit`.
- `counts` also carries `attached` (rows with `attached_at`), so the Attach step reads as done after a
  reload (S0 coder note). The coder adds a test for it; existing assertions are not edited.

### Lead rulings on the S1/S2 coder's notes (27 Oct)
- The reading detail carries a top-level `attached_count`; `counts` keeps its five keys (two tests pin it).
- A replaced row counts in `replaced` only. Toast: "Attached {attached + replaced} photos to {products}
  products. {replaced} replaced, {skipped} already on file."
- The stored PDF keeps a bare storage key in `file_path` (every reader goes through `extract_key`).
- Extra column `catalogue_photos.other_block_products` (JSONB). A human pick sets rung `manual`, High.
- `tests/test_company_scope.py` owned-table tripwire 170 -> 171 for `catalogue_photo_readings`.
- Test copies upload to the staging R2 bucket (`sorento-crm-staging`, lane `.env`), and the look-alike
  check reads existing photos from that same storage, so on a test copy a photo whose bytes are not in
  staging is simply not compared (no failure). The look-alike count at the hand test is therefore a lower bound.

## Fix round 1 (27 Oct): security review, reviewer (NOT READY), browser pass

Each item gets a red test first (tester), then the fix (coder). Existing assertions are not weakened.

Security
- FR-1 (blocker) Every Attachment and AttachmentDirectory the lane creates carries the reading's company:
  the request stamps `resolve_write_company_id(get_company_scope(db))` (as `resources_service.py:121-124`,
  `asset_service.py:200-210`), the worker stamps `reading.company_id`. Another company cannot see the
  folders or files (drive list, search, bulk download).
- FR-2 Worker caps: skip a placement or soft mask over 40M pixels (`npa_xlsx.py:27` precedent, checked
  from `get_image_info` / the smask Width x Height before decoding); refuse a PDF over 300 pages; stop at
  2,000 photos per reading (status failed, fixed message). One photo per placement stays.
- FR-3 `reading.error` holds a fixed plain message, never exception text (log the exception). Codes are
  truncated to 120 characters before they are stored. The queue failure message names no host.
- FR-4 A PATCH that changes `product_id` recomputes the look-alike for the new product (clears it when
  none, or when the check fails) and resets the decision to the default. `replaced` counts deleted rows only.
- FR-5 `catalogue_photo_readings.company_id` NOT NULL; the worker fails closed on a reading without one.
- FR-6 `also_attach_product_ids` capped at 50 (422 above).
- FR-7 Signed URLs only (drop the unsigned `or path` fallback); `stored_filename` cut to 255; the folder
  name strips `-->` as well as `/`.

Reviewer
- FR-8 (blocker) "Download all as ZIP" sends the reading's folder (`folderIds: [directory_id]`). The source
  PDF is stored in the root "Catalogue photos" folder, not in the per-catalogue folder, so the ZIP holds
  photos only.
- FR-9 (blocker) The upload creates a JobService job (as `products.py:389`) so the reading appears in the
  upload-activity drawer and links to the review page; the worker's photos never appear in that feed as
  their own "Processing" rows (`upload_activity.py:76,288-300`).
- FR-10 The Product column sorts (`accessorFn`).
- FR-11 Replace of the product's chosen (primary) photo makes the new link primary, so the product never
  loses its picture.
- FR-12 Look-alike speed: dhash per existing attachment cached for the run; each photo hashed once.
- FR-13 A failed read deletes the files it uploaded (best effort) and the task has a status guard: a
  re-delivered job for a reading that is not queued does nothing.
- FR-14 Attached rows read "Attached" on every tab, the look-alike tab included.
- FR-15 `already_on_file` ignores deleted attachments.
- FR-16 Placeholders shown on every tab where the photo appears; indexes on `catalogue_photos.attachment_id`,
  `product_id`, `duplicate_of_attachment_id`; `datetime.now(timezone.utc)`; replace unlinks through the
  product attachment service if it has no side effects beyond the delete.

Browser pass
- FR-17 Upload dialog hint shows once ("PDF only, up to 50 MB"); the dialog has a description for
  assistive tech (no aria warning).
- FR-18 The real 16.6 MB catalogue uploads on the test copy without the 500. Cause (measured): the Next dev
  rewrite proxy forwards a request body only up to 10 MB (`next/dist/server/body-streams.js:30`,
  `experimental.middlewareClientMaxBodySize`); a larger body is never forwarded and the proxy 500s at
  `proxyTimeout` (`next.config.mjs:32`). The backend takes the full POST in 4.8 s. Fix: `experimental.
  middlewareClientMaxBodySize: "60mb"` (50 MB ceiling plus multipart overhead). Production sits behind its
  own reverse proxy without these rewrites (`next.config.mjs:54-57`); its body limit is not in this repo
  (UNVERIFIED, the 50 MB flyer upload already relies on it).

## Fix round 2 (27 Oct): reviewer READY, security NOT CLEAN on one should-fix

Kill-proof round 1 (reviewer, `git archive` copy): FR-1, FR-9 (job and feed exclusion), FR-8 FE all went
red when broken and green when restored.

- FR-19 (security should-fix) The 2,000-photo cap stops the extraction itself: `extract_catalog_photos`
  takes the limit and stops decoding at limit + 1, so a PDF placing one image thousands of times never
  decodes them all. Each (xref, crop) is re-encoded once per run and reused. A soft mask whose size cannot
  be read is skipped, not decoded.
- FR-20 The final commit of a read sits inside the failure path, so a failed commit also deletes the files.
- FR-21 `thumbnail_url` / `image_url` are `string | null` in the FE type; a missing thumbnail renders an
  empty box, never an `<img>` without a source.
- FR-22 "Download all as ZIP" passes the folder as `directoryId` too, so the ZIP is named after the catalogue.
- FR-23 `CATALOGUE_MAX_PAGES` declared once; `CatalogueReadError` sits with the other classes.
- Known and accepted: Replace calls `delete_product_attachment`, which commits before the new link is made;
  a crash between the two is recovered by re-running Attach, but the handed-over primary flag is then lost
  (rare, and Attach shows the product's photos as they are).
- Test copy DB: crew held the migration SQL (`SET NOT NULL` counts as destructive), so the shared dev DB
  lacks the NOT NULL and the three indexes. Owner approval (`crew migrate --approved`) before the hand test.
