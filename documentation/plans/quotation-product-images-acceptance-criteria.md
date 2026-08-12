# UAC - Quotation product images (S21)

**Status:** Draft (pre-code) - **Classification:** CORE - **Domain:** project-sales / master data
**Plan:** `documentation/plans/PLAN-standard-products-images-and-recompute.md` (slice S21)
**Supersedes:** `documentation/plans/UAC-project-sales-pipeline.md` AC-E8 (both halves - see SUP below).

Tags: `[BE]` backend - `[FE]` frontend - `[T]` unit/service test.

---

## Journey

The salesperson is pricing a scope. They pick `CWC604-RL` off the catalogue and the row fills
itself: description, brand, unit, list price. **They are never asked which photograph of that
product the customer should see** - somebody already answered that once, on the product, and the
brochure prints the same one. The row simply shows it.

For most products, on day one, nobody has answered yet: 30 of 535 products with candidate photos
carry a choice. So the cell says so, in the words of the thing that is missing ("No photo chosen"),
and it is a link to the place where the answer is recorded. It never shows a broken image and never
shows a blank cell the reader has to interpret.

They issue. What went out is frozen: the customer's PDF and workbook show the photograph that was
chosen at the moment of issue, and re-downloading that revision next year shows the same one even
if the product's photo has since been re-chosen.

The customer never reads a word about our internal state. A line with no chosen photo prints an
empty cell, and a scope where nothing at all has been chosen prints no PRODUCT IMAGE column.

## Reference

`Cabana Elmina- nadi cergas R2.xlsx`, sheet `Quotation`, header row 20:
`ITEM | PRODUCT IMAGE | TECHNICAL SPEC | DESCRIPTION | BRAND | PRODUCT CODE | QTY | UNIT RATE (RM)
| COMPLETE SET`. 24 images, every one anchored in column B, at **24 distinct rows** - at most one
picture per line.

## Code anchors

`product_attachments.is_primary` (`app/models/product.py`, partial unique index
`uq_product_attachment_primary` on `(company_id, product_id) WHERE is_primary IS TRUE`) -
`project_quotation_lines.image_attachment_id` (`app/models/projects.py`) -
`project_quotation_pdf_service._scope_html` - `project_quotation_excel_service._write_scope` -
`InlineLineTable` / `QuotationVersionEditor` - `storage_router.resolve_signed_url` -
`attachments.thumbnail_path` (~320px).

---

## Group SUP - what this replaces

- **SUP-1** AC-E8's rule ("image-class attachment type, lowest `sort_order`") is **withdrawn**. It
  is the "whichever photo was linked first" fallback that `is_primary` exists to remove: for
  `SRTWC286-SH` the first-linked row is one of 31 files including a blank page and two other
  products' photographs. There is now exactly ONE image decision in the system and the quotation
  is its third consumer, after the brochure and 3D-model generation.
- **SUP-2** AC-E8's "an off-catalog line may upload its own" is **withdrawn**. An off-catalog line
  has no `product_id`, so there is no `product_attachments` row a flag could point at; a per-line
  upload would be a second place where "the picture of this thing" is decided, which is precisely
  the defect. Off-catalog lines never carry an image, on any of the three surfaces.

## Group RES - the resolver (one implementation, three consumers)

- **RES-1 `[BE][T]`** GIVEN a product with a `product_attachments` row where `is_primary IS TRUE`
  whose attachment is an image (`mime_type ILIKE 'image/%'`) and not deleted, THEN the resolver
  returns that attachment id.
- **RES-2 `[BE][T]`** GIVEN a product with candidate images but **none** flagged, THEN the resolver
  returns **no attachment** and reports `state = not_chosen` with the candidate count. It never
  falls back to the first-linked row, the lowest `sort_order`, or a filename match.
- **RES-3 `[BE][T]`** GIVEN a product with no image attachments at all (or only PDFs / only deleted
  files), THEN `state = no_photos`, `candidate_count = 0`.
- **RES-4 `[BE][T]`** GIVEN a line with no `product_id`, THEN `state = off_catalog` and no
  attachment, without a query being needed.
- **RES-5 `[BE][T]`** GIVEN a chosen image whose attachment row has since been deleted
  (`is_deleted`), THEN it is not returned - the product reads as not chosen, never as a broken
  link.
- **RES-6 `[BE][T]`** Resolving N lines costs a bounded number of queries (not one per line): a
  52-line scope must not issue 52 round trips.

## Group FRZ - freeze at issue

- **FRZ-1 `[BE][T]`** GIVEN an **editable** version, THEN the line's image is resolved LIVE from
  `is_primary` - choosing a product's photo makes it appear on every open draft without re-saving
  a single line.
- **FRZ-2 `[BE][T]`** WHEN a document is issued, THEN every line of every recorded version gets its
  chosen attachment id stamped onto `image_attachment_id`.
- **FRZ-3 `[BE][T]`** GIVEN an issued line with a stamped id, WHEN the product's chosen photo is
  changed afterwards, THEN the issue's PDF and workbook still render the stamped photo. What the
  customer holds does not move.
