# UAC: finance module, billing documents from AutoCount (issue #1309)

Plan: `documentation/plans/finance/PLAN-finance-billing-documents-27sep.md`. Alignment page:
`documentation/plans/finance/alignment/finance-alignment-r2.html` (round 2, the rulings; round 1
with the original questions is `finance-alignment-r1.html`). S0 build brief:
`documentation/plans/finance/S0-build-brief.md`.

Status: draft, round 2 (27 Sep). The owner's 13 rulings (plan section 0) are folded in: Q1 to Q4
and Q6 to Q13 are settled, so their "(Q#)" markers are gone. Still marked: "(Q5)" (staff only,
being confirmed) and "(Q14)", "(Q15)", "(Q16)" (new, plan section 9). Every changed AC keeps its
id; new ACs are appended at the end of their slice (S0-22, S1-9, S1-10, S2-11, S2-12). Changed in
round 2: S0-2, S0-3, S0-12, S0-16, S0-22 (new), S1-1, S1-4, S1-5, S1-8, S1-9 (new), S1-10 (new),
S2-1, S2-3, S2-11 (new), S2-12 (new), S3-3, S4-1, S4-2, S4-3. Nothing is built.
Track: full (new module, new schema, a migration, new permissions, a new external ingest entity).

Tags: `[BE]` pytest (Postgres only), `[FE]` vitest, `[E2E]` recorded agent-browser run (no new
Playwright spec), `[T]` text or copy check. Every AC traces to a journey step (J1 to J9).

## The ask (owner, 27 Sep 15:20 MYT, verbatim)

> we need to start working on the financial module in our system as we will ingest the invoices,
> CN and any billing documents (in ERP i think the best practice is to have billing documents of
> differne types like invoices, Cn, DN, etc.) cause we are gonna ingeest that from shared service,
> we will let autocount open that for us after signing NDA with the relevant parties, so let's
> start planning and executing that

## Journey

Three actors. Nobody in the CRM types a billing document: AutoCount is the book of record, the
shared service carries it, the CRM shows it and counts it. So the journey has no create or edit
step, and the fewest-decisions rule is met by there being none to make beyond "which filter".

**The shared service (system actor), J1 to J3**

- **J1.** After the NDA, AutoCount opens its billing tables (IV, CS, CN, DN) to the shared
  service. The shared service pushes each document, header and lines together, to the same
  endpoint it already uses for sales orders, naming the company (`companyCode`). The CRM already
  knows the customers, sales agents and products by the refs and codes the SO feed established,
  so a document never carries anything the CRM must be told twice.
- **J2.** A document changed or cancelled in AutoCount is pushed again, whole. The CRM updates it
  in place; a cancelled one stays visible and stops counting. A document deleted in AutoCount
  arrives as a deletion.
- **J3.** History from the start date the owner sets on the shared service (1 Jan 2023 planned)
  arrives through the same endpoint in batches. The CRM takes any date it is sent. Pushing any
  batch twice changes nothing.

**The owner or a manager reading sales, J4 to J5**

