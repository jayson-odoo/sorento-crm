# PLAN: product ref collision (ItemKey vs ItemCode refs)

Status: BUILDING (card approved by crew 3 Oct: Q1a, Q2 yes, Q3 keep, Q4 warn, Q5 L steps minus migration). Track: L pipeline (external ingest), no migration expected.

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

## Design (pending owner answers, recommended options)
1. Products feed: a ref hit counts only when the hit row's normalized `product_code` equals the
   payload code. Otherwise behave as a ref miss: code adopt (code-wins branch, `:1255-1288`) or
   create; never write the feed ref onto a row when another row already holds it; warning
   `ref_mismatch`.
2. Line resolver, Product model only: ref hit whose code differs from the sent code, and another
   product owns the sent code, resolves to the code owner with `ref_mismatch`. Ref hit with an
   unowned sent code keeps the ref (AutoCount item rename) and warns.
3. No data backfill: existing ItemKey refs stay (they are correct for lines).
4. No name matching.

## Files
- `sorento_crm_backend/app/services/master_ingest_service.py` (`_apply_scoped`, `_link` on create/adopt)
- `sorento_crm_backend/app/services/master_ref_resolver.py` (`_resolve_master`)
- tests: new `tests/test_product_ref_collision.py`

## Pipeline
tester (red, from UAC) -> `test(red):` commit + red-proof -> coder -> kill-proof -> reviewer +
security-reviewer (external ingest) -> CI. No UI, no browser pass, no hand test unless owner asks.
