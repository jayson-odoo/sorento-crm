# PLAN — Quotation as a DOCUMENT (multi-scope, cover letter, issue snapshot)

**Status:** written, not started. Blocked on the client's answers to the UAC's open questions.
**UAC:** `documentation/plans/UAC-project-quotation-document.md`
**Slug:** project-quotation-document

---

## The decision that shapes everything: what gets restructured

Today `project_quotations` IS a scope: it carries `scope_label`, its own `outcome`, and its own
version chain (`project_quotation_versions` → `project_quotation_lines`). The client needs a
document that carries SEVERAL scopes.

Two ways to get there, and the cheap-looking one is wrong:

**Rejected — move scopes under the version.** Add `scope_id` to lines, make the version the
document revision, and scopes children of it. This breaks the one thing the current model got
right: **outcome is per scope and is not a property of a revision.** Winning the townhouse is
not a fact about R2. It also invalidates every FK that points at a version (`project_purchase_
orders.quotation_version_id`, `project_samples.quotation_version_id`, task links, the amendment
and divergence flows), for no gain.

**Chosen — add a document layer above, keep the scope's chain intact.**

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

**`project_quotation_documents`** — `id`, `project_id` FK, `document_no` (series),
`your_ref`, `doc_date`, `recipient_party_id` FK, `recipient_name_snapshot`,
`recipient_address_snapshot`, `recipient_phone_snapshot`, `attn_name`, `subject_title`,
`cover_letter_html`, `terms_html`, `signatory_name`, `signatory_phone`, `created_by`,
timestamps, `CompanyScopedMixin`.

**`project_quotations`** (existing) — add `document_id` FK NOT NULL (after backfill),
`sort_order`. `scope_label`, `outcome`, `loss_reason`, `decided_at`, `series_id` all stay.

**`project_quotation_lines`** (existing) — add `item_label` VARCHAR(8), `brand_snapshot`
VARCHAR(100), `technical_spec` TEXT, `complete_set` VARCHAR(100), `is_rate_only` BOOL NOT NULL
DEFAULT false, `band_label` VARCHAR(150) NULL (a line that STARTS a band carries the label;
no second table, so a band cannot orphan itself from its lines).

**`project_quotation_issues`** — `id`, `document_id` FK, `issue_no` INT, `our_ref_text`,
`issued_at`, `issued_by`, `cover_letter_rendered`, `terms_rendered`, `grand_total`,
`pdf_attachment_id`, `xlsx_attachment_id`. Unique `(document_id, issue_no)`.

**`project_quotation_issue_scopes`** — `issue_id` FK, `quotation_id` FK, `version_id` FK,
`sort_order`, `scope_total`. Unique `(issue_id, quotation_id)`.

**`quotation_templates`** — `id`, `kind` (`cover_letter` | `terms`), `name`, `body_html`,
`is_active`, `CompanyScopedMixin`. One active per `(company, kind)`, enforced by a partial
unique index - the `system_settings` lesson: a singleton nothing enforces becomes two rows and
then reads are non-deterministic.

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
| **S5** | Issue + PDF | `issue` action: freeze, stamp `R{n}`, snapshot letter/terms/totals/(scope,version) pairs, render PDF in the sample's layout via the existing WeasyPrint pipeline, store as an attachment. Re-download serves the stored file (AC-F3). |
| **S6** | Excel export | One sheet per scope, sample column set, per-sheet total + grand total. |

S1 and S2 are the ones that answer images 40-41 on screen. S5 is what makes the record match
what the customer holds.

### Scope note — the template designer

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

- **pytest** — backfill migration leaves totals unchanged on the real dev copy; issue freeze is
  idempotent; rate-only excluded from all three totals; per-scope outcome still derives the
  project outcome; a leak test per new table; PO / sample binding unaffected.
- **vitest** — header prefill renders from project + party; scope tabs add / reorder; footer
  total per tab and grand total across tabs; rate-only renders "rate only" and does not move the
  total; template edit does not mutate an existing document.
- **playwright** — sidebar → project → Quotations → new document → add two scopes → price both
  → issue → PDF downloads and re-download after a template edit returns the ORIGINAL text.

## Risks

1. **`document_id` NOT NULL** needs the backfill in the same migration; a two-step deploy would
   leave a window where a create fails. Backfill, then set NOT NULL, in one revision.
2. **Alembic head** — this branch is already at 326. Chain onto the committed head and verify a
   single head before deploy (the dual-head lesson).
3. **The dev DB is a copy of prod data.** The backfill runs against real quotations; it must be
   idempotent and re-runnable, JOIN-based, "set where mismatch" rather than "where NULL".