- **J4.** Opens Sales > Yearly comparison or Sales report (PR #1269). The Basis filter now offers
  **Invoiced** beside Ordered and Delivered. Picking it shows invoices plus cash sales plus
  debit notes minus credit notes, excluding tax, filed by document date, in ringgit.
- **J5.** The figure tallies with the AutoCount yearly sales PDF for the same months (2024
  onwards) and the same grouping: each document counts for the team its sales agent was in on the
  document date, and a document whose agent had no team shows under "No team". The basis line
  under the filters says which documents were counted.

**Staff in sales admin or accounts, J6 to J9**

- **J6.** Sidebar > FINANCE > Billing Documents (for roles granted Finance on the Roles screen;
  admin and superadmin by default). A list of every billing document of the current
  company, newest first, with type, number, date, customer, agent, total and status. Filters:
  type, date, customer, agent, status. Search by document number or customer.
- **J7.** Clicks a row. The record page shows the header (type badge, number, status, date,
  customer, agent, currency), the lines, the tax and totals, and the documents it is linked to:
  the sales orders its lines came from, the invoice a credit note is against, the credit notes
  against an invoice. Prev and next walk the list.
- **J8.** From a sales order's record, or a customer's record, the same documents are one click
  away (S3).
- **J9.** A dealer on the portal sees none of this (Q5, being confirmed).

## S0: model and ingest contract, with a replayable fixture

- **S0-1 [BE]** (J1) Given the migration `fin_0001_billing_documents` has run, when the schema is
  listed, then schema `finance` holds `billing_documents` and `billing_document_lines`, both with a
  NOT NULL `company_id` FK to `companies`, and `app_modules_catalog` holds a `finance` row with
  `is_core = false` and no `tenant_modules` row (dormant until switched on in App Store).
- **S0-2 [BE]** (J1, J6) Given the migration, when `user_permissions` is read, then
  `finance.billing_documents.{view,export,edit,delete}` exist, each granted to `admin` and
  `superadmin` and to no other role by name (the `sales_0001_teams` precedent; everyone else on
  the Roles screen). `edit` and `delete` are the ingest and deletions gates only; no UI uses
  them. (Q16: if answered (a), `edit`, `delete` and `view` are also granted to every role holding
  `scm.sales_orders.edit`; if (b), they are not.) The same four slugs are declared in
  `app/rbac/permission_registry.py`, so a `create_all` + `sync_permissions` database has them,
  and `permission_module_map` maps prefix `finance` to module `finance`. Running the migration's
  grant twice adds no row.
- **S0-3 [BE]** (J1) Given `document_type` has a CHECK constraint, when a row with a type outside
  `invoice`, `cash_sale`, `credit_note`, `debit_note` is inserted, then Postgres rejects it; each
  of the four is accepted.
- **S0-4 [BE]** (J1) Given the replayable fixture `tests/fixtures/finance/billing_documents_v1.json`
  (one IV with two lines linked to an SO line, one CS with no SO, one CN against that IV, one DN,
  one cancelled IV, one USD IV), when it is pushed to `POST /api/v1/external/ingest/billing_documents`
  with `companyCode`, then the response is 200 with six `created` verdicts and the rows match the
  fixture field for field.
- **S0-5 [BE]** (J3) Given S0-4 has run, when the same fixture is pushed again, then every verdict
  is `unchanged`, row counts are unchanged and no row's `updated_at` moves.
- **S0-6 [BE]** (J2) Given S0-4 has run, when the IV is pushed again with one line's quantity
  changed and one line removed, then the verdict is `updated`, the changed line keeps its id, the
  removed line is gone, and the header totals are those of the payload.
- **S0-7 [BE]** (J1) Given an IV and a CN share the same AutoCount DocKey number (separate key
  spaces per document table), when both are pushed, then they land as two documents: the
  idempotency key is `(company, document_type, source_ref)`, never `source_ref` alone.
- **S0-8 [BE]** (J2) Given a stored document, when it is pushed with `status: "cancelled"`, then the
  row and its lines stay, `status = 'cancelled'`, and the verdict is `updated`.
- **S0-9 [BE]** (J2) Given a stored document with `source_modified_at` T2, when a push carries the
  same document with `source_modified_at` T1 < T2, then nothing is written and the verdict is
  `unchanged` with the warning `stale_ignored`.
- **S0-10 [BE]** (J2) Given a stored document, when `POST /external/ingest/billing_documents/deletions`
  names its ref, then the document and its lines are hard deleted and the verdict is `deleted`;
  when a CN is still linked against it, then it is set `cancelled` instead and the verdict is
  `deactivated`.
- **S0-11 [BE]** (J1) Given a document whose `customer_ref` and `customer_code` resolve to no
  customer, when it is pushed, then it lands with `customer_id` NULL, `debtor_code` kept, and the
  warning `customer_unresolved`; a line whose product resolves to nothing lands with `product_id`
  NULL and `item_code` kept (never retryable: a billing document is money, and dropping a line
  would change a total).
- **S0-12 [BE]** (J1) Given a CN whose `against_doc_no` names an IV not yet pushed, when the CN
  lands, then `against_document_id` is NULL and `against_doc_no` is kept; when the IV lands later,
  then the CN's `against_document_id` is filled by the IV's ingest.
- **S0-13 [BE]** (J1) Given an IV line whose `from_line_ref` is an SO line's integration ref, when
  it lands, then `sales_order_line_id` points at that line; given a ref that resolves to nothing,
  then it stays NULL with `from_doc_type`, `from_doc_no` and `from_line_ref` kept as sent.
- **S0-14 [BE]** (J1) Given company A anchors the push, when a document's customer resolves only in
  company B, then the customer is not linked (warning `customer_unresolved`); a read-back under B
  of a document written under A answers `not_found`.
- **S0-15 [BE]** (J1) Given a push without `companyCode` and without an integration binding, then
  422 `COMPANY_ANCHOR_REQUIRED` (the existing anchor, unchanged).
- **S0-16 [BE]** (J1) Given a caller holding `scm.sales_orders.edit` but not
  `finance.billing_documents.edit`, when it pushes `billing_documents`, then 403; the same for
  `/deletions` without `.delete` and `/read` without `.view`. Holding `.view` or `.export` alone
  never lets a caller push.
- **S0-17 [BE]** (J1) Given the fixture has landed, when `POST /external/read/billing_documents`
  asks for its refs, then each comes back in the canonical shape it was pushed in (money as JSON
  numbers), with `entity_id` per header and per line.
- **S0-18 [BE]** (J1) Given `GET /api/v1/external/contract`, then `version` is `"2.6"` and
  `fields_added` names `billing_documents` with its fields.
- **S0-19 [BE]** (J1) Given a record with `extra` keys, a negative quantity on an IV, a total that
  is not `net_total + tax_total` within 0.01, or more than 2000 lines, then that record is
  `failed` with the field named and the rest of the batch lands.
- **S0-20 [BE]** (J3) Given a batch of 1000 fixture-shaped documents of 5 lines each, when it is
  pushed on the CI database, then it completes inside the ingest route's existing timeout and
  writes one `integration_references` row per document.
- **S0-21 [T]** (J1) The contract section for `billing_documents` is appended to
  `documentation/plans/autocount/PLAN-autocount-cross-repo-contract.md` as section 12, so the
  shared service has one contract of record.
- **S0-22 [BE]** (J3) Given documents dated 2019-06-30, 2022-12-31 and 2023-01-01, when they are
  pushed, then all three are `created` and stored with their dates: the CRM has no start-date
  floor and no start-date setting, because the shared service owns the start (ruling Q2).

## S1: the invoiced basis on the sales reports

Depends on PR #1269 (the reports kernel dataset and the Basis filter), merged to main at 52b0ac24,
and on #1260's dated `sales.team_members` for the grouping (ruling Q8).

- **S1-1 [BE]** (J4) Given the S0 fixture in company A, when the Yearly comparison runs with Basis
  = Invoiced, then the fixture month's figure is IV net + CS net + DN net - CN net, excluding
  tax, in MYR (`local_net_total`), the cancelled IV and the USD IV's foreign amount excluded or
  converted as stored, filed under each document's `doc_date`.
- **S1-2 [BE]** (J4) Given a CN dated in a later month than its IV, then the CN reduces the CN's
  own month, never the IV's month.
- **S1-3 [BE]** (J4) Given the Basis filter, then its options are Ordered, Delivered and Invoiced;
  Delivered stays the default until the owner rules otherwise.
- **S1-4 [BE]** (J5) Given the invoiced basis, then each document counts in the block of the team
  its `sales_agent_id` belonged to on its `doc_date` in its company (a `sales.team_members` row
  with `coalesce(valid_from, -infinity) <= doc_date <= coalesce(valid_to, infinity)`), the block
  headed by the team's name (Q14), never by `demand_class` and never by the agent's current
  class. Given an agent who moved from team A to team B on the 15th, then a document of the 14th
  counts for A and one of the 15th for B. The Channel filter on Invoiced lists the company's
  teams plus "No team".
- **S1-5 [T]** (J5) Given Basis = Invoiced, then the basis line under the filters and in the
  workbook reads "Basis: Invoiced (invoices, cash sales and debit notes less credit notes,
  excluding tax), by document date, grouped by the sales agent's team on that date."
