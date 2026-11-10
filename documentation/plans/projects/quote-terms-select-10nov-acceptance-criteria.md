# UAC: QUOTE-TERMS-SELECT

Plan: `PLAN-quote-terms-select-10nov.md`. Lane PR #2305.

## A. Payment terms master (AutoCount, read-only)

- **A1** `POST /external/ingest/payment_terms` (contract 2.14) creates one `payment_terms` row per
  company per code (`code` = AutoCount `Terms.DisplayTerm`), updates it on a re-push, and never
  touches another company. `GET /external/contract` lists the entity and its fields.
- **A2** `/payment_terms/deletions` only deactivates. The read door returns the stored fields.
- **A3** A non-dry push links every terms template and unlocked quotation of that company whose
  legacy payment-terms text equals an ACTIVE term's DisplayTerm exactly (edge padding ignored) and
  that has no term yet. Printed text is not rewritten. A dry run links nothing.
- **A5** The feed record is `code` (DisplayTerm, prints), `rule` (AutoCount Terms, the calculation
  rule) and `is_active`; AutoCount has no description or day count.
- **A6** Master Data > Payment Terms lists every synced term (active or not) read-only: Term,
  Rule, Company, Status; search over term and rule; sortable columns.
- **A4** The CRM never writes AutoCount and has no screen that edits a term.

## B. Payment Terms field

- **B1** Terms template dialog and the quotation's Terms tab show Payment Terms as a clearable
  searchable select of this company's ACTIVE terms, one line per term: the AutoCount DisplayTerm
  only. Asterisk-prefixed variants are listed after the plain ones.
- **B2** Picking a term saves `payment_term_id` and prints the label; clearing clears both.
- **B3** A term of another company, an unknown id or an inactive term is refused with 422
  `payment_term_unknown`.
- **B4** A term picked earlier and later deactivated still shows as picked and still prints.

## C. Validity field

- **C1** Validity is a number (1..999) and a unit (Days / Weeks / Months / Years), sent as a pair.
- **C2** It prints upper-case, plural when the number is not 1: `2 WEEKS`, `1 MONTH`, `30 DAYS`.
- **C3** Half a pair, a unit outside the four, or a number outside 1..999 is refused with 422.
- **C4** Emptying both clears the validity.

## D. Legacy text (no silent loss)

- **D1** A legacy free text nobody has picked over shows as `Current: <text>` under its field and
  keeps printing on cover, PDF and sign link.
- **D2** A save that does not touch the field leaves the legacy text as it is.
- **D3** The migration fills `validity_value` / `validity_unit` where the legacy validity text is
  exactly a number and a unit (`30 days`, `2 Weeks`), and leaves the text untouched.

## E. Where it applies

- **E1** Terms template default (Quotation Templates > Terms > Edit Default / Add).
- **E2** A new quotation copies the active template's term and validity (picks and texts).
- **E2b** Owner Q3: when the project's customer carries AutoCount debtor terms
  (`payment_terms_code`, customer feed contract 2.14) naming an active synced term's DisplayTerm exactly, that term is
  the new quotation's default instead of the template's; validity stays the template's.
- **E3** The quotation form's Terms tab edits its own copy; the cover preview prints the picks
  before save.
- **E4** Issue freezes the printed text as before; nothing already issued changes.
