# PLAN - Quotation as a DOCUMENT (multi-scope, cover letter, issue snapshot)

> **Table names in this document predate the schema move.** On 2026-08-15 the projects
> module's 47 tables moved into a dedicated `projects` Postgres schema and the 34 that
> carried a `project_` prefix dropped it: `project_leads` is now `projects.leads`,
> `project_quotation_lines` is `projects.quotation_lines`, and so on. The 13 unprefixed
> ones only changed schema. Nothing else in this document changes. See
> [ADR-0011](../adr/0011-project-sales-tables-live-in-the-projects-schema.md) and
> `documentation/plans/PLAN-projects-schema-move.md` for the full mapping.

**Status:** S1-S8 implemented on `feat/project-lead-to-so` (2026-08-04), verified end to end in a
browser against real production-copy data (the Tuju Residences quotation, RM 1,805,907.02): signed
as Sorento, minted the counter-sign link, signed as the customer at 375px, and confirmed the scope
and the project both moved to `won`. Remaining gaps are listed under "Known gaps" below.

The UAC's five open questions were answered on 2026-08-04 and are folded in: running-number
`Our Ref`, both-sides e-sign, free-text bands, one Excel sheet per scope, one terms set per
company. **AC-H7 was overruled by the client the same day**: a counter-signature DOES win the
scopes (see the scope note below, which records the superseded reasoning).
**UAC:** `documentation/plans/UAC-project-quotation-document.md`
**Slug:** project-quotation-document

---

## The decision that shapes everything: what gets restructured

Today `project_quotations` IS a scope: it carries `scope_label`, its own `outcome`, and its own
version chain (`project_quotation_versions` → `project_quotation_lines`). The client needs a
document that carries SEVERAL scopes.

Two ways to get there, and the cheap-looking one is wrong:

**Rejected - move scopes under the version.** Add `scope_id` to lines, make the version the
document revision, and scopes children of it. This breaks the one thing the current model got
right: **outcome is per scope and is not a property of a revision.** Winning the townhouse is
not a fact about R2. It also invalidates every FK that points at a version (`project_purchase_
orders.quotation_version_id`, `project_samples.quotation_version_id`, task links, the amendment
and divergence flows), for no gain.

**Chosen - add a document layer above, keep the scope's chain intact.**

```
project_quotation_documents        (NEW)  header, recipient snapshot, cover letter, terms
  └─ project_quotations            (kept) = ONE SCOPE. label, outcome, series, sort_order
       └─ project_quotation_versions (kept) line-set revisions of that scope
            └─ project_quotation_lines (kept, +columns)
project_quotation_issues           (NEW)  R1, R2 … what the customer holds
  └─ project_quotation_issue_scopes(NEW)  which version of each scope this issue contained
```

Every existing invariant survives untouched: per-scope outcome, `MAX(version_no)` = current,
snapshot-at-quote-time lines, and every FK. The migration is additive - one document per
existing quotation, `sort_order = 0` - so **AC-G1 is a backfill, not a rewrite**.

The client's "tabs" are `project_quotations` rows under one document. The sample workbook's
"bands" are the same rows rendered as sections instead of tabs, plus in-scope band markers
(AC-C3). One model, two renderings.

### An ISSUE is a set of (scope, version) pairs

This is the part worth stating plainly. A revision does not force every scope to move, and the
customer holds one PDF, not N scope-chains. `project_quotation_issue_scopes` records exactly
which `version_id` each scope contributed to `R2`, so "what did we send them in February" is a
lookup, not a reconstruction. The rendered cover letter, the rendered terms and the grand total
are frozen onto the issue for the same reason lines are snapshotted onto a version.

---

## Schema

**`project_quotation_documents`** - `id`, `project_id` FK, `document_no` (series),
`your_ref`, `doc_date`, `recipient_party_id` FK, `recipient_name_snapshot`,
`recipient_address_snapshot`, `recipient_phone_snapshot`, `attn_name`, `subject_title`,
`cover_letter_html`, `terms_html`, `signatory_name`, `signatory_phone`, `created_by`,
timestamps, `CompanyScopedMixin`.

**`project_quotations`** (existing) - add `document_id` FK NOT NULL (after backfill),
`sort_order`. `scope_label`, `outcome`, `loss_reason`, `decided_at`, `series_id` all stay.

**`project_quotation_lines`** (existing) - add `item_label` VARCHAR(8), `brand_snapshot`
VARCHAR(100), `technical_spec` TEXT, `complete_set` VARCHAR(100), `is_rate_only` BOOL NOT NULL
DEFAULT false, `band_label` VARCHAR(150) NULL (a line that STARTS a band carries the label;
no second table, so a band cannot orphan itself from its lines).

**`project_quotation_issues`** - `id`, `document_id` FK, `issue_no` INT, `our_ref_text`,
`issued_at`, `issued_by`, `cover_letter_rendered`, `terms_rendered`, `grand_total`,
`pdf_attachment_id`, `xlsx_attachment_id`. Unique `(document_id, issue_no)`.

