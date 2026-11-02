# PLAN: Quotation cover page + terms print (QUOTE-COVER-PAGE)

**Status:** Build. Sample v2 approved by the owner 2 Nov, every point settled. Track: L (new
columns via migration, new printed page, public countersign payload change). UAC:
`quote-cover-page-02nov-acceptance-criteria.md`.

## Journey

Project sales keeps a one-sheet Excel cover page per quotation (reference, date, attn, company,
contact, address, email, purpose, terms, payment terms, validity, prepared by) and retypes it for
every quotation. The owner wants it inside the quotation: filled from the record, printed as the
first page of the quotation PDF, shown at the top of the customer countersign link, and the terms
printed the way they were written.

## Owner decisions (final, 2 Nov)

1a portrait first page, label/value rows, workbook order. 2a reference = quotation number +
project name, the team's own code goes away. 3a no Fax; Email and Contact from the customer
contact; Purpose optional. 4a one company T&C template editable per quotation; Payment Terms and
Validity pre-filled free text; validity not enforced. Then on mock v1/v2: Prepared By = project
salesperson; Payment Terms / Validity defaults beside the T&C template; letterhead on page 1;
terms on page 1 only (countersign bottom panel goes, tick box stays); Your Ref stays; the
countersign link shows the same cover page.

## Facts the design rests on (origin/main 5ac2eb7fa6)

- Issue snapshot: `issue()` `app/services/project_quotation_document_service.py:517` copies
  `cover_letter_rendered`/`terms_rendered` (:566-567), `our_ref_text` (:563), grand total. No
  header snapshot: the PDF (`project_quotation_pdf_service.py:445-467`) and the countersign
  payload (`serialize_sign_page` `project_quotation_document_service.py:1407`, :1516-1550) read
  attn, recipient, date, subject, signatory LIVE from the document, and `update_document` (:834,
  allow-list :850-862) stays open after issue (only pending/approved lock, `approval_service.py:76`).
- Terms today: `_terms_html` `project_quotation_pdf_service.py:585-593` runs `_text_blocks(...,
  strip_numbering=True)` (:183) and wraps every non-empty line in `<li>` of one `<ol>`: headings
  numbered, blank lines dropped, nested lists flattened. Countersign shows the raw editor HTML
  (TipTap StarterKit) through `sanitizedHtml` + `prose` (`QuotationSignClient.tsx:185-210`).
- Project title `Project.title` (`app/models/projects.py:255`); salesperson = `User.name` of
  `project.owner_user_id`, fallback `document.created_by`
  (`project_quotation_template_service.py:233-237`); FE project response already has `owner_name`
  and `customer_attn`/`customer_phone` (`app/schemas/projects.py:348-356`), built from the main
  `CustomerContact` in `_customers_for` (`project_service.py:1314-1344`).
- Template: `quotation_templates` (`projects.py:1165-1198`), `letter_templates()`
  (`project_quotation_document_service.py:379`) returns the active bodies; form seeds them on
  create (`QuotationFormClient.tsx:278-286`).
- Backend has no HTML sanitiser library (no bleach/nh3 in requirements.txt).

## Architecture

**One shared mechanism, one rule.** A new module `app/services/quotation_cover_service.py` owns
the cover page content for BOTH surfaces:

- `COVER_LAYOUT = 2`, `layout_of(issue)`: the issue's `layout_version` (old rows 1).
- `cover_reference(document, issue, project)` -> `"<quotation_no()> <project.title>"` (title
  omitted when blank).
- `cover_rows(db, document, issue)` -> ordered list of `{key, label, text}` / `{key: "terms",
  label, html}`, empty rows dropped. Keys/labels in order: reference "Reference No.", date
  "Date", attn "Attn", company "Company", contact "Contact", address "Add", email "Email", purpose
  "Quotation Purpose", terms "Terms & Conditions", payment_terms "Payment Terms", validity
  "Validity", prepared_by "Prepared By".
- `clean_terms_html(raw)` -> allow-list HTML built with stdlib `html.parser`: keeps `p, br,
  strong, em, u, ul, ol, li` (b->strong, i->em), drops every attribute, drops `script`/`style`/
  `iframe`/`object`/`embed` with their content, unwraps any other tag (text kept), escapes text,
  balances unclosed tags, turns an empty `<p></p>` into `<p>&nbsp;</p>` so a blank line keeps its
  gap on both surfaces.

The PDF renders `cover_rows` as a table (labels upper-cased with a colon) and the countersign
page renders the same list (labels as given), so order, labels and terms structure cannot drift.