- **FRZ-4 `[BE][T]`** Re-issuing a revision that contributes the SAME version leaves the stamped
  ids untouched (idempotent), so R1 and R2 of an unchanged scope cannot disagree about a picture.

## Group PDF - the document

- **PDF-1 `[BE][T]`** GIVEN at least one line on a scope with a chosen photo, THEN that scope's
  table carries the `PRODUCT IMAGE` column and the picture is inlined as a data URI (no network
  fetch at render time, so a re-download is the same document).
- **PDF-2 `[BE][T]`** GIVEN NO line on a scope has a chosen photo, THEN that scope prints **no**
  `PRODUCT IMAGE` column. Judged per scope, not per document.
- **PDF-3 `[BE][T]`** GIVEN a scope that carries the column, a line with no chosen photo prints an
  **empty cell** - never a placeholder, never the words "no photo chosen". The document is
  customer-facing; our internal to-do list does not belong on it.
- **PDF-4 `[BE][T]`** Every embedded picture is downscaled to a bounded box before it is inlined. A
  52-line quotation of full-resolution product photographs (mean 1.1 MB in live data) must not
  produce a tens-of-megabyte PDF; the measured size is recorded in the test.
- **PDF-5 `[BE][T]`** Storage being unreachable degrades to a missing picture, never to a quotation
  that cannot be produced.

## Group XLS - the workbook

- **XLS-1 `[BE][T]`** GIVEN a scope with at least one chosen photo, THEN its sheet carries a
  `PRODUCT IMAGE` column and **the picture itself** is anchored over that line's cell in that
  column, matching the client's own workbook. (This reverses the earlier "filename, not picture"
  decision, whose stated reason - a floating drawing does not survive a sort - is real but is
  outweighed by the client showing us their file and asking for it.)
- **XLS-2 `[BE][T]`** The image cell's VALUE stays empty, exactly as in the reference workbook, so
  nothing shows through around the picture.
- **XLS-3 `[BE][T]`** The column collapses per SHEET when no line on that sheet has a chosen photo.
- **XLS-4 `[BE][T]`** The row is tall enough for the picture it carries; the sheet stays landscape
  and fit-to-one-page-wide.
- **XLS-5 `[BE][T]`** The workbook for a 52-line quotation stays a sane size; the measured size is
  recorded in the test.
- **XLS-6 `[BE][T]`** A picture that cannot be fetched or decoded leaves the cell empty rather than
  failing the export.

## Group API - contract

- **API-1 `[BE]`** `GET .../versions/{id}/lines` returns, per line, `product_image`:
  `{ state: 'chosen' | 'not_chosen' | 'no_photos' | 'off_catalog', url: string | null,
  filename: string | null, candidate_count: number }`. `url` is a **signed thumbnail** URL
  (`attachments.thumbnail_path` when present, the original otherwise), never a raw object key.
- **API-2 `[BE]`** `url` is populated only when `state = 'chosen'`.

## Group UI - the line table

- **UI-1 `[FE]`** The line table carries a `Photo` column immediately after `Item`, mirroring the
  printed order.
- **UI-2 `[FE]`** `state = chosen` renders the thumbnail, with the filename as its `title`.
- **UI-3 `[FE]`** `state = not_chosen` renders "No photo chosen" as a **link to the product's
  Attachments tab**, plus the candidate count - the thing that is missing, and the way to fix it.
- **UI-4 `[FE]`** `state = no_photos` renders "No photo on file", also linked, because the fix
  there is an upload rather than a click.
- **UI-5 `[FE]`** `state = off_catalog` renders a plain dash: there is no product, so there is
  nothing to choose and nothing to invite.
- **UI-6 `[FE]`** A row staged in the current edit session and not yet saved renders nothing in
  this column, the same rule the row's other server-decided facts (`Off-catalog`, `Below floor`,
  `Non-standard`) already follow.
- **UI-7 `[FE]`** No UUID is displayed. The product id appears only inside an href.
- **UI-8 `[FE]`** Usable at 375px and 1280px - the column takes a fixed width inside the table's
  own horizontal scroll, so it cannot widen the page.

## Group CHO - recording the choice

- **CHO-1 `[BE][T]`** `PUT /api/v1/master-data/product-attachments/{id}` with `is_primary: true`
  clears any other primary on the same product in the SAME transaction. Without this the partial
  unique index rejects the write, so "choose a different photo" would 500.
- **CHO-2 `[BE][T]`** Choosing a photo that is already chosen is idempotent (it stays chosen), and
  `is_primary: false` simply clears it.
- **CHO-3 `[FE]`** The product's Attachments tab offers "Use as product photo" on each IMAGE row
  (never on a PDF) and badges the chosen one. This is the SAME flag the brochure reads; it is not
  a second decision.
- **CHO-4 `[FE]`** The product EDIT form honours `?tab=`, so UI-3 / UI-4 land the user on the
  Attachments tab. The edit route rather than the detail page, because choosing is a write and
  the detail page is a read - it shows which photo was picked and offers no way to change it.
