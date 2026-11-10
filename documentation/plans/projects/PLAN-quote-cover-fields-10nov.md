# PLAN: Quotation cover page: source-field rows and the sales cover sheet layout (QUOTE-COVER-FIELDS)

**Status:** Build (mock v1 approved 10 Nov). Track: M (one additive migration for Fax).
Track: M (expected migration for the missing sources, see card Q2). Follow-up to QUOTE-COVER-DESIGN
(`documentation/plans/projects/PLAN-quote-cover-design-02nov.md`).

## Journey

Owner, 10 Nov ~14:55 MYT: the cover page designer (Project Sales > Configuration > Quotation Templates > Cover page)
needs more fields, laid out like the sales team's real cover sheet: a "Propose to:" band with two columns, a
"Project Title:" band, a "Term & Condition:" band, a "Prepared by," signature block and a company footer.

Owner ruling, 10 Nov ~15:00 MYT:
1. Reference No. = the document number ONLY. The project title gets its own Project Title band.
2. Every designer row has a SOURCE FIELD the admin picks from a list, plus the editable label and
   show/hide/drag as today. Adding a row = pick a source + label. Defaults reproduce today minus the
   project title in Reference No.

## Today (origin/main a4af6565)

- Rows are a fixed tuple of 12 keys: `sorento_crm_backend/app/services/quotation_cover_service.py:24-37`,
  refused when unknown `:99-100`, all 12 required `:109-110`.
- Reference No. appends the project title: `quotation_cover_service.py:133-138`.
- Values per key: `issue_values` `quotation_cover_service.py:242-270`.
- Designer: `sorento_crm_frontend/app/(protected)/project-sales/quotation-templates/components/QuotationCoverDesigner.tsx:216-342`.
- One active design per company: partial unique index `sorento_crm_backend/app/models/projects.py:1340-1346`.

## Source field registry (draft, see the behaviour card)

One dict in `quotation_cover_service.py`: source key -> caption, default label, resolver. Rows become
`{source, label, shown}` (plus a section once Q1 is answered). Validation accepts any known source.

Open questions and the full source list with file:line live in the lane PR's behaviour card.

## Owner answers (10 Nov ~15:10 MYT) and mock approval ("ok")

- Q1 (a) rows sit in sections, plus: a section can have ANY number of columns; the admin sets the column count
  per section and places each row in a column.
- Q2 (a) Fax added: `projects.parties.fax`, `system_settings.fax`, `quotation_documents.recipient_fax_snapshot`.
- Q3 (a) Total Pages = "1+N", counted when the PDF is drawn (blank on the sign page).
- Q4 (b) no Sale admin source until data exists.
- Q5 (a) footer = the issuing company only (`_sender()`).
- Quotation Purpose REMOVED from the source list and the default rows (PROPOSAL-FORM-COLLAPSE removes the field).

## Contract

Design (stored on `quotation_templates.design`, copied onto the issue at send, layout_version 4):

```
{show_letterhead, title, closing_html,
 sections: [ {style: fields|title|numbered|signature|footer, label (<=60), columns (1..6),
              rows: [{source, label (<=60), shown, column (0..columns-1)}]} ]   1..12 sections, <=80 rows}
```

- Sources: one dict `SOURCES` in `quotation_cover_service.py`, served at
  `GET /project-sales/config/quotation-templates/cover-sources` (same gate as the list). A source may repeat.
- A design saved before this lane (`rows: [{key,...}]`) is normalized on read and on issue: one `fields` section,
  1 column, `key` mapped to its source, `purpose` dropped, `prepared_by` -> `salesperson_name`.
- Revisions already sent (layout 1, 2, 3) print exactly as before, including the old reference text.
- Layout 4 Reference No. (`document_no`) = the document number only; the project title is the `project_title`
  source (`document.subject_title`).
- Payload: `cover_sections: [{style, label, columns, cells: [[{source, label, text|html}] per column]}]`;
  `cover_rows` stays as the flattened list. Empty / unticked rows drop; a section with no rows drops.
- PDF: rendered twice only when a shown `total_pages` row exists (first pass counts the pages).

Tests: `sorento_crm_backend/tests/test_quote_cover_fields.py` (red first), `tests/test_quote_cover_fields_fax.py`.
