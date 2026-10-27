# PLAN: access-sheet follow-up fixes (ACCESS-SHEET-FIXES)

Status: Review. Track: M (cloud lane, follow-up to #1893; no migration, no auth change; diff over 300 lines).
Parent: `PLAN-bulk-access-preview-27oct.md`. UAC: `access-sheet-fixes-27oct-acceptance-criteria.md`.

## Owner feedback (27 Oct, after a real prod import)
1. A dealer whose rows tag only SRT shows Mocha accounts ticked in the preview.
2. The customer search in the import picker spins forever.
3. Internal Users: the Customers column and Customer filter must show customers of every company the
   viewer holds, not just the current company.

## Owner rulings (27 Oct 15:2x)
- Older Mocha `source='access_sheet'` links on Sorento-only contacts: NOT removed.
- Brands: any contact holding MCH keeps every brand; the import never narrows it; a script restores the
  contacts already narrowed.
- New rule: every Internal Users column sorts, server-side.

## Fixes
1. BE `contact_access_sheet_service._build_blocks`: an exact account is proposed only when its company
   is one the dealer's rows tag. Other-company exacts stay listed, unticked.
2. FE `AccessSheetImportPage.ExtraCustomers`: `onLabels` in a ref, `fetchOptions` stable via
   `useCallback` on `picker.fetchOptions`, so `SearchableMultiSelect` searches once per query.
3. BE `customer_codes_by_contact` + the `customer_id` filter read every granted company (`grants_scope`);
   a code outside the active company reads `300-1001 (MCH)`. FE `ContactAccessFilters` searches with
   `{companyScope: 'grants'}` (label formatter `customerService.searchCustomersSelect`) and reads a
   restored id back through `/customers/select?customer_id=` (the single-customer GET is company-scoped).
4. BE `contact_setup_engine` brands step: a contact holding (or given) a company in
   `EVERY_BRAND_COMPANIES` (MCH) keeps or goes back to every brand (NULL); holds-more skips brands for it.
   `scripts/fix_access_sheet_mocha_brands.py` (dry run default, `--apply` one transaction + audit rows).
5. BE `ContactService._order_by`: every grid column id sorts (empty last both ways, name/id tie-break);
   FE `ContactsList` headers all sortable (`DataGridColumnHeader`, `manualSorting`).
