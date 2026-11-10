# PLAN: Quote payment terms from an AutoCount-synced select, validity as number + interval

Status: Merge-ready (owner hand test passed 10 Nov ~16:45; chained after #2301, migration on pname_0001_project_lead_name). Track: L (new master table + migration + ESB
ingest entity; the push side is the shared-service lane SS-PAYMENT-TERMS). UAC:
`quote-terms-select-10nov-acceptance-criteria.md`.

Lane: QUOTE-TERMS-SELECT. Owner ask, 10 Nov 2026 ~14:45 MYT, on Quotation Templates > Terms >
"Edit Default".

## Scout (file:line)

- Storage today: free `Text` columns `payment_terms` + `validity` on three tables,
  `sorento_crm_backend/app/models/projects.py:1209-1210` (per-quotation copy),
  `:1327-1328` (terms template), `:1400-1401` (issue snapshot, frozen at issue).
- Schemas: `app/schemas/projects.py:1972-1973`, `:2253-2254`, `:2278-2279`, `:2522-2523`
  (all `Optional[str]`, max 2000).
- Template service: `app/services/project_quotation_template_service.py:435-436, 480, 548-549`.
- Cover page reads the ISSUE copy: `app/services/quotation_cover_service.py:267-268`; labels at
  `:48-49`; sample at `:360-361`. Public sign link reads the issue too
  (`app/api/v1/public/quotation_sign.py:44`).
- NO payment-terms master exists in the CRM. `app/services/master_ingest_service.py:420-425`
  says so in as many words ("the payment-terms master it once waited for still does not exist");
  `customers` never had a terms column (`:472-474`); the only terms data is
  `suppliers.payment_terms_days` int (`app/models/procurement.py:66`). AC-AC-36 (Group H, new
  masters) in `documentation/plans/_archive/autocount/autocount-integration-acceptance-criteria.md:353`
  specified one and it was never built.
- How AutoCount masters reach the CRM: the shared service (ESB) PUSHES canonical records into
  `MasterIngestService` (`app/services/master_ingest_service.py:702` `ENTITY_SPECS`:
  categories, brands, item classes, UoM, warehouses, suppliers, customers, products, sales
  agents). The CRM-initiated pull (`app/services/autocount_pull_service.py:40`) covers only
  products, stock balances, DOs and GRNs via FoundryX snapshots.

## Design (proposed, see behaviour card on the PR)

1. New company-scoped master `payment_terms` (code = AutoCount `Terms.DisplayTerm`,
   description, term_days nullable, is_active, source_system/source_ref via the existing
   integration references). Only ingest creates rows; the CRM never writes AutoCount.
2. New ingest entity `payment_terms` in `ENTITY_SPECS` (pushed before customers). The push
   side is a foundryx-shared-service change (cross-repo, not in this lane's diff).
3. Template + quotation + issue: add `payment_term_id` (FK, nullable), `validity_value` (int),
   `validity_unit` (`day|week|month|year`). Keep the legacy `payment_terms` / `validity`
   text columns: they hold the PRINT text (snapshot at issue), and they hold the old
   unmatched value until someone picks.
4. Printing: payment terms prints the chosen term's description (else the legacy text);
   validity prints `"<n> <UNIT>S"` upper-case, e.g. `2 WEEKS`, `1 MONTH`.
5. Backfill (migration): exact, case/space-insensitive match of legacy text to a synced term
   code or description; validity text matching `^\s*(\d+)\s*(day|week|month|year)s?\s*$`.
   Everything else stays as visible legacy text.

## Decisions

- Q1 (crew): ESB ingest entity `payment_terms`, contract 2.14, pushed by foundryx-shared-service
  (lane SS-PAYMENT-TERMS). Contract posted on PR #2305.
- Q2 (owner, 10 Nov 15:10 MYT): a term prints its AutoCount Description, else its code.
- Q3 (owner): YES, a new quotation defaults its payment term from the project customer's
  AutoCount debtor terms (`Debtor.DisplayTerm`, back on the customer feed as `payment_terms_code`,
  stored on `customers.payment_terms_code`), when that code names an active synced term; the Terms
  template's term otherwise. Validity always from the template.
- Q4 (owner): `1 WEEK` / `2 WEEKS`, upper-case, 1..999.
- Q5 (crew): unmatched legacy text is kept and printed, shown as `Current: ...`.

## Build notes

- Picks: `quote_terms_service.resolve/apply` (`sorento_crm_backend/app/services/quote_terms_service.py`)
  is the one rule for template create/update, quotation create/update and the cover preview.
- Select routes: `GET /project-sales/config/quotation-templates/payment-terms` (projects.types.view)
  and `GET /project-sales/projects/{id}/quotation-documents/payment-terms` (the form's own gate).
- Migration `qts_0001_quote_terms_select`: table, three columns on both projects tables,
  validity backfill, `master_data.payment_terms.*` grants mirrored from item classes.
- FE: one `QuoteTermsFields` component (`project-sales/_shared/components`) in the template dialog
  and the quotation Terms tab; only changed picks are sent.

## Round 3 (10 Nov ~16:00, crew AutoCount probe + owner hand test)

- AutoCount `Terms` has two fields only: `DisplayTerm` (prints) and `Terms` (calculation rule).
  The master is `payment_terms.term_code` = DisplayTerm and `term_rule` = Terms; no description,
  no day count. The feed record is `code`, `rule`, `is_active` (contract 2.14).
- Q2 restated: what prints is the DisplayTerm. Matching (debtor default, legacy link) is exact
  on DisplayTerm, edge padding ignored, case kept.
- Owner: the picker shows one line per term, the DisplayTerm only.
- Owner: Master Data > Reference Data > Payment Terms, a read-only DataGrid (Term, Rule, Company,
  Status; search over term and rule; sortable). `GET /api/v1/master-data/payment-terms/`, gated
  `master_data.payment_terms.view`, `# ai: not-for-assistant`.
- Owner, 10 Nov ~16:10: "*"-prefixed DisplayTerms are never offered for a new pick (select,
  `resolve`, template default, legacy link). One already carried still prints; a "*" debtor
  default is handed on as text only (shown as "Current: ..."). The list page shows every row.
- SS-PAYMENT-TERMS: `customers.payment_terms_code` is VARCHAR(100), the same cap as the term.
