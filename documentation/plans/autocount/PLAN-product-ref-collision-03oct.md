# PLAN: product ref collision (ItemKey vs ItemCode refs)

Status: BUILDING, code-first redesign per owner ruling 3 Oct (L steps minus migration). Track: L pipeline (external ingest), no migration expected.

## Problem
Document lines link products under `BOOK:<ItemAutoKey>` (shared-service `presets.py:250/410/480`);
the product feed sends `BOOK:<ItemCode>` (`presets.py:805`). For numeric item codes the two collide.
`MasterIngestService._apply_scoped` trusts a ref hit before the code (`master_ingest_service.py:1213-1229`)
and `_update` writes every sent column including `product_code` (`:1635-1657`). Result on PROD 3 Oct:
push of Mocha ItemCode 2001/2002/2003 tries to rename MKT4524SS-DIY / MKT4524SS-GM-DIY /
MKT4528ASS-DIY and fails on `uq_products_company_product_code`. When no product owns the code yet
the same path renames the wrong product silently.

Line side: `MasterRefResolver._resolve_master` returns a ref hit without checking the sent code
(`master_ref_resolver.py:168-169`).

## Design (owner ruling 3 Oct: code-first everywhere)
"When we match product, it is by product code, we don't really care about the source ref."
1. Product feed (`master_ingest_service._apply_scoped`): products skip the ref lookup; match by
   company + normalised code first (existing adopt / code-wins / create paths). Link the pushed ref
   only when it is free; when another product holds it, warn `ref_mismatch` and leave it.
2. Line ladder (`master_ref_resolver._resolve_master`, Product only): when a code is sent, the code
   decides; no code owner -> existing unknown-product verdict, never the ref. Ref used only when no
   code is sent. Never link a ref already held by another product.
3. Billing (`finance/billing_document_ingest_service._product`) and the document snapshot preload
   (`document_ingest_service` ~:713): code first, same rule.
4. DO/GRN (`autocount_doc_ingest_service` :773) already code-only, unchanged.
5. No migration, no backfill, no name matching.

Open (one owner question): AutoCount item renamed (same ItemKey, new ItemCode) -> code-first creates
a new product; old one kept or flagged? Recommendation: keep it untouched, the line `ref_mismatch`
warning is the flag.

## Files
- `sorento_crm_backend/app/services/master_ingest_service.py`
- `sorento_crm_backend/app/services/master_ref_resolver.py`
- `sorento_crm_backend/app/services/finance/billing_document_ingest_service.py`
- `sorento_crm_backend/app/services/document_ingest_service.py`
- tests: `tests/test_product_ref_collision.py`

## Pipeline
tester (red, from UAC) -> `test(red):` commit + red-proof -> coder -> kill-proof -> reviewer +
security-reviewer (external ingest) -> CI. No UI, no browser pass, no hand test unless owner asks.
