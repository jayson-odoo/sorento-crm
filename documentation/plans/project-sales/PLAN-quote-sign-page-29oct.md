# PLAN: quotation sign page + PDF: logo, quotation number, one card of sections, terms checkbox, side-by-side signatures (QUOTE-SIGN-PAGE)

Status: Plan. Owner answered card a73603971 (29 Oct ~22:45: Q1 a + keep Revision row, Q2 a, Q3 a, Q4 yes + visible
reason when not ready, Q5 a); mock v2 filed, waiting on its approval; UAC updated; no code until the mock is approved.
Track: M (feature track: changed wording and layout on an existing screen + PDF, a new required consent on the
public accept endpoint; no migration planned, no auth/RBAC change). UAC: `quote-sign-page-29oct-acceptance-criteria.md`.
security-reviewer joins (server fetch of the admin-entered logo URL; public accept endpoint gains a required field).

Owner team meeting 29 Oct 15:40 (Project Sales module) decided the five items below for the customer quotation sign
page (`/quotation-sign/{token}`) and the issued quotation PDF.

## Facts (read 29 Oct, head 3b3d3e1b91)

- Sign page: `sorento_crm_frontend/app/(auth)/quotation-sign/[token]/components/QuotationSignClient.tsx` (letterhead
  :33-92, cover :425-429, scopes :431, terms :433-437, Sorento signature card :439-451, customer form :133-339) and
  `QuotationSignScopes.tsx` (one fixed Card per scope :140-163, separate Total Card :166-173). Data:
  `GET /api/v1/public/quotation-sign/{token}` (`app/api/v1/public/quotation_sign.py:33`), built by
  `serialize_sign_page` (`app/services/project_quotation_document_service.py:1282-1398`), schema
  `QuotationSignPageResponse` (`app/schemas/projects.py:2245-2274`).
- PDF: WeasyPrint HTML (`app/services/project_quotation_pdf_service.py:24, 644-656`), only `data:` URLs are fetched
  (:655). Letterhead `_sender` :258-277 + `_header_html` :304-349 (name, address, Tel; no logo). Sign-off :505-542,
  stacked `.signoff` / `.accepted` (CSS :587-596). Page A4 landscape (:546).
- Number: `our_ref_text = f"{document_no} (R{issue_no})"` at issue (`document_service.py:554`) and for the draft view
  (:700-703). PDF prints it as "Our Ref" (pdf :316); sign page prints "Our Ref" plus a separate "Revision R{n}" row
  (Client :69-76).
- Logo: `companies.logo_url` free-text String(500) (`app/models/company.py:38`), set by a system admin
  (`app/api/v1/system/companies.py:122/194/341`); read today only by email (`email_layout.py:214-227, 275`). Dev copy
  (29 Oct, API on crew copy :8105): both companies (MCH, SRT) have NO logo_url set.
- Terms: `quotation_templates` kind=terms (`app/models/projects.py:1164`), rendered once into `document.terms_html`
  at create (`document_service.py:199-220`), copied to `issue.terms_rendered` at issue (:558); shown on the PDF
  (pdf :450-458) and on the sign page (`terms`, `document_service.py:1384`). No checkbox, no consent field anywhere;
  accept body = `QuotationSignatureRequest` (`schemas/projects.py:2162-2173`).
- Salesperson: only `document.signatory_name` / `signatory_phone` (free text, `document_service.py:187-188`), printed
  under the Sorento signature at the bottom of the PDF; on the sign page only as the Sorento signature label (:448).

## Items (shape pending the owner's answers on the card)

1. Logo on the sign page letterhead and the PDF letterhead, from the document company's `logo_url`; none set = name
   only, as today.
2. One quotation number label "Quotation No. <document_no>-R<issue_no>", separate Revision row dropped.
3. One card: sections as expandable rows, each with its section total; the grand total as the last row of that card.
4. Terms checkbox before signing; the accept endpoint refuses an accept without `terms_accepted: true`.
5. Signatures side by side (PDF + sign page); salesperson name + phone in the letterhead refs block.

## Tests (red first; filled in with the UAC)

- pytest: `tests/test_project_quotation_pdf.py`, `tests/test_project_quotation_signing.py`,
  `tests/test_project_quotation_document.py`.
- vitest: `app/(auth)/quotation-sign/[token]/components/QuotationSignClient.test.tsx`.