**Old vs new layout = one integer on the issue.** `quotation_issues.layout_version SMALLINT NOT
NULL DEFAULT 1`; existing rows get 1 from the default, `issue()` sets `COVER_LAYOUT`. No python
`default=` on the model column, so a test or path that builds an issue directly keeps layout 1
(today's layout) unless it opts in. Every branch reads `layout_of(issue)`; nothing infers layout
from dates or null columns.

**Values follow today's header rule** (B3): cover values other than terms are read live from the
document/project, exactly like the attn/address/date the price-page header already prints, so page
1 and page 2 cannot disagree. Freezing header values per issue is a pre-existing gap for every
header field; not widened here (noted for backlog).

**PDF** (`project_quotation_pdf_service.py`): layout 2 -> `@page cover { size: A4 portrait }`
plus a `.cover { page: cover; break-after: page }` section (letterhead from `_sender` as
`_header_html` does, title QUOTATION, rows table); the price-page "Quotation No." shows
`cover_reference`; no `_terms_html` after the total. Layout 1 -> byte-for-byte today's path.

**Countersign** (`serialize_sign_page` + `QuotationSignPageResponse` `app/schemas/projects.py:2354`):
new `cover_rows: list | null` (null for layout 1); for layout 2 `our_ref` = `cover_reference`. FE
`QuotationSignClient.tsx`: when `cover_rows` present -> cover card first (sender row moved into
it from `Letterhead`, rows via the refs-row pattern, terms row through `sanitizedHtml` with
explicit list/paragraph classes, label above value under `sm`), bottom terms `ProsePanel` not
rendered, tick box unchanged. `cover_rows` null -> today's page untouched.

**Fields.** `quotation_documents` + `recipient_email_snapshot`, `quotation_purpose`,
`payment_terms`, `validity` (TEXT NULL): model, schemas Base/Create/Update/Response
(`app/schemas/projects.py:1908-2056`), `update_document` allow-list, FE types
(`quotationDocumentService.ts:97/205`), `QuotationDocumentHeader.tsx` (Email under Phone, Purpose
under Subject, Prepared By read-only from `project.owner_name`), `QuotationLetterPanels.tsx`
`QuotationTermsPanel` (Payment Terms + Validity above the editor). `quotation_templates` +
`payment_terms`, `validity` (TEXT NULL): model, schemas (:2141-2165), `letter_templates()` returns
the active terms template's two values, `QuotationTemplateDialog.tsx` two inputs between Name and
Terms, form prefill on create next to the terms seed. Project response + `customer_email` from the
main `CustomerContact.email` (`app/models/order.py:305`), prefilled into Email on create
(`QuotationFormClient.tsx:240-250`).

**Migration** `qcp_0001_cover_page_fields`, down_revision `das_0001_ai_read_ticks`, raw
`op.execute` with `projects.` prefix and `IF NOT EXISTS` (style of
`alembic/versions/qca1_0001_amendment_requests.py`); downgrade drops the seven columns. Applied
and checked on the lane throwaway DB (bootstrapped at `das_0001_ai_read_ticks` before the model
change); idempotent SQL for the shared dev DB at `crew/state/migrations/QUOTE-COVER-PAGE.sql`.

Not touched: the Excel export (omits letter and terms by design), the merge-token set, sign-link
expiry.

## Test list (tester writes red first; coder makes green)

Backend, new `tests/test_project_quotation_cover_page.py` (+ route file if cleaner):
1. `clean_terms_html`: heading/blank/bullets/nested/"- " cases (C1), b->strong, i->em, attributes
   dropped, script/style content gone, link text kept, unclosed tags balanced, empty p -> nbsp p.
2. Issue built directly has `layout_version == 1`; `issue()` stamps 2.
3. PDF layout 2: cover section before the first scope; portrait named page CSS; rows in UAC A2
   order; reference string on cover and in price-page refs; no Fax; empty Purpose row omitted;
   Purpose `<script>` escaped; Prepared By = owner name (fallback creator); Email/Contact values;
   letterhead sender name on cover; no terms block after the total; terms structure on cover.
4. PDF layout 1: no cover, numbered `<ol>` terms after total, "Quotation No." = `<doc>-R<n>` only.
5. Countersign GET (route, through `response_model`): layout 2 `cover_rows` in order with same
   reference as PDF, terms html cleaned, empty rows omitted; layout 1 `cover_rows` null, `our_ref`
   unchanged.
6. Document create/PATCH/GET round-trip of the four fields; template create/update round-trip of
   the two; letter-templates returns them; project detail returns `customer_email`.

Frontend (vitest, touched files only):
7. `QuotationSignClient.test.tsx`: with `cover_rows` -> cover card rows in order, nested list in
   terms row, no bottom terms panel, tick box present, "Quotation from" once; with null -> today.
8. `QuotationFormClient.test.tsx`: create prefills Email / Payment Terms / Validity, save body
   carries the four fields.
9. `QuotationDocumentClient.test.tsx`: view shows Email, Purpose, Prepared By; Terms tab shows
   Payment Terms, Validity.
10. `QuotationTemplatesClient.test.tsx`: dialog has the two inputs; save sends them.

Global guards (table changed): `tests/test_schema_uuid_id_principle.py`,
`tests/test_list_pagination_limit.py`.

## Lane steps

UAC (done) -> tester red tests, `test(red):` commit + red-proof -> coder green -> migration on
throwaway + crew SQL -> kill-proof -> reviewer + security-reviewer (public countersign payload,
HTML from user input) + browser pass (real PDF read by eye, countersign 1280/375) -> guides
(`project-sales-rep/work-a-project-quotation.md`,
`project-sales-admin/set-standard-quotation-terms.md`) -> PR -> hand test script.
