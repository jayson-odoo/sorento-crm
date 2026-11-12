# PLAN: quotation line note shows in the customer REMARK column

Status: Build (card approved 12 Nov: Q1 a stacked on #2339, Q2 a all notes, Q3 a Excel too). Track: M, cloud lane QUOTE-LINE-NOTE-REMARK.

## Journey

Owner, 12 Nov 2026: a salesperson writes a note on a quotation line (Lines editor, note icon). The
customer never sees it. It should show in the REMARK column of what the customer reads, after any
flag text such as "Non-cancellable".

## Facts (main + #2339 branch)

- Note storage: `projects.quotation_lines.notes` (Text, nullable),
  `sorento_crm_backend/app/models/projects.py:2124`; written in
  `app/services/project_quotation_service.py:464, 1160, 1762`.
- Editor: `NotesButton`,
  `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/QuotationLinesGrid.tsx:1006-1045`.
- Customer render paths, none reads `notes` today:
  - PDF (also the email attachment): `app/services/project_quotation_pdf_service.py` (matrix rows
    ~:632, plain rows ~:769).
  - Sign link page: `serialize_sign_page` in `app/services/project_quotation_document_service.py`
    (~:2508) -> `QuotationSignScopeLine` (`app/schemas/projects.py:2607`) ->
    `app/(auth)/quotation-sign/[token]/components/QuotationSignScopes.tsx`.
  - Excel: `app/services/project_quotation_excel_service.py`.
  - Email body: no line table (link + PDF only). No portal view of the quotation.
- #2339 (NON-CANCELLABLE-ITEMS, not merged) adds the REMARK column and ONE formatter,
  `quotation_columns.remark(line)` + `for_lines()` (`app/services/quotation_columns.py:43-68` on
  that branch), already called by PDF, Excel and sign page.

## Approach (reuse)

Extend `quotation_columns.remark(line)` to return flag text, then the trimmed note on its own line;
extend `for_lines()` so REMARK shows when any non-section line has a flag OR a note. Every render
path already calls these two functions after #2339, so no path gets its own copy. Renderers keep
line breaks (PDF `white-space: pre-line`, sign page same, Excel wrap). Editor: a one-line hint in
the note popup that the note is shown to the customer.

Depends on #2339's code: stack on it (crew-ask).
