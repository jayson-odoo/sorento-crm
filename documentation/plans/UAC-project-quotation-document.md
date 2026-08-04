# UAC — Quotation as a DOCUMENT (multi-scope, cover letter, issue snapshot)

**Status:** written, not built. Awaiting the client's grill.
**Slug:** project-quotation-document
**Source:** client review of the built quotation screens (images 40-41) plus the real
artifact `Cabana Elmina - nadi cergas R2.xlsx` (Sorento → Nadi Cergas, 2026-02-26,
TOTAL AMOUNT RM 696,923).

The client's words: *"got a header as like the excel, then can add multiple tabs (meaning
add multiple scope), then in each scope can add lines, then the total we should always put
at the bottom of the corresponding column ... we should also have a cover letter template
also ... a template designer that can design the template for the cover letter, and every
quotation just preset to it"*.

---

## 0. What the real artifact actually contains

Read off the sample workbook rather than imagined, because every gap below is a gap against
a document Sorento has already sent a customer:

| Part | In the sample | In the CRM today |
|---|---|---|
| Sender block | SORENTO SDN BHD (694526-P), address, Tel | ✗ |
| Refs | `Our Ref: (R2)`, `Your Ref:`, `Date: 2026-02-26` | ✗ |
| Recipient block | `To:` party, 4 address lines, 2 phones | ✗ |
| `Attn:` | Kelly | ✗ |
| Subject line | CADANGAN MEMBINA PANGSAPURI RUMAH IDAM | ✗ (project title only) |
| Column set | ITEM / PRODUCT IMAGE / TECHNICAL SPEC / DESCRIPTION / BRAND / PRODUCT CODE / QTY / UNIT RATE / COMPLETE SET / GRAND TOTAL | partial |
| Section bands | `BILL NO 3 PAGE 15/4`, `15/5`, `15/6`, `15/7`, `15/8` | ✗ |
| Item letters | A, B, C … grouping sub-lines (WC + angle valve + hose all under A) | ✗ |
| Alternates | `OPTION`, `OPTIONAL ITEMS FOR OKU TOILET` | ✗ |
| Unpriced-but-quoted | `rate only` / `RATE ONLY` in the total column | ✗ |
| Grand total | `TOTAL AMOUNT … 696923`, under the money column | ✗ (was a toolbar chip) |
| Terms | 8 numbered clauses | ✗ |
| Sign-off | "We trust the above prices are to your satisfaction", Thank You, BASER RAMLI, 019-3508781 | ✗ |

**The sample is ONE sheet with bands.** Other projects (the client's example: townhouse /
guard house / reception) split those bands into separate tabs. Both are the same shape: a
document that carries several priced scopes. Tabs and bands are a rendering choice, not two
data models.

---

## Journey (Phase 0 — written before any schema)

**Actor:** the salesperson who has walked a development and has to send a price.

1. Opens the project → **Quotations** → sees the quotation documents already sent, each
   with its ref, date, recipient and total. Clicks one, or **New quotation**.
2. The new document arrives **already filled in**: sender block from the company, recipient
   block from the project's developer / main contractor party (address, phones), `Attn:`
   from the party's primary contact, subject line from the project title, `Our Ref` from the
   series, date = today, cover letter and terms from the active template. **The only thing
   asked is what is not already known.**
3. Adds a scope tab — *Townhouse* — and prices it. Product picked from the catalogue brings
   its own code, description, brand, image, list price. Quantity is typed; the line total
   computes. A line can be marked **rate only** — quoted, printed, excluded from the total.
4. Adds *Guard house*, *Reception* the same way. Each tab shows its own total at the bottom
   of the money column; the document header shows the grand total across tabs.
5. Reviews the cover letter — it is already written, from the template, with the names filled
   in. Edits this one if this customer needs different words. The template is untouched.
6. **Issue.** The document is stamped `R1`, frozen, and a PDF (and Excel) is produced that
   looks like the workbook above. What the customer holds is now a fact in the system.
7. The customer negotiates. The salesperson opens a revision: `R2`. Only what changed is
   re-priced; the previous issue stays readable exactly as it was sent.
8. Each scope is won or lost **on its own**, and that keeps working: the project stays live
   while any scope is open.

What they hold at the end: a PDF identical in structure to what Sorento sends today, and a
CRM record that can answer "what exactly did we quote them, and when".

---

## Group A — The document

- **AC-A1** A quotation DOCUMENT belongs to a project and carries: `our_ref`, `your_ref`,
  `doc_date`, recipient party, recipient address snapshot, recipient phones snapshot,
  `attn_name`, `subject_title`, `signatory_name`, `signatory_phone`.
- **AC-A2** Every one of those is **prefilled** from the project, the party and the company on
  create (Journey step 2). A field the system can derive is never presented as a blank.
- **AC-A3** The recipient block is **snapshotted onto the document**, not read live from the
  party. A party address edited next year must not rewrite what was sent last year - the same
  doctrine `ProjectQuotationLine` already applies to product facts.
- **AC-A4** A document holds one or more **scopes**, ordered, each with a label. The scope is
  what the UI renders as a tab and the PDF renders as a band.
- **AC-A5** **Per-scope outcome survives.** Won / lost / open, loss reason and decided-at stay
  a property of the scope, and the project outcome stays derived from them (AC-E10 of the
  pipeline UAC). A document with a won townhouse and an open guard house is still live.
- **AC-A6** Deleting a document with any issue is refused, not silently hidden. An unissued
  draft deletes with the standard confirmation.

