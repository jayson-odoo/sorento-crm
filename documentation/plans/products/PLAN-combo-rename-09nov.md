# PLAN - Rename a product combo after creating it

Status: merge-ready on PR #2281, awaiting owner hand test (Track: small fix - no migration, no auth/RBAC change, expected diff under 300 lines). Plan created 2026-11-09.

crew-lane: COMBO-RENAME. Base: main 609b53bb.

## Ruling

> "how can I edit the combo name after creating?"
>
> - Owner, 9 Nov 2026 ~14:00 MYT, on product detail > Combos card

## Measured facts

- The combo title is plain text, Delete beside it, no rename
  (`sorento_crm_frontend/app/(protected)/master-data-management/products/[id]/components/ProductCombosSection.tsx:523-541`).
- The backend already renames: `PATCH /api/v1/master-data/product-combos/{combo_id}`
  (`sorento_crm_backend/app/api/v1/master_data/product_combos.py:77-85`, `master_data.products.edit`),
  `ProductComboUpdate.name` (`app/schemas/product_combo.py`), applied in
  `app/services/product_combo_service.py:265-284` (trim, empty -> 422, case-insensitive unique per host -> 409
  `COMBO_NAME_TAKEN`).
- FE type and client already accept `name` (`types/productCombo.types.ts`, `services/productComboService.ts`).
- Gap: `product_combos.name` is VARCHAR(100) (`app/models/product_combo.py:62`) with no schema or UI cap, so a long
  name is a DB error rather than a 422.
- Price tags read the combo name live by `combo_id`: no tag change.

## Build

1. Backend: `max_length=100` on `ProductComboCreate.name` and `ProductComboUpdate.name`.
2. Frontend: a pencil next to the combo title (edit permission only, same `canEdit` gate). Inline edit in place
   (pattern: Family code edit, `ProductVariantsTab.tsx` Pencil -> Input + Save/Cancel): Enter saves, Escape cancels.
   409 reads "Another combo on this product already has this name"; empty reads as a field error; `maxLength=100`
   on the rename input and on the Add combo modal name input.

## Tests (red first)

- Backend (`tests/test_product_combos.py`): 101-char name -> 422 on create and on update; 100 chars ok; rename
  trims; empty -> 422; case-insensitive taken -> 409; view-only -> 403.
- Frontend (vitest): pencil hidden without edit; rename saves via Enter; Escape cancels without a write; 409 message;
  empty name field error with no write; maxLength 100 on both inputs.

## UAC

See `combo-rename-acceptance-criteria.md`.

## Assistant coverage (DoD 6 to 8)

- 6: n/a, no new list screen.
- 7: no `ActionDef`. No combo write has one today (`app/services/assistant_registry/` has no combo entries: prices,
  description, parts and delete are all UI-only), and rename is one more field on the same PATCH. Trigger: when combo
  editing gets assistant actions, rename joins them.
- 8: n/a for the same reason (no combo assistant feature to evaluate).