**`project_quotation_issue_scopes`** - `issue_id` FK, `quotation_id` FK, `version_id` FK,
`sort_order`, `scope_total`. Unique `(issue_id, quotation_id)`.

**`quotation_signatures`** - `id`, `owner_kind` (`user` | `customer`), `user_id` FK NULL,
`image_attachment_id` FK (the rendered PNG - drawn, typed or initials all end as one image),
`mode` (`draw` | `type` | `initials`), `signed_at`, `ip_address`, `user_agent`, `gps_lat`,
`gps_lng`. A user's reusable signature is the row with `owner_kind='user'` and no issue binding;
applying it to an issue COPIES it, so re-drawing later cannot alter a signed document.

**`project_quotation_issues`** also carries `sorento_signature_id` FK (required to issue),
`customer_signature_id` FK NULL, `accepted_at` NULL, `signed_pdf_attachment_id` NULL,
`sign_token` (the tokenised counter-sign link) and `sign_token_expires_at`.

**`quotation_templates`** - `id`, `kind` (`cover_letter` | `terms`), `name`, `body_html`,
`is_active`, `CompanyScopedMixin`. One active per `(company, kind)`, enforced by a partial
unique index - the `system_settings` lesson: a singleton nothing enforces becomes two rows and
then reads are non-deterministic.

**Numbering.** No new counter. `document_numbering_rules` gains a `project_quotation` row and
`NumberingService.get_next_number` claims the number at document create. `Our Ref` on an issue is
`{document_no} (R{issue_no})`; the document number itself never changes across revisions.

**Totals rule (one place, not three).** `is_rate_only` lines contribute zero. Scope total,
document grand total and issue `grand_total` all come from one service function; no
recomputation in a serializer, no arithmetic in the FE.

---

## Slices

| # | Slice | Ships |
|---|---|---|
| **S1** | Document layer + backfill | Tables, migration (one document per existing quotation), `document_id` NOT NULL, model + schema + service, CRUD routes. Existing tests must pass unedited (AC-G2). |
| **S2** | Header FE + scope tabs | Document detail page: header block (prefilled, AC-A2), scope tabs, add / rename / reorder / delete scope. Per-tab `PanelDataGrid` with the footer total (AC-D1) and the standard pagination bar (AC-D4). |
| **S3** | Line columns | `item_label`, brand, technical spec, complete set, `is_rate_only`, band markers. Editor + totals honouring rate-only (AC-C2). Grand total across tabs (AC-D2). |
| **S4** | Cover letter + terms templates | `quotation_templates`, admin screen under Project Sales Setup, rich-text + merge-field picker, render-on-create into the document's own copy (AC-E2). |
| **S5** | Signature capture | `SignaturePad` component: draw (mouse / touch), type, initials - one PNG out of all three. Saved to the user, reused with one click, re-drawable. Metadata: signed at, IP, user agent, GPS when the browser gives it. **Net-new: the repo has no signature capture today** - `signature` is a declared form field type with no renderer. |
| **S6** | Issue + PDF | `issue` action: require the owner's signature, freeze, stamp `R{n}`, snapshot letter/terms/totals/(scope,version) pairs, render PDF in the sample's layout via the existing WeasyPrint pipeline, store as an attachment. Re-download serves the stored file (AC-F3). |
| **S7** | Customer counter-sign | Tokenised public page in the existing `(auth)` portal family: read-only quotation, Sign action, identity confirmation reused. Stores the customer signature + metadata on the issue, stamps `Accepted`, regenerates the PDF with BOTH signatures. |
| **S8** | Excel export | One sheet per scope, sample column set, per-sheet total, grand total stated on the first sheet. |

S1 and S2 are the ones that answer images 40-41 on screen. S6 is what makes the record match what
the customer holds; S7 is what makes acceptance a fact rather than an email thread.

### Scope note - the counter-sign flow

The client's reference is the ecohub handover screen (drawn signature, `SIGNED AT` / `IP ADDRESS`
/ `GPS LOCATION` beside it). S7 does NOT need a new portal: contact-facing tokenised pages already
live under `(auth)` with an identity confirmation step, and the counter-sign page joins that
family. What it does need is a decision the UAC flags: **acceptance does not win the scopes**
(AC-H7). A signed quotation is evidence; the scope is won when the salesperson says so or a PO
lands. Building it the other way would flip projects to won on a signature and then need unwinding
when the PO never arrives.

> **Superseded 2026-08-04.** The client overruled this: a counter-signature IS the commitment, so
> acceptance marks every scope the issue carried as won and the project outcome follows. Shipped
> that way. One exception is kept and tested: a scope somebody already marked LOST is not flipped,
> because a signature must not silently overrule a human decision.

### Known gaps

