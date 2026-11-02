# PLAN: Project spec sheet from templates (PS-SPEC-SHEET)

**Status:** Waiting (built provisionally ahead of mock approval; owner reviewing mock v2; security PASS, reviewer re-check of round 2, cloud browser pass done, crew browser pass pending). No merge until the mock is approved. Track: L (one
migration, new public print payload branch, new tab). PR #2103. UAC:
`ps-spec-sheet-02nov-acceptance-criteria.md`. Card: `CARD-ps-spec-sheet-02nov.md`.

## Journey

Project sales sends the customer's QS a PROJECT CATALOG: a picture cover, then one landscape page per
quoted item (photo, drawing, code and spec bullets, its valve / hose / trap, and a title block with
the project, ref, area, salesperson and date). Today it is built by hand in PowerPoint. The owner:
"Reuse our price tag mechanism ... we need the template design also."

## Shape (simplest thing that works)

- The pages ARE tag templates (two new families), designed in the existing editor. The PDF is the
  existing tag-sheet print page and renderer: the backend builds a `TagSheetDoc` with one full-page
  placed "tag" per sheet and the rows the slots and merge fields read. No second renderer, no
  second editor, no new export table.
- Prints an ISSUED revision (`quotation_issues` -> `quotation_issue_scopes` -> lines), like the
  quotation PDF.
- Settings: ONE JSONB column `projects.quotation_documents.spec_sheet` (migration
  `pss_0001_spec_sheet`), keyed by item (product id / `set:<id>`) so they survive revisions.
- Export: a `user_downloads` row of kind `quotation_spec_sheet_pdf` (source = the issue), queued on
  `catalogue_render`; the public print payload route answers it by kind. The render CLI gains
  `--width-mm/--height-mm`; the A4 tag sheet command is unchanged.

## Backend

- `app/services/project_spec_sheet_service.py`: `settings_of`, `save_settings` (template family +
  published check, row checks), `issue_for`, `pages`, `build_print_payload`, `request_export`,
  `print_payload_for_download` (company scope pinned to the document's company).
- `app/api/v1/projects/spec_sheet.py`: GET / PUT `.../quotation-documents/{id}/spec-sheet`, GET
  `/preview`, POST `/export`. Reads = project read; PUT = edit + write access.
- `tag_sheet_export_service.resolve_tag_sheet_print_payload`: dispatch on download kind.
- `dealer_kit_export_tasks.generate_spec_sheet_pdf`, `_render_pdf(size_mm=)`,
  `catalogue_render_cli.pdf_options`.
- Spec registry: `is_accessible` (Yes/No) after `is_rimless`.

## Frontend

- Tag template types: families `spec_cover` / `spec_page` (`SPEC_SHEET_FAMILIES`,
  `isSpecSheetFamily`), slot `drawing`, `TagLayer.show_when`, spec sheet row fields
  (`brand`, `drawing`, `area`, `comment`, `marker`, `doc`, `strict_parts`).
- `product-block.ts`: `layerShownFor`, `drawingOf`, strict parts (missing part = empty product).
- `merge-fields.ts`: "Spec sheet" field group.
- Editor: `specSheet` flag (Accessory 1..3 subjects, "Show only when"), Drawing slot option; price tag
  editors do not offer the Spec sheet group; `listPublishedTemplates` drops spec families.
- Quotation document: "Spec sheet" tab (`QuotationSpecSheetTab`), service `specSheetService.ts`,
  hooks `useSpecSheet.ts`.

## Owner answers on mock v3 (2 Nov 23:29)

Q-A (a), Q-B (b): rows carry the quoted unit price in `list_price` (+ `parent_list_price`), so the price tag
designer's List Price slot and list-only price badge print it; set parts carry none; a picked accessory
carries its own line's price; the tab's API never returns it. Q-C (a): fixed layers repeat (already so).

## Deferred, with their triggers

- Shrink-to-fit text for the long project title: the first real title that does not fit its box.
- Per-product default page template (#2100 links): when two item kinds need different layouts on
  one sheet.
- Brand on price tags (`{{product.brand}}` for price tags): the first price tag that asks for it.
- "2 of 3 accessories fit this template" on a row (card edge case): needs the template's accessory
  row count read off its layers. Today the extra accessories simply do not print. Trigger: the
  first item with more accessories than its template has rows.

## Coordination

- PS-PROPOSAL-QUOTATION (#2097): `make_quotation` should copy `spec_sheet` (told on #2097).
- PRICETAG-TEMPLATE-PER-PRODUCT (#2100): excludes `spec_` families server side (done on #2100).
- QUOTE-COVER-DESIGN (#2094): no overlap (A4 letter cover vs. 16:9 catalogue cover).
