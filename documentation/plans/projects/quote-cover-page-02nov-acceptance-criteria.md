# UAC: Quotation cover page + terms print (QUOTE-COVER-PAGE)

**Status:** Draft. Waits on the owner's approval of sample v2
(`documentation/mockups/QUOTE-COVER-PAGE/index.html`) and the two points marked OPEN below.
Decisions 1a, 2a, 3a answered by the owner 2 Nov. Plan: `PLAN-quote-cover-page-02nov.md`.

## A. Cover page (PDF page 1)

- **A1** A quotation issued after release downloads as ONE PDF whose page 1 is A4 portrait and
  whose price pages are A4 landscape, as today.
- **A2** Page 1 prints label/value rows in this order: Reference No., Date, Attn, Company,
  Contact, Add, Email, Quotation Purpose, Terms & Conditions, Payment Terms, Validity,
  Prepared By. There is no Fax row.
- **A3** Reference No. = quotation number (`<document_no>-R<issue_no>`) followed by the project
  name. The same string prints in the price-page header and shows on the customer sign page.
- **A4** Date = the quotation date; Attn, Company, Add, Contact = the quotation's recipient
  snapshot; Email = the quotation's email snapshot.
- **A5** A row whose value is empty is left out (no blank label, no dash).
- **A6** Every printed value is escaped: a `<` typed in Purpose prints as text.
- **A7** Terms & Conditions print on page 1. OPEN A: whether they also repeat after the price
  table (sample shows page 1 only).
- **A8** Prepared By = the project's salesperson (owner, 2 Nov, 1a), frozen on the issue.
- **A9** Company letterhead prints on page 1 (owner, 2 Nov, 3a).
- **A10** Your Ref: OPEN B, stays on the Header tab and price-page refs (sample) or goes.

## B. Quotation fields

- **B1** The quotation has four new fields: Email, Quotation Purpose, Payment Terms, Validity.
  All optional free text; all saved per quotation and shown on the view page in the same place
  as on the edit form.
- **B2** On a NEW quotation, Email prefills from the customer's main contact (the same contact
  that fills Attn), and Payment Terms and Validity prefill from the active company terms
  template, which carries them as two fields beside its terms text (owner, 2 Nov, 2a). Editing
  them changes only this quotation.
- **B3** Issuing copies all four values onto the issue. Editing the quotation afterwards does not
  change what a re-download of the earlier issue prints.
- **B4** Validity is printed and shown, never enforced: the sign link keeps working after it.
- **B5** Usable and not clipped at 375px and 1280px.

## E. Countersign link (owner, 2 Nov: "it should reflect in the customer countersign link also")

- **E1** `/quotation-sign/[token]` opens with a cover card showing the same rows, in the same
  order, with the same values as PDF page 1 of that issue, including the reference and the terms.
- **E2** The reference string on the countersign link equals the one on the PDF.
- **E3** At 375px each label sits above its value; nothing clipped.
- **E4** The bottom terms panel follows OPEN A; the terms tick box and signing work as today.
- **E5** An issue created before release shows its countersign page as before release.

## C. Terms print

- **C1** For a new issue, terms print the way they were written: a heading line stays a
  heading (not a numbered clause), blank lines keep their gap, a bulleted list prints as bullets
  with no number in front, a nested list prints nested.
- **C2** The sign page shows the same structure as the PDF for the same issue.
- **C3** Bold survives; any other markup (scripts, links, images, styles) is dropped on both
  surfaces.
- **C4** An issue created BEFORE release re-downloads exactly as it did before release: same
  landscape-only layout, same numbered terms.

## D. Company T&C template

- **D1** One active company terms template, copied into each new quotation and then editable per
  quotation (unchanged rule, `QuotationTemplatesClient.tsx:31-45`).
- **D3** The template add/edit dialog has Payment Terms and Validity fields; the active
  template's values prefill a new quotation.
- **D2** No template active: a new quotation starts with empty terms and the PDF prints no terms
  row; nothing errors.