- **The letterhead is a stub.** The sender block prints `Sorento`, not
  `SORENTO SDN BHD (694526-P)` with an address and phone. `companies` has only `name`, `code` and
  `logo_url` - there is nowhere to put them. The UAC's artifact table already marks this row `✗`.
  Needs letterhead columns on `companies` plus an admin screen, in its own slice.
- **The internal line editor still prints `RM 0.00`** on a zero-priced set component. The three
  CUSTOMER-facing surfaces (PDF, workbook, counter-sign page) leave it blank; the editor is an
  input surface where a blank cell is ambiguous with "not filled in yet", so it was left alone
  deliberately rather than by omission.
- **The per-scope page `/quotations/{quotationId}` has no inbound link.** Dead but harmless.
- **S5's "saved to the user, reused with one click"** is not built. The pad captures a signature
  every time; it is not yet stored against the user for re-use.

### Scope note - the template designer

The client pointed at `dreamz_ems .../settings/templates`. That is a drag-and-drop block
editor: palette (heading / text / image / table / repeater / QR), canvas, settings panel, PDF
preview - roughly 3,500 lines of editor plus its own block-render pipeline and a
`template_contexts` merge-field registry. Porting it is its own project.

**S4 ships a rich-text template with a merge-field picker instead**, which is what a cover
letter actually is: a page of prose with names filled in. The block editor earns its keep for
badges and marketing emails, where layout is the content. If the client wants the full designer
afterwards it is a separate plan, and nothing in S4 blocks it - the template stores HTML either
way.

---

## Test plan (Phase 2 is test-first)

- **pytest** - backfill migration leaves totals unchanged on the real dev copy; issue freeze is
  idempotent; rate-only excluded from all three totals; per-scope outcome still derives the
  project outcome; a leak test per new table; PO / sample binding unaffected.
- **vitest** - header prefill renders from project + party; scope tabs add / reorder; footer
  total per tab and grand total across tabs; rate-only renders "rate only" and does not move the
  total; template edit does not mutate an existing document.
- **playwright** - sidebar → project → Quotations → new document → add two scopes → price both
  → issue → PDF downloads and re-download after a template edit returns the ORIGINAL text.

## Grill findings (self-grill, step 4)

Two holes the first draft had. Both are recorded because each would have shipped as a silent
data bug rather than a visible failure.

**1. Issuing must freeze, or R1 rewrites itself.** `project_quotation_issue_scopes` points at a
`version_id`, but today a line edit mutates the CURRENT version in place - a new version is only
created by an explicit "new revision" action. So editing a line after issuing R1 would rewrite
the very rows R1 claims to have contained, and the PDF on file would stop matching the record
behind it.

The fix has to respect how frozen is already defined. `project_quotation_service.is_frozen` is
DERIVED - `version_no < MAX(version_no)` for the scope - and the model comment is explicit that
there is deliberately no `is_frozen` flag, because two facts that must agree drift the first time
a write half-fails. Stamping `frozen_at` on the current version would introduce exactly that
second fact: the highest-numbered version would claim to be frozen while the derivation says it
is current.

So the definition is EXTENDED rather than replaced, and stays derived:

```
frozen  =  version_no < MAX(version_no)        (superseded by a later revision)
        OR EXISTS (issue_scopes WHERE version_id = this)   (already sent to the customer)
```

An issued version is frozen because the customer holds it, and editing it raises the existing 422
telling the reader to revise - which opens the next version carrying the lines, through the
`revise()` path that already exists and is already tested. Nothing is stamped, nothing can
disagree, and no empty placeholder version is created at issue time.

A test asserts that editing a line on an issued version is refused, and that the rows the issue
points at are byte-identical afterwards.

**2. `document_numbering_rules` has no company.** `doc_type` is globally unique and the table
carries no `company_id`, so SRT and MOCHA would draw from ONE counter and print the SAME prefix -
the first cross-company quotation would expose it, and by then numbers are already on customer
documents. Options: (a) accept one shared series, (b) add `company_id` and make the unique key
`(company_id, doc_type)`, (c) encode the company in the prefix template. **[DECISION NEEDED]** -
written as (b), because a customer-facing running number that two companies share is not a series,
and (c) leaves the counter shared anyway.

## Risks

1. **`document_id` NOT NULL** needs the backfill in the same migration; a two-step deploy would
   leave a window where a create fails. Backfill, then set NOT NULL, in one revision.
2. **Alembic head** - this branch is already at 326. Chain onto the committed head and verify a
   single head before deploy (the dual-head lesson).
3. **A signature is a legal-ish artifact.** The image and its metadata are snapshotted onto the
   issue, never referenced live from the user's reusable signature - otherwise re-drawing a
   signature silently rewrites every document already signed with it. Same rule as lines and
   templates, and the one most likely to be got wrong by "just point at the user's signature".
4. **The dev DB is a copy of prod data.** The backfill runs against real quotations; it must be
   idempotent and re-runnable, JOIN-based, "set where mismatch" rather than "where NULL".
