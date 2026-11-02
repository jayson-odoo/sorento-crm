# UAC: Quotation cover page + terms print (QUOTE-COVER-PAGE)

**Status:** Final. Owner approved sample v2 (`documentation/mockups/QUOTE-COVER-PAGE/index.html`)
on 2 Nov with every point settled: 1a Prepared By = project salesperson, 2a Payment Terms and
Validity defaults beside the company T&C template, 3a letterhead on page 1, terms on page 1 only
(countersign bottom panel goes, tick box stays), Your Ref stays. Plan:
`PLAN-quote-cover-page-02nov.md`.

"New issue" = an issue created after release. "Old issue" = any issue that exists at release.

## A. Cover page (PDF page 1, new issues)

- **A1** A new issue downloads as ONE PDF: page 1 A4 portrait (the cover page), price pages A4
  landscape as today.
- **A2** Page 1 carries the company letterhead (logo, name, address, phone, as on the price
  pages), the title QUOTATION, then label/value rows in exactly this order: Reference No., Date,
  Attn, Company, Contact, Add, Email, Quotation Purpose, Terms & Conditions, Payment Terms,
  Validity, Prepared By. There is no Fax row.
- **A3** Reference No. = `<document_no>-R<issue_no> <project title>` (example
  `PRJQ-2026-0042-R2 SERI MUTIARA RESIDENCES`). The price-page "Quotation No." shows the same
  string.
- **A4** Date = the quotation date; Attn = Attn; Company = recipient name; Contact = recipient
  phone; Add = recipient address (line breaks kept); Email = the quotation's Email; Purpose,
  Payment Terms, Validity = the quotation's fields; Prepared By = the project salesperson's name.
- **A5** A row with no value is left out entirely.
- **A6** Every printed value is escaped (`<script>` typed in Purpose prints as text).
- **A7** Terms & Conditions print on page 1 only; the price pages have no terms block.
- **A8** Your Ref stays on the Header tab and in the price-page refs, as today; it is not a cover
  row.

## B. Quotation fields

- **B1** The quotation has four new optional free-text fields: Email, Quotation Purpose, Payment
  Terms, Validity. Saved per quotation; shown on the view page in the same place as on the edit
  form (Email under Phone and Purpose under Subject on the Header tab; Payment Terms and Validity
  above the terms editor on the Terms tab). Prepared By shows read-only on the Header tab.
- **B2** On a NEW quotation, Email prefills from the customer's main contact email (the contact
  whose name prefills Attn), Payment Terms and Validity prefill from the active company terms
  template. Every value stays editable for this quotation only.
- **B3** Cover values other than the terms are read from the quotation as it is now, exactly like
  today's header (Attn, address, date): page 1 and the price pages can never disagree. The terms
  come from the issue snapshot, as today.
- **B4** Validity is printed and shown, never enforced: the sign link keeps working after it.
- **B5** Usable and not clipped at 375px and 1280px.

## C. Terms print (new issues)

- **C1** Terms print as written: a heading line stays a plain (bold) line, not a numbered
  clause; a blank line keeps its gap; a typed "- " line prints as typed with no number before
  it; a bulleted list prints as bullets; a nested list prints nested.
- **C2** The countersign page shows the same structure as the PDF for the same issue.
- **C3** Bold, italic and underline survive; every other tag is dropped (scripts and styles with
  their content; links, images, spans and the like keep only their text); no attribute survives.

## D. Company T&C template

- **D1** One active company terms template, copied into each new quotation and editable per
  quotation (unchanged rule, `QuotationTemplatesClient.tsx:31-45`).
- **D2** The template add/edit dialog has Payment Terms and Validity fields between Name and the
  terms text; saving keeps them.
- **D3** No active template: a new quotation starts with empty terms, Payment Terms and
  Validity; nothing errors and the PDF prints no empty rows.

## E. Countersign link (owner, 2 Nov: "it should reflect in the customer countersign link also")

- **E1** For a new issue, `/quotation-sign/[token]` opens with a cover card: the letterhead
  ("Quotation from" and the company), then the same rows, in the same order, with the same values
  and the same terms structure as PDF page 1.
- **E2** The reference on the countersign link (cover card and the "Quotation No." row) equals
  the PDF's.
- **E3** The bottom "Terms and conditions" panel is gone; the terms tick box, signature and
  Accept work as today.
- **E4** At 375px each label sits above its value; nothing clipped.

## F. Old issues keep their old layout

- **F1** An old issue's PDF re-downloads in today's layout: landscape only, no cover page,
  "Quotation No." without the project title, numbered terms after the total.
- **F2** An old issue's countersign page looks as today: no cover card, bottom terms panel
  present.
