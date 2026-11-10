# PLAN: QUOTE-DESC-RICHTEXT (rich text line description on proposals / quotations)

Status: Build (red tests and implementation pushed on the card's recommendations; owner answers pending). Track:
LEAD pattern, size M. No migration, no auth / RBAC change. PR #2304.

Owner ruling, 10 Nov ~14:30 MYT: "the description should use rich text editor also to allow styling".
Behaviour card (rules, readers table, questions): `CARD-quote-desc-richtext-10nov.md`.

## Slices

1. Server save rule: `app/utils/tag_rich_text.py` `sanitise_description` (rich -> price tag allow-list; plain kept
   as typed; unstyled edit -> plain lines; empty -> null). Called once in `_write_line`
   (`services/project_quotation_service.py`), which every line write path goes through.
2. PDF: `_description_html` in `services/project_quotation_pdf_service.py` re-sanitises and wraps styled text in
   `<div class="rt">` for both the plain and the matrix scope tables; `.rt` CSS keeps paragraphs tight.
3. Plain readers: `line_text(line)` in `project_quotation_service.py` (= `plain_text`), used by Excel, price-change
   alert, amendment feedback rows, SO draft (both component paths), PO check, sample request, spec sheet, the
   re-ask report label. Guard test: no other module reads `description_snapshot` raw.
4. FE: `components/common/RichDescription.tsx` (plain as typed, styled via `RichTextView`, never innerHTML);
   `QuotationLinesGrid.tsx` DescriptionCell = trigger + popover with the shared `RichTextEditor` (full toolbar);
   labels / line search read plain (`richOneLine` / `richPlainText`); sign page `QuotationSignScopes.tsx` draws
   `RichDescription`, feedback label plain.

## Tests

- `sorento_crm_backend/tests/test_quotation_line_description_rich.py`
- `QuotationLinesGrid.description.test.tsx`, `QuotationSignScopes.richDescription.test.tsx`
