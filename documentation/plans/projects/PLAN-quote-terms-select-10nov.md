# PLAN: Quote payment terms from an AutoCount-synced select, validity as number + interval

Status: Plan (behaviour card posted, awaiting owner answers). Track: L (new master table + migration +
ESB ingest entity; the push side lives in foundryx-shared-service).

Lane: QUOTE-TERMS-SELECT. Owner ask, 10 Nov 2026 ~14:45 MYT, on Quotation Templates > Terms >
"Edit Default".

## Scout (file:line)

- Storage today: free `Text` columns `payment_terms` + `validity` on three tables,
  `sorento_crm_backend/app/models/projects.py:1209-1210` (terms template),
  `:1327-1328` (per-quotation copy), `:1400-1401` (issue snapshot, frozen at issue).
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

## Open questions

Posted as `crew-ask` on the PR.
