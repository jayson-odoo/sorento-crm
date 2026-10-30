# Behaviour card: QUOTE-SIGN-PAGE (customer quotation sign page + issued PDF)

Source: owner team meeting 29 Oct 15:40. Plan: `PLAN-quote-sign-page-29oct.md` (same folder, facts with file:line).

Example quotation, real shape from the dev copy (API on crew copy :8105, 29 Oct), names masked:
PRJQ-2026-0003, one section "Townhouse", 2 lines (32MM TAIL PIECE COUPLING, 1 EA x RM 300.00; BRAC73080604-0001,
1 EA x RM 500.00), total RM 800.00, recipient CUSTOMER A, Attn CONTACT B, signatory SALES REP A +60100000001.
Dev has 3 quotation documents (PRJQ-2026-0002/3/4), none issued yet, so "R1" below is what the first issue prints.

## Before / after

| # | Item | Today | After |
|---|------|-------|-------|
| 1 | Logo | Name only, page and PDF (`QuotationSignClient.tsx:41-44`, `project_quotation_pdf_service.py:304-349`) | Company logo left of the name on the page and the PDF letterhead, from System > Companies "Logo URL" (`companies.logo_url`, `models/company.py:38`); no logo set = name only, as today. Dev: MCH and SRT both have none set. |
| 2 | Number | Page: "Our Ref PRJQ-2026-0003 (R1)" AND a second row "Revision R1" (`QuotationSignClient.tsx:69-76`); PDF "Our Ref PRJQ-2026-0003 (R1)" (`document_service.py:554`, pdf :316) | One row "Quotation No. PRJQ-2026-0003-R1" on page and PDF; Revision row gone; PDF file `quotation-PRJQ-2026-0003-R1.pdf` |
| 3 | Sections | One always-open card per section, each with its section total, then a separate "Total amount" card (`QuotationSignScopes.tsx:140-173`) | ONE card: each section is a row "Townhouse . 2 items . RM 800.00" that expands to its line table; last row of the same card "Total amount RM 800.00". PDF unchanged (paper prints every line) |
| 4 | Terms | Terms shown read-only; no checkbox; "Signing below accepts this quotation." (:227-229); pad unlocks once a name is typed (:252) | Checkbox "I have read and agree to the Terms and Conditions" above the pad; "Sign and accept" stays locked until name typed AND box ticked; the server refuses an accept without the tick (422), so the rule holds even if the page is bypassed |
| 5 | Signatures | PDF: Sorento sign-off, then "Accepted by" below it (pdf :505-542, CSS :587-596); page: Sorento card, then customer card below (:439-451); salesperson only at the bottom | PDF + page: "For Sorento" left, "Accepted by" right, same row (page stacks at phone width 375px). Salesperson name + phone also in the letterhead refs block at the top |

## Edge cases

- No terms on the issue (`terms_rendered` empty): page says "No terms were included" today; see Q4.
- Unsigned PDF (issued, not yet accepted): right box prints empty signature / name / date lines.
- One section only: see Q3. Many sections (5+): rows stay one line each until opened.
- Already-signed and changes-requested states keep today's behaviour; only their position moves (right column).
- Old issues already sent with "(R1)" text: see Q1.

## Questions (each with a recommendation)

Q1. Number format. (a) "Quotation No. PRJQ-2026-0003-R1", Revision row dropped (crew rec); (b) keep "Our Ref" label,
change text only; (c) keep today. Rec (a). Already-issued revisions store their text (`our_ref_text`, set once at
issue, `document_service.py:554`): rec build the label from document_no + issue_no when shown, so old and new
issues read the same. Count of already-issued prod revisions: UNVERIFIED (no prod access).

Q2. Logo source. (a) reuse Companies "Logo URL" (already editable, already used by emails `email_layout.py:275`;
no migration); the PDF server downloads it once per render (https only, 3 s timeout, 1 MB cap, image types only,
since the PDF engine can only embed inline images, pdf :655); (b) new logo upload on the Company form (file stored
like attachments; needs a migration, makes the lane size L). Rec (a): no migration, one place to set it; owner or
admin then pastes the logo URL for SRT and MCH. Security review runs either way (server fetch of a URL).

Q3. Sections open or closed when the page loads? (a) closed, except a quotation with one section opens it;
(b) all closed; (c) all open. Rec (a): a one-section quote has nothing to summarise, many sections read as a list.

Q4. Terms checkbox. Text source: (a) today's Terms template (System > Project Sales templates, rendered into the
quotation at create, `document_service.py:199-220`, frozen per issue at :558); (b) a new fixed text. Rec (a): it
already exists and prints on the PDF. When an issue has NO terms: (i) no checkbox (nothing to agree to);
(ii) block issuing without terms. Rec (i): no change to the issue flow. Consent record: rec no new column;
`accepted_at` plus the frozen `terms_rendered` already prove what was agreed.

Q5. Salesperson near the top: (a) the quotation's signatory name + phone (on the document today,
`document_service.py:187-188`, the person who signs for Sorento); (b) the project owner user (template token
`salesperson_name`, `project_quotation_template_service.py:233-237`). Rec (a): same person who signs, already on
the quotation, no new lookup.
