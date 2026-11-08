# CARD: Certificate links to check (CERT-LINK-CLEANUP, 8 Nov)

Behaviour card, Step 1, no code. Read of `origin/main` d7f43233 (#2245 merged). Real dev counts were
asked for with `crew-data-request:` on #2249; they change the numbers below, not the rules.

## Why links are wrong today (read of the code)

- The ingest (`app/api/v1/external/product_attachments.py:203`) resolves every product string the
  reader returns through `resolve_codes_to_products(..., allow_prefix=True)`
  (`app/services/product_code_resolution.py:126`). Tier 4 is a plain SUBSTRING (`:219`,
  `LIKE %code%`) and tier 5 a family PREFIX (`:258`). So a short string such as `14A` links every
  product whose code merely contains `14a` (`CSK14A-BL`, `114A...`), and a 4+ character family head
  links up to 200 families.
- Nothing checks that the string is printed on the PDF at all. The string that matched is kept as the
  link's Suggested "Code on certificate" (`_store_printed_codes`, `:206`), so each bad link still
  says which string pulled it in.
- #2245 greys these out on quotes only (`quotation_certificate_service.py:391`, state
  `not_on_certificate`). The register itself still lists all 158.

## Rules (proposed)

R1. **The report.** Master Data > Certificates > "Links to check": one row per certificate-product
    link: certificate (scheme + number), certificate type, product code + name, Code on certificate,
    source (AI / Manual / Confirmed), Verdict. Standard DataGrid, sortable on every column, filters:
    certificate (searchable select), verdict, certificate type. Default filter: verdict = Not found.
