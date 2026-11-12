# UAC: Quotation cover page fields and sales cover sheet layout (QUOTE-COVER-FIELDS)

Plan: `PLAN-quote-cover-fields-10nov.md`. Owner rulings 10 Nov 2026 (~14:55, ~15:00, ~15:10 MYT); mock v1 approved
("ok"). Tests: `sorento_crm_backend/tests/test_quote_cover_fields.py` (QCF), `tests/test_quote_cover_fields_fax.py`
(FAX), `QuotationCoverDesigner.test.tsx` (DES), `components/quotation/CoverPageCard.sections.test.tsx` (CARD).

## A. Source fields

- A1. Every designer row picks a source field from one server list (`GET .../quotation-templates/cover-sources`,
  same permission as the template list). QCF `test_sources_*`.
- A2. The list holds: document number, date, project title, total pages, To name / address / tel / fax / email,
  Attn, salesperson name / email / mobile, prepared by name / phone, terms text, payment terms, validity, company
  name / address / tel / fax. It holds no Quotation Purpose, no Sale admin, no project short name. QCF.
- A3. A source may be used in more than one row. QCF `test_validate_accepts_the_sheet_*`.
- A4. Adding a row = pick a field; it arrives ticked with that field's default label. Changing a row's field
  replaces a label still at the old default and keeps a typed one. DES.

## B. Sections and columns

- B1. A design is a list of sections (1 to 12); each has a style (label and value, centred title, numbered list,
  signature block, footer), a band label, 1 to 6 columns, and rows each placed in one column. QCF validate tests.
- B2. Unknown source, unknown style, a column outside the section, 0 or 7 columns, a label or title over 60
  characters, no sections or more than 12: refused with a 422, nothing saved. QCF, template route tests.
- B3. Fewer columns moves rows from a removed column into the last one. DES.
- B4. Sections can be added, moved up / down and removed (never the last one). DES.
- B5. Unticked and empty rows do not print; a section with nothing to print does not print; an empty column keeps
  its place. QCF `test_sections_*`.

## C. Printing

- C1. A revision sent from now on is layout 4 and carries the design active at send. QCF issue tests.
- C2. Reference No. (document number) prints the number only; the project title prints from its own source
  (the document's subject title). QCF values, PDF and sign page tests.
- C3. PDF page 1 prints each section as a dark band with its label over its columns: label and value rows, a
  centred title, numbered items with bold labels (numbering continues across columns), a signature line with its
  rows, a footer under a rule. Terms html prints on its own lines under its label, never after a bare colon.
  QCF PDF tests.
- C4. Every admin label and every value is HTML escaped; the terms go through the terms cleaning. QCF
  `test_pdf_layout_4_escapes_*`.
- C5. Total Pages prints "1+N" in the PDF only (N = pages after the cover), counted from the rendered PDF; it is
  blank, so not printed, on the sign page and previews. QCF total pages tests.
- C6. The customer sign link and the quotation's Cover letter tab draw the same sections (columns stack on a
  phone). QCF sign page + draft preview tests, CARD.
- C7. The footer is the issuing company's: name off the company, address / Tel / Fax off System Settings. QCF.

## D. What already exists

- D1. Revisions sent before this change (layouts 1, 2, 3) print exactly as they went out, including the old
  reference text with the project title. QCF `test_a_sent_legacy_layout_3_*`, the migrated layout 2 / 3 tests.
- D2. A design saved before this change opens in the designer as one single-column section (Quotation Purpose
  dropped, a blank label shown as its old default) followed by a Project Title band, and saves in the new shape.
  QCF legacy test, template route tests.
- D3. The default design (Add) is today's rows minus Quotation Purpose in one section, then a Project Title band.
  QCF default test, DES.

## E. Fax

- E1. A party has an optional Fax (form, detail page); a new quotation snapshots it as the recipient fax; the
  quotation header shows and edits it. FAX.
- E2. System Settings (General) has an optional Fax, printed as the company fax. FAX.
