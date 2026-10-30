# UAC: QUOTE-SIGN-PAGE (quotation sign page + issued PDF)

Status: binding. Owner answered the card 29 Oct ~22:45 (ask a73603971): Q1 a but KEEP the Revision row, Q2 a, Q3 a,
Q4 yes plus a visible reason when Sign and accept is not ready, Q5 a. Mock v2 approved 29 Oct 23:16. AC1.4 and AC2.6
tightened in review round 1 (security + reviewer findings).

Terms: "sign page" = `/quotation-sign/{token}`; "PDF" = the issued quotation PDF
(`project_quotation_pdf_service.build_issue_html`); "issue" = one `quotation_issues` row (one revision).

## AC1 Logo

1. The sign page payload carries `sender_logo_url` = the document company's `companies.logo_url`, null when unset.
2. Sign page: with a logo, the letterhead shows an image (alt "<company name> logo") left of the company name; without
   one, no image and no empty box.
3. PDF: with a logo that downloads, the letterhead holds an inline `data:image/...` image left of the company name.
4. PDF download rules: the URL must pass `assert_safe_outbound_url` (`app/services/outbound_url_guard.py:207`: https
   only, no loopback / private / link-local / own host), 3 s timeout, at most 1 MB, response content type `image/*`.
   Any refusal or failure: the PDF still renders, name only, a warning is logged, no error reaches the user.
   Round 1 (security review): a malformed URL never raises; the request asks for `Accept-Encoding: identity` and any
   other `content-encoding` is refused; the 3 s is a total deadline, not per read; the bytes are re-encoded through
   `product_image_service._downscale` (PNG / JPEG / WebP only, never SVG, content-type not trusted). The sign page logo
   `<img>` sends no referrer.

## AC2 Quotation number

1. Sign page and PDF show ONE row "Quotation No." with value `<document_no>-R<issue_no>`, e.g. `PRJQ-2026-0003-R1`.
2. The sign page KEEPS its "Revision R<n>" row, under Quotation No. (owner 29 Oct ~22:45). The PDF has no "Our Ref"
   row and, as today, no Revision row.
3. The value is built from `document_no` + `issue_no` when shown, so an issue stored with the old text
   (`PRJQ-2026-0003 (R1)`) also shows `PRJQ-2026-0003-R1`.
4. A new issue stores `our_ref_text = "<document_no>-R<issue_no>"`; the draft view (`document_service.py:700-703`) uses
   the same format.
5. PDF file name: `quotation-PRJQ-2026-0003-R1.pdf`.
6. The Excel export labels the same value "Quotation No." and the pending download file name uses it (review round 1).

## AC3 One card of sections

1. The sign page renders all sections and the total inside ONE card titled "Quotation"; there is no separate
   Total card.
2. Each section is a row showing its label, its item count ("2 items", "1 item") and its section total (RM).
3. Clicking (or tapping) a section row opens / closes that section's line table (today's 9 columns, unchanged).
4. On load: a quotation with exactly one section shows it open; two or more sections all start closed.
5. The last row of the card is "Total amount" with the grand total.
6. PDF sections are unchanged (every line printed).

## AC4 Terms checkbox

1. When the issue has terms (`terms_rendered` not empty), the accept form shows an unticked checkbox "I have read and
   agree to the Terms and conditions." above the signature pad.
2. The signature pad and "Sign and accept" stay disabled until a name is typed AND the box is ticked; unticking
   disables them again.
2a. While "Sign and accept" is not ready, a hint line beside it names the next missing step (owner: "the user know why
   they cannot accept"): no name and no tick = "Type your name and tick the terms box to accept."; name, no tick =
   "Tick to agree to the terms before you accept."; name + tick, nothing drawn = "Draw your signature to accept.";
   ready = no hint. With no terms on the issue the tick step is skipped in every message.
2b. Tapping the not-ready "Sign and accept", or the locked signature pad, highlights the first missing step (name
   field or tick row), scrolls it into view and focuses it; the hint turns to the warning colour. Nothing is sent.
3. `POST /api/v1/public/quotation-sign/{token}/accept` with `terms_accepted` missing or false, on an issue with terms,
   returns 422 and records no signature; with `terms_accepted: true` it accepts as today.
4. When the issue has no terms: no checkbox, and accept does not require `terms_accepted`.
5. Already-accepted and changes-requested states show no checkbox (unchanged otherwise).

## AC5 Signatures side by side, salesperson at the top

1. Sign page, width 768px and up: "Signed for Sorento" (left) and the customer card (right) share one row; under
   768px they stack, Sorento first.
2. The letterhead refs show "Sales contact" = `signatory_name`, `signatory_phone` (name only when no phone; row hidden
   when both are empty), on the sign page and the PDF. The sign page payload carries `signatory_phone`.
3. PDF sign-off is two columns: left "For Sorento" (signature image, signatory name, phone); right "Accepted by"
   (customer signature image, signer name, "Date:" accepted date) or, before acceptance, blank signature / name /
   date lines.
4. PDF stays A4 landscape.

## AC6 Layout

1. Sign page usable and not clipped at 375px and 1280px (no horizontal page scroll; the line table scrolls inside
   its section).

## AC7 Owner hand test round 1 (30 Oct ~10:10)

1. The Sorento card is titled "Prepared by <name>": the Sorento signature's signer name, else the quotation signatory,
   else the company name. Blank or whitespace names fall through; the title never shows "-". A new Sorento signature
   with no typed name and no signatory stores the signing user's name.
2. The customer card is titled "Accepted by" while unsigned and "Accepted by <signer name>" once accepted.
3. The sign page shows no "GPS location" row on either card and never asks the browser for location; the accept
   request sends `gps_lat` / `gps_lng` as null. The columns stay (no migration): new customer signatures simply carry
   no location, so the PDF prints none for the customer. Staff-side signing keeps its location capture.
4. Other SignaturePad callers (staff sign dialog, signature block) keep the location prompt and rows: the hide is opt-in.
