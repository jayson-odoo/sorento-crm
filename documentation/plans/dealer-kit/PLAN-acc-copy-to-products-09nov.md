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
