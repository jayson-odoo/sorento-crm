# PLAN: access-sheet follow-up fixes (ACCESS-SHEET-FIXES)

Status: Build. Track: M (cloud lane, follow-up to #1893; no migration, no auth change).
Parent: `PLAN-bulk-access-preview-27oct.md`. UAC: `access-sheet-fixes-27oct-acceptance-criteria.md`.

## Owner feedback (27 Oct, after a real prod import)
1. A dealer whose rows tag only SRT shows Mocha accounts ticked in the preview.
2. The customer search in the import picker spins forever.
3. Internal Users: the Customers column and Customer filter must show customers of every company the
   viewer holds, not just the current company.

## Fixes
1. BE `contact_access_sheet_service.py` exact-account match: propose only accounts whose company is a
   company the dealer's rows tag. Other-company exact matches are still listed, unticked.
2. FE `AccessSheetImportPage.tsx` picker: `onLabels` kept in a ref, `fetchOptions` stable via
   `useCallback` on `[picker.fetchOptions]`, so `SearchableMultiSelect` searches once per query.
3. BE Internal Users customer codes read + `customer_id` filter under `grants_scope`; FE
   `ContactAccessFilters` searches with `{companyScope: 'grants'}` and labels each option with its company.

## Held (pending owner ruling)
- Brands narrowed to Sorento on contacts that hold MCH.
- Removing older Mocha `source='access_sheet'` links on Sorento-only contacts.
