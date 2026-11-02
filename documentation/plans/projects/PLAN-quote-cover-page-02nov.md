# PLAN: Quotation cover page + terms print (QUOTE-COVER-PAGE)

**Status:** Plan. Sample v2 filed for owner approval (decisions 1a, 2a, 3a answered 2 Nov; OPEN A terms page 1 only, OPEN B Your Ref); no product code until approved. Track: L
(new columns via migration, new printed page, cross-cutting PDF change).

## Journey

Project sales keeps a one-sheet Excel cover page per quotation (reference, date, attn, company,
contact, address, email, purpose, terms, payment terms, validity, prepared by). They retype it by
hand for every quotation. The owner wants it inside the quotation: filled from the record, printed
as the first page of the quotation PDF, and the terms block printed the way it was written.

## Owner decisions (final, 2 Nov 08:45)

1. **1a** Separate portrait first page, label/value rows, in the Excel's field order:
   Reference No., Date, Attn, Company, Contact, Add, Email, Quotation Purpose,
   Terms & Conditions, Payment Terms, Validity, Prepared By.
2. **2a** Reference = system quotation number + project name. One reference on the PDF and the
   sign page. The team's own code goes away.
3. **3a** Fax dropped. Email and Contact (phone) come from the customer contact. Quotation Purpose
   is optional free text.
4. **4a** One company T&C template, editable per quotation. Payment Terms and Validity are two
   pre-filled free-text fields on the quotation. Validity is NOT enforced on the sign link.

## Must fix: terms print

`_terms_html` (`sorento_crm_backend/app/services/project_quotation_pdf_service.py:585-593`) runs
`_text_blocks(strip_numbering=True)` and wraps every non-empty line in its own `<li>`: headings
become numbered clauses, blank-line gaps vanish (`_text_blocks` skips empty lines), a typed
"- " prints after the number, nested bullets flatten. The sign page shows the editor HTML
unnumbered, so the two disagree. Target: headings, blank lines and bullets print as written, the
same on PDF and sign page.

Downloads re-render from the issue snapshot every time (module rule,
`project_quotation_pdf_service.py:13-14`), so an already issued quotation must keep its layout:
the new cover page and new terms layout apply to issues created after release only.

## Architecture (to confirm after the sample is approved)

- Layer: backend PDF render (`project_quotation_pdf_service.py`) + quotation document model and
  schema + form (`QuotationFormClient.tsx`) + sign page terms block.
- Old vs new layout: one integer on the issue row (`layout_version`, existing rows 1, new issues
  2) read by `build_issue_html`; no inference from dates or null columns.
- New quotation document columns (Email snapshot, Purpose, Payment Terms, Validity) copied onto
  the issue at issue time under the existing snapshot rule.
- Payment Terms / Validity defaults: from the company T&C template or system setting (decided in
  the plan after approval; simplest that works).
- Terms: one HTML sanitiser that keeps `p`, `br`, `strong`, `ul/ol/li` and blank paragraphs,
  shared by PDF and sign page, so both print the same structure.

## Open (after owner approves the sample)

- UAC file `quote-cover-page-02nov-acceptance-criteria.md`.
- Migration, red-first tests, kill tests, reviewer, security review, browser pass with a real
  rendered PDF (portrait first page + landscape price pages in one file), guide update, hand test.
