# CARD: Quotation Certification tab (QUOTE-CERT-TAB, 8 Nov)

Behaviour card. Read of `origin/main` 53603f2b. Map and feasibility: `PLAN-quote-cert-tab-08nov.md`.
Mock: `mockups/quote-cert-tab-08nov.html`. Examples below are masked (public repo); the real dev
rows were asked for with `crew-data-request:` on #2245 and only change the examples, not the rules.

## Rules (proposed)

R1. **Which certificates.** The tab lists one row per DISTINCT certificate that covers at least one
    product on the quote's current version, through the existing explicit link `certificate_products`
    (`app/models/certificate.py:287`), plus certificates added by hand, minus those removed on this quote.
    Archived certificates never appear by themselves. Standard list view (`PanelDataGrid`).
R2. **One row for a shared certificate.** A certificate covering several quoted products is one row;
    "Quoted products" lists them all, and every matching row inside the PDF is boxed.
R3. **How a product is found in the PDF (no fuzzy matching).** Each product-certificate link gets an
    explicit "Code on certificate" (new `certificate_products.model_code`, e.g. `14A` for product
    `SV-14A-CP`). Empty = the product's own `product_code` is searched. The search is an exact,
    whole-word text hit: `14A` hits a cell reading `14A` but never `114A` or `14AB`. No name matching,
    no partial-code guessing. Nothing found = no box, and the panel says the code is not on the
    certificate.
R4. **What gets boxed.** The table row that holds the hit: from the ruled line above to the ruled line
    below, across the table's width, so a wrapped description stays inside the box. A table without rules
    gets the hit's text line, padded.
R5. **Fixing boxes.** On the certificate page a user can remove a box, move or resize it, or draw a new
    one. Changes save to "this quote only" by default, or to "every quote" for that product (the
    product-certificate default). A quote's own boxes win over the default; the default wins over
    auto-found.
R6. **Scanned certificates** (no text layer) get no automatic box; the row says "No text, draw a box".
    No OCR in v1.
R7. **Remove / Add.** Remove from this quote is the 5 s reversible countdown with Cancel (detach, no
    confirm dialog); it only hides the certificate on this quote. Add certificate = one searchable
    select over the company's active certificates; a hand-added certificate that covers none of the
    quoted products is sent whole, unboxed.
R8. **Customer copy.** See Q3. Whatever is chosen, boxes are burned into a COPY at export; the stored
    certificate file is never changed. Issuing a revision freezes its certificate list, revisions and
    boxes (like line images, `project_quotation_image_service.py:270`); later edits affect the next revision.
R9. **Renewal.** A certificate renewal (new revision) drops saved boxes for the old file (they were
    drawn on another PDF) and boxes are found again from the code. Issued revisions keep their frozen copy.

## Examples (masked)

| # | Quote line | Certificate | Code on cert | Result |
|---|---|---|---|---|
| E1 | `SV-14A-CP` stop valve DN20 | SPAN WCM PC 00xxxx, p.2 row 17 reads `14A` | `14A` | Row 17 boxed. Rows `114A`, `14AB` not boxed. |
| E2 | `SV-14A-CP` + `SV-15A-CP` | same SPAN certificate | `14A`, `15A` | ONE list row, quoted products "SV-14A-CP, SV-15A-CP", rows 17 and 18 boxed. |
| E3 | `BM-2201` basin mixer | PPS 04xxxFC prints `2201-B` | empty | `BM-2201` not on the certificate: no box, amber note. User types `2201-B` (fixed for every quote) or draws a box. |
| E4 | `WC-8038` | SIRIM scan, no text layer | `WC-8038` | "No text, draw a box"; user drags a box over row 2. |
| E5 | none | IKRAM 04xxxFC added by hand | n/a | Listed "Added by hand", no rows marked, sent whole. |

## Edge cases

- Code appears on several pages / several rows: every hit is boxed (a certificate may list the model per size).
- Same product on two certificates: both rows listed; each boxed independently.
- Line with no `product_id` (free text line): contributes no certificate.
- Product removed from the quote: its certificate leaves the list unless added by hand; a hand-added or
  removed marker for a certificate stays on the quote.
- A product whose own `product_code` is edited keeps a negative "no code found" cache until the next
  certificate revision or a typed code; the cache is keyed by revision, not by the product code.
- Certificate's current revision has no file (`attachment_id` NULL): listed with "No file", cannot be
  opened, left out of the customer PDF.
- Encrypted or broken PDF: treated like scanned (no auto box); export copies it without boxes and the
  export names it in the job result.
- Rotated pages: boxes stored in unrotated PDF points, so they stay on the row at any viewer rotation.
- Large certificates (50+ pages): text search runs server side once per revision + code and is cached
  on the box record, not per page view.

## Questions (max 5, each with a recommendation)

Q1. **Matching.** (a) explicit "Code on certificate" per product-certificate link, auto box = exact
    whole-word hits of that code (or the product code when empty), user fixes the rest; (b) also try
    pieces of the product code automatically (e.g. find `14A` inside `SV-14A-CP` by itself).
    **Recommend (a)**: standing rule is explicit links only; (b) is name-guessing and boxes `114A`-style
    neighbours on dense tables.
Q2. **Where highlights live.** (a) default per product-certificate (set once, every quote starts from
    it) with a per-quote override; (b) per quote only. **Recommend (a)**: the same SPAN certificate is
    quoted every week; fixing a box once should stick, while a one-off quote can still differ.
Q3. **What the customer receives.** (a) a separate "QT-xxxx Rn Certificates.pdf" (all included
    certificates, boxed), downloaded next to the quote PDF and listed in the WhatsApp dialog; (b) the
    certificates appended as extra pages at the end of the quote PDF; (c) both. **Recommend (a)**:
    the quote PDF stays small and readable, certificates can be resent alone, and today's "Send"
    is a hand-sent wa.me link with files the salesperson attaches (no server send exists).
Q4. **Permissions.** (a) see the tab = can see the quote; add / remove / box on a quote = can edit the
    quote (`projects.projects.edit`); "every quote" defaults and "Code on certificate" = Certificates
    edit (`master_data.certificates.edit`); (b) anyone who can edit the quote can also change the
    defaults. **Recommend (a)**: a salesperson's one-off fix should not silently change every other
    quote.
Q5. **Expired certificates on a quote.** (a) listed with a red Expired pill and left OUT of the
    customer PDF unless the user ticks "Include"; (b) hidden from the tab; (c) treated like valid ones.
    **Recommend (a)**: sending an expired certificate to a customer is the costly mistake, while
    hiding it hides that the product's certificate lapsed.

## Not in v1 (named triggers)

- OCR for scanned certificates: add when the count of scanned certificates on live quotes is material
  (count requested from crew on #2245). Cost: tesseract on every backend image, or ~1 Gemini call per page per revision.
- Auto-filling "Code on certificate" from the n8n extraction: add when the Gemini output carries the
  printed model code per product (it does not today; `certificate_revisions.extracted_json`).