R2. **Verdict** of one link, read from the certificate's CURRENT revision PDF, text decoded first
    (symbol font U+F020-F0FF, as #2245):
    - **Found**: the Code on certificate is printed as a whole token (the #2245 matcher: spaces,
      hyphens and case ignored, a run of 1-4 words may cross a line break; `14A` never hits `114A`,
      `14AB`, `CSK14A-BL`). With no Code on certificate: one dash/space-delimited part of the product
      code (3+ characters with a digit, `SV-14A-CP` -> `SV`, `14A`, `CP` -> only `14A` qualifies) or the
      whole product code is printed as a whole token.
    - **Not found**: the PDF has text and neither is printed.
    - **Cannot check (scanned)**: the PDF has no text layer. **No file**: the revision has no PDF.
    The product's own NAME is never searched.
R3. **Checking is done once per revision, on the worker.** A verdict is stored on the link next to
    #2245's box cache (`certificate_products.boxes`, keyed by revision + code), so the report is a
    plain query. A link with no current verdict shows "Checking" and its certificate is queued; a new
    revision or a changed Code on certificate re-checks it. Backfill: one worker job over every
    certificate after deploy.
R4. **Confirm** (bulk or per row): a person says the link is right. See Q3. Confirmed links leave the
    default view, count as verified on quotes, and are never touched by a later ingest.
R5. **Remove** (bulk or per row): hard-deletes the selected links and their `product_attachments`
    projection rows (`CertificateService.remove_coverage`, `certificate_service.py:847`). It is the
    standard 10 s server-deferred countdown with Cancel (no confirm dialog); the server commits even if
    the tab closes. Never automatic: no verdict ever deletes a link by itself.
R6. **Audit.** `certificate_products` is audit-skipped (high churn, `models/certificate.py:290`), so
    each bulk action writes ONE audit row on the certificate per certificate touched:
    `coverage_removed` / `coverage_confirmed`, with the product codes, the verdicts at the time and
    the actor. Ingest churn stays out of the log.
R7. **Permission.** View the report = `master_data.certificates.view`; Confirm / Remove =
    `master_data.certificates.edit` (the existing coverage-edit permission).
R8. **Ingest from now on** (see Q2): a printed string links a product only when it is (1) printed as a
    whole token on the PDF (when the PDF has text) AND (2) resolves through exact code, product set,
    `+` split, or equals one whole dash-delimited part run of the product code. The substring and
    family-prefix tiers are OFF for certificates (they stay as they are for flyers, packing lists and
    promotions). A string that fails goes to the revision's "Unmatched products" list and the
    revision is flagged for review, exactly as an unknown code is today, so nothing is silently dropped.

## Examples (masked shapes; real rows replace them after the data request)

| # | Certificate | Link | Code on cert | PDF text | Verdict |
|---|---|---|---|---|---|
| E1 | SPAN BPAI/1327-2024 (stop valve) | `SV-14A-CP` | `14A` | row reads `14A` | Found |
| E2 | same | `BRD7711CP` towel rail | `14A` | no `14A` token near it, `BRD7711CP` not printed | Not found |
| E3 | same | `CSK14A-BL` | `14A` | `14A` printed, but `14A` is not a whole part of `CSK14A-BL` | Found (code printed) - see Q1 |
| E4 | SIRIM scan | `WC-8038` | empty | no text layer | Cannot check |
| E5 | PPS 04xxxFC | `BM-2201` | empty | prints `BM-2201` | Found |

Ingest after R8, same SPAN PDF read again: `14A` links `SV-14A-CP` (whole part) only; `CSK14A-BL`,
`BRD7711CP`, `FUR-A11C` are not linked and nothing is reported for them (they were never printed).

## Edge cases

- Shared certificate (company NULL): listed once; the report is company-scoped like the register.
- Archived certificates: listed (their links still project onto products); filter by status.
- Encrypted / broken PDF: Cannot check, like a scan.
- A product linked by a set expansion: verdict uses the printed SET code (the Code on certificate).
- A renewal does not re-derive coverage (REV-2), so its links get a fresh verdict against the new PDF.
- 10k links x ~1 PDF read per certificate: the backfill reads each PDF once (not once per link).

## Owner answers (crew, 8 Nov) - these override the rules above where they differ

- **Q1: not (a) as written.** A link is FOUND when the printed code (whole token on the PDF) is
  CONTAINED in the product code as a contiguous run of 3+ characters with a digit (`14A` inside
  `CSK14A-BL`, `WB 1515` inside `SRTWB1515`); digits-only = Check; a code a person typed always counts.
  E3 therefore reads Found. The exact tiers count too (own code, printed set code, `A + B` parts).
- **Q2 (a)** certificates only. **Q3 (a)** Confirm flips source to manual, audit "was AI".
- Recorded deviations (R3 lazy check instead of a deploy job, R6 one audit row per link): see the plan.

## Questions as asked (3, each with a recommendation)

Q1. **What "Found" means when the Code on certificate is a whole token on the PDF but only a fragment
    of the product code** (E3: `14A` printed, product `CSK14A-BL`). (a) Not found: the printed code must
    also be a whole dash-delimited part of the product code (or the Code on certificate was typed by a
    person); (b) Found: the printed code is on the PDF, the product side is not checked.
    **Recommend (a)**: it is exactly the over-match being cleaned (the AI Suggested `14A` for
    `CSK14A-BL` from a substring); a person can still type a Code on certificate and Confirm.
Q2. **Ingest tightening scope.** (a) certificates only: substring and family-prefix off, printed
    whole-token check on, everything else unchanged; (b) also tighten flyers / spec sheets on the same
    attachment-link path. **Recommend (a)**: the lane's evidence is certificate links; the
    `WC7601 -> MWC7601-RL-S12` substring case the resolver was built for is a flyer case, and changing
    it needs its own evidence.
Q3. **What Confirm stores.** (a) flip the link's `source` to `manual` (no migration; #2245 already
    treats manual links as verified on quotes; the audit row keeps "was AI"); (b) new
    `confirmed_by` / `confirmed_at` columns, source stays `ai`. **Recommend (a)**: simplest thing that
    works, and "a person stands behind this link" is what `manual` already means to every reader.

## Not in v1 (named triggers)

- OCR for scanned certificates: when the data request shows scanned links are a material share.
- Auto-remove of Not found links: never without a person (owner rule); a "select all Not found" bulk
  action covers the clean-up.
