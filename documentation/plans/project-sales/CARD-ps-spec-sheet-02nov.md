# CARD: PS-SPEC-SHEET v2 (2 Nov 2026)

**Status:** Build (answers in). Track: L.

**Crew answers on v1 (dfd2f5be), 2 Nov:** Q1 (c) a free marker per page (crew asks the owner what the stars
mean, non-blocking). Q2: offer both `{{doc.your_ref}}` and `{{doc.quotation_no}}` (same `quotation_no()` as
`cover_reference`, `BE/services/quotation_cover_service.py:31-36`); `{{doc.ref}}` is (a) and the default
template prints it. Q3: (a) set parts + (c) hand-pick; NOT (b) position grouping (owner: no implicit
matching). Q4 (a) free-text comment, blank prints an empty box. Q5 (a) add an `is_accessible` spec key next
to `is_rimless`. Sample Q7: no product code starts with BBT; print the line's code as quoted.
**Owner answers on mock v3 (2 Nov 23:29):** Q-A (a) the right band shows the project details; Q-B (b) an
optional price area shows the quoted unit price of the issued revision, a template without one prints none
(built through the price tag's own List Price slot / price badge, rows carry `list_price`); Q-C (a) any fixed
area anywhere repeats on every page. "Reuse the price tag designer as much as possible" (reuse table on the PR).
#2100 already excludes families starting `spec_` from product links (`NON_PRICE_TAG_FAMILY_PREFIX`).
Track: L (one migration, new template families, new print payload, new document tab).

Owner, 2 Nov ~21:05: "the spec sheet needs to follow the PDF that I shared (R1 - C2 - PROJECT CATALOG).
Reuse our price tag mechanism ... They have a cover page, then they put each product in each template,
so we need the template design also."

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend`. Code read on origin/main 46de2f6d77.
The owner's PDF is not in the repo (public repo); its layout is described by page type only.

## The sample, in one paragraph

36 landscape pages, 338.7 x 190.5 mm (16:9). Page 1 is a cover: one photo collage and the brand logo,
no text. Pages 2-36 are one product each: photo (left), dimensioned drawing (centre), a text block
(brand + code, name, 3-6 spec bullets), 0-2 accessory rows (small photo + code + 1-3 lines), an optional
badge on the photo (rimless, accessible), and on the right a title block: project description,
`REF :`, `AREA :`, `PREPARED BY :` name + phone, `DATE :`, `COMMENT :` (empty box), company logo under it.
No prices, no page numbers. Two layouts: "with accessories" (19 pages) and "single item" (16 pages).

## How it works today (facts)

- **Templates**: `TagTemplate` (`BE/models/dealer_kit.py:705`) holds a layer doc in mm of any size
  (`FE/lib/dealer-kit/tag-template-types.ts:377-381`), draft + published versions (`:733`,
  `TagTemplateVersion` `:764`). `family` is a free string server side (`BE/schemas/price_tag.py:777`), so
  a new family is a FE list entry (`tag-template-types.ts:338-367`), no migration.
- **Editor**: `TagCanvasEditor` (`FE/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor.tsx`)
  with image / text / shape / badge / group layers, slot bindings, `{{merge fields}}`
  (`FE/lib/dealer-kit/merge-fields.ts:42-119`) and a per-layer subject `subjectPart`
  (`FE/lib/dealer-kit/product-block.ts:74-90, 189`) that points a layer at part N of a line.
- **Print**: the worker renders `/c/print/tag-sheet/{download_id}` in Chromium
  (`BE/tasks/dealer_kit_export_tasks.py:76-110, 186-240`), which draws `TagSheetDoc.sheets[]`, one PDF page
  per sheet, through `TagSheetRenderer` (`FE/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer.tsx:1041-1146`).
  The payload comes from `GET /public/print/tag-sheet/{download_id}` (`BE/api/v1/public/print.py:122-158`)
  -> `resolve_tag_sheet_print_payload` (`BE/services/dealer_kit/tag_sheet_export_service.py:391-546`):
  `doc`, `resolvedData` keyed by tag id, signed `assets` / `images`, `fonts`. Page size is hard-coded A4
  portrait (`dealer_kit_export_tasks.py:202-205`); the render CLI takes a paper name only
  (`BE/tasks/catalogue_render_cli.py:25-50`).
- **Quotation lines**: an issued revision = `quotation_issues` + `quotation_issue_scopes` (scope, version)
  (`BE/models/projects.py:1225, 1473`); lines `quotation_lines` (`:1630-1700`). Issue freezes a photo AND
  the first drawing onto every product/set line (`freeze_version_images`,
  `BE/services/project_quotation_image_service.py:270-330`, called at `project_quotation_document_service.py:600`).
- **Grouping**: a WC + angle valve + hose is ONE line today when quoted as a product set: its parts are
  frozen in `set_parts_snapshot` with an `is_driver` flag (`BE/services/project_quotation_service.py:555-598`).
  The old A/B/C `item_label` is no longer typed (`project_quotation_pdf_service.py:118-130`). Plain
  "components at zero after the priced parent" lines also exist (`project_quotation_pdf_service.py:134-140`).
- **Document fields**: `your_ref`, `doc_date`, `signatory_name`, `signatory_phone`, `document_no`
  (`BE/models/projects.py:1106-1130`); `Project.title` (`:256`).
- **Exports**: the quotation's queued exports create a `UserDownload` with `source_entity_type
  ='quotation_issue'` and enqueue a task (`BE/api/v1/projects/quotation_documents.py:884-950`); the file
  lands in My Downloads.
- **Not here**: Area, a per-page comment, a drawing slot, conditional badges, custom page size.

## Rules (recommended answers in place)

1. **Where it lives**: a **Spec sheet** tab on every quotation document page (proposal or quotation, per
   PS-PROPOSAL-QUOTATION #2097: same `quotation_documents` row with `kind`), beside Header / Lines /
   Cover letter / Terms / Signatures (`.../[documentId]/components/QuotationDocumentTabs.tsx:31-40`).
2. **What it prints from**: an ISSUED revision (default the latest; a picker lists the others). Same
   doctrine as the quotation PDF: what the customer received. A document with no issue shows the empty
   state "Issue a revision first" and no export.
3. **Pages**: page 1 = the cover template. Then one page per ITEM, in quotation order (scope order, then
   line order), unless the salesperson reorders them on the tab.
4. **Item** = one quotation line with a product or a set. A set line prints its driver part as the main
   item and the other parts as accessory rows (the frozen `set_parts_snapshot`). Nothing is grouped by
   position (Q3). Free-text lines (no product, no set) print nothing.
4a. **Hand-picked accessories** (Q3 c): on a page row, "Accessories" picks other items of the same
   revision; a picked item prints as an accessory row of that page and no longer gets a page of its own.
   Set parts come first, hand-picked after. Unpicking gives the item its page back.
5. **Same product twice** (two scopes, or a line repeated): ONE page, at its first position. Key = product
   id, else `set:<set id>` (sample: 35 pages, 35 different codes).
6. **Templates**: two new families, `Spec sheet cover` (`spec_cover`) and `Spec sheet page`
   (`spec_page`), designed in the existing Dealer Kit > Tag templates editor. The tab picks a cover
   template, a "with accessories" page template and a "single item" page template (defaults to the first
   one; the single-item pick is optional and falls back to the other). Only published templates are
   offered. These families are hidden from the price tag request designer and its template picker.
7. **Page size** = the cover template's size; every page template must have the same size or export
   refuses with "Page templates must be the same size as the cover". The sample's 338.7 x 190.5 mm is
   simply the size the designer gives the templates (Q5 of the owner list: no fixed A4).
8. **New fields a template can place** (Insert field, new group "Document"): `{{doc.project_title}}`,
   `{{doc.ref}}` (Your ref, else quotation no), `{{doc.your_ref}}`, `{{doc.quotation_no}}`, `{{doc.prepared_by}}`, `{{doc.prepared_by_phone}}`, `{{doc.date}}` (`02 NOV 2026`),
   `{{line.area}}`, `{{line.comment}}`, `{{line.marker}}` (Q1 c), and `{{product.brand}}`. Cover and page templates both get them.
9. **Accessory rows**: layers pointed at part 1 / part 2 (the editor's existing subject picker). On a
   spec page a layer pointed at a part the item does not have draws NOTHING (today it falls back to the
   parent, which would print the main item twice).
10. **Drawing**: a new image slot `Drawing`: the line's frozen drawing; for an accessory, its product's
    first "Technical Specifications" file. No drawing = empty (the sample's photo-only pages).
11. **Badges**: an image layer can carry "Show only when spec <key> is Yes" (Rimless `is_rimless`,
    `BE/services/product_spec_registry.py:284`; new Accessible `is_accessible`, Q5).
12. **Area, Comment and Marker**: typed per page on the tab, free text, saved on the document and keyed by item
    (rule 5), so they survive a new revision and the proposal -> quotation copy. Upper-cased at print.
    The Area input suggests the areas already typed on this spec sheet.
13. **Hide**: a page can be hidden from the spec sheet (e.g. a consumable) without touching the quotation.
14. **Export**: "Export PDF" queues a render (worker, `catalogue_render` queue); the file arrives in My
    Downloads as `spec-sheet-<quotation no>.pdf`. Nothing prints a price.
15. **Who**: anyone who can read the project sees the tab and exports; saving areas / order / templates
    needs the same right as editing the quotation (projects edit + write access to the project).

## Storage (one migration)

`projects.quotation_documents.spec_sheet` JSONB NULL:
`{cover_template_id, page_template_id, single_page_template_id, issue_id, rows: [{key, area, comment, marker, hidden, accessories: [key]}]}`
in page order. A key not in `rows` (a new line in a later revision) is appended in quotation order. No new
table: one document has one spec sheet, and its settings are read and written together.

## Real examples (dev data)

Thin: crew reports the dev DBs hold only 13 / 7 quotation lines, so there is no real 35-item catalogue to
test against. No product code starts with `BBT`. The browser pass uses the best real project crew can
point at, with a set line (WC set: pan + angle valve + hose) to exercise the accessory rows, and says it is
thin.

## Edge cases

- An issued line whose product was deleted: prints from the line's snapshot (code, description, frozen
  photo / drawing); specs and brand blank.
- An item with 3+ accessories and a template with 2 accessory rows: the first two print. (The row hint
  "2 of 3 fit" is deferred, see the plan.)
- A template unpublished after it was picked: the tab shows "Pick a template" and export refuses (422).
- The project title longer than its box: clipped at the box (the designer sets the font size, the sample
  uses ~7 pt). Shrink-to-fit is NOT built; trigger: the first real title that does not fit.
- Two documents on one project (proposal and quotation): each has its own spec sheet; making a quotation
  copies the proposal's `spec_sheet` (PS-PROPOSAL-QUOTATION `make_quotation` copies one more column).

## Owner's 7 questions on the sample

| # | Question | Answer |
|---|---|---|
| 1 | Red `*` / `**` / `***` after codes? | **Asked (Q1).** |
| 2 | REF source? | **Asked (Q2).** |
| 3 | Area free text or a list? | Decided: free text per page with suggestions from this sheet (rule 12); no area master exists and the sample mixes lists ("UNIT & PODIUM FACILITIES"). |
| 4 | Cover: collage only or project fields? | Decided: the cover is a template; the designer places whatever fields they want (rule 8). The sample's design is collage + logo. |
| 5 | 16:9 or A4 landscape? | Decided: the template's own size is the page size (rule 7); 16:9 works as drawn. |
| 6 | Lines from the quotation or a separate list? | Decided: from the issued revision (rules 2-5) with per-page Area / Comment / Hide / order. Grouping detail **asked (Q3)**. |
| 7 | `BBT` codes real? | Data check asked on the PR; until answered the page prints the line's code as quoted. |

## Questions (max 5, each with a recommendation)

- **Q1 Markers.** (a) not printed; (b) `*` when the line is flagged non-standard (`is_non_standard`);
  (c) a free marker typed per page. **Recommend (c)**: the meaning is not in the data, and a free field
  beside Area costs nothing.
- **Q2 REF.** (a) the quotation's "Your ref" when filled, else our quotation number with revision;
  (b) always our quotation number; (c) typed per spec sheet. **Recommend (a)**: the sample's ref looks
  like the customer's own, and an empty Your ref still prints something traceable.
- **Q3 Accessories.** (a) set parts only; (b) set parts + zero-priced product lines right after a priced
  line; (c) picked by hand per page. **Recommend (b)**: both are how the team quotes a WC with its valve
  and hose today; (c) can come later if (b) groups wrongly.
- **Q4 Comment.** (a) free text per page, printed in the box; (b) always an empty box (sample).
  **Recommend (a)**: empty prints as the sample does.
- **Q5 Accessible badge.** (a) add a Yes/No spec "Accessible (OKU)" to the spec registry, filled in
  master data; (b) skip the accessible badge for now. **Recommend (a)**: one registry entry, and the
  badge rule (rule 11) then works for both icons.

## What this lane touches that others also touch

- PS-PROPOSAL-QUOTATION (#2097): `quotation_documents` (new column), the document tabs, and
  `make_quotation` should copy `spec_sheet`. I add the tab and the column; they add the one copy line (or
  I do if mine merges second).
- QUOTE-COVER-PAGE / QUOTE-COVER-DESIGN (#2088, #2094): no overlap. Their cover is the quotation's
  letter-style page 1 (WeasyPrint, portrait rows). The spec sheet cover is a picture page drawn by a tag
  template; reusing their form designer would mean a second designer for pictures. Not building a second
  cover system: the spec cover IS a tag template.
- PRICETAG-TEMPLATE-PER-PRODUCT (#2100): template <-> product links. Spec families must not be offered
  as a product's price tag template; I filter them out of the request designer source, they should filter
  the product link picker the same way.
- Price tag print pipeline: `TagSheetRenderer`, `merge-fields.ts`, `product-block.ts`, the render CLI
  (custom size flag). Additive only; price tag output must not change (kill tests on the existing suites).