- **S1-6 [BE]** (J4) Given the chatbot's `crm_sales_analysis` tool, when asked for invoiced sales,
  then it answers from the same dataset (one query layer, as #1269 built it).
- **S1-7 [BE]** (J4) Given a caller without `finance.billing_documents.view`, then Invoiced is
  still offered on the sales reports (the report's own slug `sales.reports.view` gates it; the
  report shows totals, never a document).
- **S1-8 [E2E]** (J4, J5) The owner's three chosen months, all in 2024 or later, run on the prod
  copy after the backfill, are recorded against the PDF in this file's "Measured" block, per team
  block and for "No team".
- **S1-9 [BE]** (J5) Given a document whose agent did not resolve (`sales_agent_id` NULL), a
  document whose agent has no team row covering its `doc_date`, and a document whose agent is in
  no team, then all three count in one "No team" block that sorts last, is omitted when empty,
  and is included in the company total; the company total on Invoiced equals the ungrouped
  invoiced sum.
- **S1-10 [BE]** (J5) Given an IV whose own agent differs from the agent on the SO its lines came
  from, then it counts whole for its own agent's team (Q15).

## S2: the Finance menu, list and record pages

Phase 1 against a mock, then Phase 2 wiring, per the pipeline.

- **S2-1 [FE]** (J6) Given a user with `finance.billing_documents.view` and the `finance` module on,
  then the sidebar shows a FINANCE heading with Billing Documents; without either, it does not.
  An admin or superadmin has it without any grant; any other role has it only once granted on
  the Roles screen.
- **S2-2 [FE]** (J6) Given the list, then it is a `DataGrid` with `tableLayout: { width: 'fixed',
  columnsResizable: true }`, columns Type (Badge), Number, Date, Customer, Agent, Total (right
  aligned, currency code when not MYR), Status (Badge), each with an explicit `size`, long text
  truncated with a `title`; no Add button, no row delete.
- **S2-3 [FE]** (J6) Given the filters, then Type, Status, Customer and Agent are
  `SearchableSelect` or `SearchableMultiSelect`, each optional one `clearable`; Date is the
  standard date range; query strings are built with `buildDataGridParams`. The Export button
  shows only with `finance.billing_documents.export` (and view).
- **S2-4 [BE]** (J6) Given `GET /api/v1/finance/billing-documents`, then it pages, sorts and
  searches through the list-query registry (resource `finance_billing_documents`), is scoped to
  the caller's company, and answers 403 without the view slug.
- **S2-5 [FE]** (J7) Given a row click, then `/finance/billing-documents/{id}` opens with a
  `PageHeader` (number, type badge, status badge), a meta strip (source AutoCount, last synced,
  document date), `RecordNavigation` prev and next, and line tabs Details, Lines, Related.
- **S2-6 [FE]** (J7) Given a document with no related documents, then the Related tab renders its
  empty state with the sentence that says so, never a hidden tab.
- **S2-7 [FE]** (J7) Given a CN, then Related shows the invoice it is against (or its raw number,
  unlinked, when the invoice is not in the CRM); given an IV, Related lists its credit notes and
  the sales orders its lines came from.
- **S2-8 [BE]** (J7) Given `GET /api/v1/finance/billing-documents/{id}`, then the header, lines and
  related documents come back in one response with human-readable names (no UUID shown in the UI),
  and a document of another company is 404.
- **S2-9 [E2E]** (J6, J7) Sidebar click from `/` to the list, a filter, a row, prev and next, at
  375 and 1280, recorded as agent-browser evidence under `documentation/plans/finance/evidence/s2/`.
- **S2-10 [T]** (J6) No UI text explains the feature; no UUID is visible anywhere.
- **S2-11 [BE]** (J9) Given a dealer's portal user (a portal role, no finance slug), then every
  `/api/v1/finance/*` call answers 403 and no portal page links to Finance. (Q5, being confirmed:
  staff only.)
- **S2-12 [BE]** (J6) Given `POST /api/v1/list-query/export` for resource
  `finance_billing_documents`, then a caller with `.view` but not `.export` gets 403 and a caller
  with both gets the filtered rows, scoped to the caller's company.

## S3: billing on the records people already open

- **S3-1 [FE]** (J8) Given a sales order record, then an "Invoices" section lists the billing
  documents whose lines point at its lines, with an empty state when there are none.
- **S3-2 [FE]** (J8) Given a customer record, then a "Billing documents" tab lists that
  customer's documents (the same list component, pre-filtered), with an empty state.
- **S3-3 [BE]** (J8) Given a user without `finance.billing_documents.view` (any role not granted
  it on the Roles screen), then neither section is rendered and the backing calls answer 403.

## S4: history backfill and the tally

Mostly shared-service work; the CRM side is a runbook and a measurement.

- **S4-1 [T]** (J3) A runbook `documentation/plans/finance/RUNBOOK-billing-backfill.md` records the
  start date as set on the shared service (1 Jan 2023 planned; the CRM holds no copy of it), batch
  size (1000), order (oldest first, IV and CS before CN and DN), the permission grant to the
  feed's role when Q16 is (b), the check that every agent on the documents has a team (the
  "No team" count per month), the check queries and the re-run rule (safe: S0-5).
- **S4-2 [E2E]** (J3) After the backfill on production, documents per type per month from the
  start date match AutoCount's own counts, and the three test months (2024 or later) are
  recorded here.
- **S4-3 [E2E]** (J5) The Yearly comparison on Basis = Invoiced matches the AutoCount PDF within
  RM 1 per cell for those months, per team block, from 2024 onwards (2023 is loaded but not
  tallied), or the residual is explained cell by cell.

## Measured

_Pending: filled by S1-8, S4-2 and S4-3._
