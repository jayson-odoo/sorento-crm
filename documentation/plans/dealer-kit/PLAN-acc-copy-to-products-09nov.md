# PLAN: Copy a product's accessories list to other products (ACC-COPY-TO-PRODUCTS)

Status: Plan - behaviour card asked of the owner (crew-ask on the PR), no code yet. Track: small fix track expected (no migration, existing permission).

## Journey

Owner, 9 Nov: many bathtubs carry the same accessories (pressure pump, soap and bath bomb set,
freestanding mixer tap). Today each list is built one product at a time. Owner picked: a "Copy to
other products" button on a product's Accessories included list, and they pick the targets by hand.

## Facts (origin/main 609b53bb)

- Lists: `product_accessories` (sorento_crm_backend/app/models/accessory.py:116), combos
  `product_combo_accessories` (:160). Unique per (owner, accessory) and (owner, item product).
- PUT replaces the whole list: `AccessoryService.set_product_list` (app/services/accessory_service.py:705),
  max 100 entries (app/schemas/accessory.py:124), write gate `master_data.products.edit` signed-in only
  (app/api/v1/master_data/accessories.py:57).
- UI: `AccessoryListField.tsx` shared by product and combo sections.

Behaviour card: see the `crew-ask` comment on the PR; answers are recorded here once given.

## Behaviour card (asked 9 Nov, answers pending)

1. **Button.** "Copy to other products" in the header of the product's "Accessories included" card
   (ProductAccessoriesSection.tsx). Shown only to `master_data.products.edit` holders and only when
   the saved list has at least one entry. Not on combos' Free items (Q4).
2. **Picker.** A dialog with the system DataGrid of products: server-side search by code/name,
   Category / Brand multi-select filters (the same hooks ProductsList uses:
   `useProductCategorySelectQuery`, `useBrandSelectQuery`), checkbox column from
   `buildSelectColumn` (shift-click range, drag), "Select all N" banner from
   `DataGridListToolbar`. Active, non-discontinued by default. The source product is not offered.
   Grid-in-dialog already exists (ConvertToPackingListDialog.tsx), so no mock.
3. **Mode.** Q2.
4. **What copies.** Q3.
5. **Confirm step.** "Copy 3 entries to 12 products. 4 already have a list: their entries stay,
   the missing ones are added at the end." Then one call.
6. **Server.** `POST /api/v1/products/{id}/accessories/copy` `{target_product_ids: [...]}`
   (max 500 targets). Edit permission; every target resolved in the caller's company scope (a
   missing or out-of-scope id = 404 for the whole call); one transaction, all or nothing; a target
   that would pass 100 entries refuses the call naming it. The source itself is ignored if picked.
   Audit: the existing row listeners on `product_accessories` (`__audit_parent__ = product_id`)
   write one trail per target product.