## Group B — Revisions and what the customer holds

- **AC-B1** An **issue** is a stamped, frozen snapshot of the whole document: `R1`, `R2`, …
  It records which version of each scope's lines it contained, the rendered cover letter, the
  rendered terms, and the grand total at that moment.
- **AC-B2** `Our Ref` prints the issue label the customer quotes back at us (`(R2)` in the
  sample). Current = MAX(issue_no); everything below it is frozen. **No `is_current` flag** -
  two facts that must agree is one fact too many (the rule `ProjectQuotationVersion` already
  states).
- **AC-B3** Re-issuing does not force every scope to change. A scope untouched since R1 keeps
  its lines; the issue records which line-version each scope contributed.
- **AC-B4** A frozen issue is readable, printable and re-downloadable forever, and is never
  edited in place. Editing after issue opens the next revision.
- **AC-B5** Existing bindings keep working: a Project PO or a sample that points at a
  quotation version still resolves, and the detail screens still name the scope it was
  against.

## Group C — Lines, as the real document has them

- **AC-C1** A line carries, in addition to what it carries today: `item_label` (the A / B / C
  letter, optional and free text), `brand_snapshot`, `technical_spec`, `complete_set`.
- **AC-C2** **Rate-only lines.** A line can be quoted with a unit rate and no line total,
  printing `rate only` in the money column and contributing **zero** to every total. The
  sample has five. A system that silently added them would overstate the quote by RM 400+.
- **AC-C3** A scope can contain **section bands** - a labelled break between groups of lines
  (`BILL NO 3 PAGE 15/4`, `OPTION`, `OPTIONAL ITEMS FOR OKU TOILET`). A band is a line-level
  marker, ordered with the lines, not a separate table.
- **AC-C4** A line picked from the catalogue snapshots code, description, brand, image and
  list price at the moment it is added, exactly as today.
- **AC-C5** Every existing floor / non-standard alert keeps firing per line, unchanged.

## Group D — Totals (this is where the client was explicit)

- **AC-D1** Each scope tab shows its own total **at the bottom of the money column**, in the
  table's own footer row - never as a chip beside the toolbar. (Shipped for POs already:
  `DataGrid` renders a `<tfoot>` from `columnDef.footer`.)
- **AC-D2** The document shows a **grand total** across scopes, which is what `TOTAL AMOUNT`
  is in the sample.
- **AC-D3** Rate-only lines are excluded from both (AC-C2), and the UI says so where a reader
  might otherwise doubt the arithmetic.
- **AC-D4** Every list on these screens uses the standard pagination bar - "1 - 1 of 1", page
  picker, rows per page - and never a sentence like "3 scopes in this quotation".

## Group E — Cover letter and terms

- **AC-E1** A **cover letter template** and a **terms template** exist per company, editable
  by an admin, with merge fields for the facts the letter needs (project title, recipient,
  attn, our ref, date, grand total, signatory).
- **AC-E2** A new document renders the active template into its own editable copy. Editing the
  document's letter never touches the template; editing the template never rewrites a document
  already created, and **never** rewrites one already issued (AC-B4).
- **AC-E3** An issue snapshots the RENDERED letter and terms text. What was sent stays
  readable even after the template is rewritten.
- **AC-E4** The editor is rich text with a merge-field picker: bold, lists, links, and
  `{{field}}` insertion. **Deliberately NOT a drag-and-drop block designer in this slice** -
  see the plan's scope note. A cover letter is a page of prose, and the block editor in
  dreamz_ems (~3.5k lines of editor plus its own render pipeline) buys nothing a rich-text
  field with merge fields does not, for this artifact.

## Group F — Output

- **AC-F1** A document issue renders to **PDF** in the layout of the sample: sender block,
  refs, recipient, attn, subject, then each scope as a banded table with the sample's column
  set, then the grand total, terms, sign-off.
- **AC-F2** The same issue exports to **Excel** with one sheet per scope (the client's "tabs"),
  because the customer's QS works in Excel and re-types otherwise.
- **AC-F3** Both are produced from the ISSUE snapshot, not from live rows, so a re-download
  next year is byte-for-byte what was sent.
- **AC-F4** Product images print in the `PRODUCT IMAGE` column when the line has one, and the
  column collapses when no line in the scope has an image (an empty column of blank cells on
  every page is worse than no column).

## Group G — What must not break

- **AC-G1** Existing quotations migrate to exactly one document each, with one scope carrying
  the current `scope_label`, outcome, versions and lines. No data is dropped and no total
  changes.
- **AC-G2** PO binding, sample binding, task links, the amendment/divergence flows and the
  pipeline's derived project outcome all keep working against the migrated shape, proven by
  the existing tests continuing to pass without being edited to fit.
- **AC-G3** Company scoping holds on every new table (`CompanyScopedMixin`), with a leak test
  per table.

---

## Open questions for the client

1. **`Our Ref` format.** The sample shows only `(R2)`. Is there a real reference series
   (e.g. `SRT/Q/2026/0141`) the CRM should generate, or is the ref the project code plus the
   revision?
2. **Who signs?** Signatory is on the document in the sample (BASER RAMLI + mobile). Default to
   the salesperson who owns the project, or a fixed person per company?
3. **Bands.** Are `BILL NO 3 PAGE 15/4` labels copied from the customer's own BQ (so free
   text), or should the CRM know the BQ structure?
4. **Excel export tabs.** One sheet per scope, or one sheet with bands like the sample?
5. **Terms.** One standard set per company, or per project type?
