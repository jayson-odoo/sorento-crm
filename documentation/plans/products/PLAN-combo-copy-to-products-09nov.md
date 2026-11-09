# PLAN: Copy a product combo to other products (COMBO-COPY-TO-PRODUCTS)

Status: Plan (behaviour card posted 9 Nov as `crew-ask` on PR #2284, waiting on owner answers;
code waits for the answers and for #2280 to merge). Track: TBD after the answers (likely small
fix track + security review, no migration).

## Journey

Owner, 9 Nov 2026 (~13:55 and ~16:10): many bathtubs carry the same combo. Today a combo is built
inside one product's page. The owner wants the reverse: on a product's Combos card, pick one combo
and copy it to many other products in one go. #2280's "Copy to other products" copies only the
Accessories list; the owner wants the whole combo.

## Facts (origin/main 4b702db3)

Where a combo's pieces live:

| Piece | Stored at |
| --- | --- |
| Combo row (host, name, sort) | `product_combos`, `sorento_crm_backend/app/models/product_combo.py:44-101`; unique (host, name) `:99`, case-insensitive 409 `COMBO_NAME_TAKEN` in `app/services/product_combo_service.py:231-245` |
| Description (rich text, cleaned) | `product_combos.description` `product_combo.py:80`, cleaned by `tag_description.clean_description` (`product_combo_service.py:224`) |
| List / sell price | `product_combos.list_price`, `sell_price` `product_combo.py:82-83`; blank = the tag prints no price (`:78-79`) |
| Legacy free-items text | `product_combos.free_items` `product_combo.py:81` |
| Box style | `product_combos.accessory_box_preset_id` `product_combo.py:73-78` |
| Picture | `product_combos.image_attachment_id` `product_combo.py:68-70`; the attachment is ALSO linked into the host's gallery via `product_attachments` (`product_combo_service.py:368-381`) |
| Parts: fixed vs choice | `product_combo_parts`, `product_combo.py:104-153`: `choice_group` NULL = fixed, same label = options of one group; per part `sell_price`, `topup_amount`, `is_upgrade` (`:134-140`) |
| Free items list (+ overrides, picture pick) | `product_combo_accessories`, `app/models/accessory.py:160-198` (`name/spec/remark_override`, `image_id`) |
| Price tag template links | `dealer_kit.combo_tag_template`, `app/models/dealer_kit.py:866-904` (with `default_list` / `default_selling`); written under `dealer_kit.tag_templates.manage` (`app/api/v1/dealer_kit/tag_data.py:49,240-262`), NOT the product edit permission |

- The host is never one of its own parts: `add_part` refuses `COMBO_PART_IS_HOST`
  (`product_combo_service.py:505-511`). So "the source product becomes the target" needs no part
  rewrite: the combo simply gets the target as its host.
- Combo writes use `master_data.products.edit` (`app/api/v1/master_data/product_combos.py:77-85`).
- Button slot: the combo block header, next to Delete
  (`sorento_crm_frontend/app/(protected)/master-data-management/products/[id]/components/ProductCombosSection.tsx:521-540`).
- Flyer seed data (#2282, `scripts/data/combo_seed_flyer_2026.json`, 243 combos): all 39 bathtub
  combos are named after their host's own code (107 of 243 overall), carry the tub's own size line
  in the description, have no fixed parts, 4 upgrade options (mixer tap SRTWT51012-BL/-GM/-GY/-FRG,
  top-up RM150), and the same 3 free items. Prices differ per tub.
- Reuse: #2280's picker dialog (`CopyAccessoriesDialog.tsx`), `AccessoryService` copy
  (all-or-nothing, row locks, 500 cap) and the import script's create/fill path
  (`scripts/import_product_combos.py`, through `ProductComboService`).

## Behaviour card

Posted on PR #2284 as `crew-ask` (9 Nov). The examples come from the committed flyer seed, not the
dev database: this cloud sandbox has no dev data.

Example: SRTBT1860-16's combo "SRTBT1860-16" (LP 7588 / SP 6599, description "Free Standing
Bathtub / With Drainer & Overflow / Material : Acrylic / L1600xW780xH800mm", 4 mixer-tap upgrades
+RM150, free items pump + soap set + mixer tap, picture of the 1860 tub) copied to SRTBT1835
(flyer LP 6920 / SP 6299, L1600xW750xH580mm) and SRTBT1846 (flyer LP 7920 / SP 6999).

Q1 Name and host. Q2 Prices. Q3 Description and picture. Q4 Same name already on a target.
Q5 Tag template links. Button placement stated as an assumption. Full text on the PR comment;
answers are recorded below once given.

## Owner answers

(pending)
