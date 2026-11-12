# PLAN: a combo part can also be its free item (COMBO-FREE-PART)

Status: Built, reviewer READY, cloud browser pass done; owner hand test next (behaviour card answers pending, built on the recommendations). Small fix track (no migration, no auth change).

## Journey

Owner, 9 Nov ~22:10, product detail > Combos > Accessories included: adding SRTWT6203-GM as a
free item fails because it is already a part of the combo. The 2026 dealer flyer
"SRTBF11829 + SRTMR8083-BL, 5 IN 1 BATHROOM FURNITURE" lists SRTWT6203-GM (Basin Cold Tap
Gunmetal) as a part AND prints it in the FREE box.

## Guards found today (rule A2 reading, CARD-pricetag-accessories-06nov.md)

| Where | file:line | What it does |
| --- | --- | --- |
| API / service | `sorento_crm_backend/app/services/accessory_service.py:838-842` | `set_combo_list` refuses each part with 422 "This product is already a part of this combo" |
| Seed import (loose) | `sorento_crm_backend/scripts/import_product_combos.py:477,485` | a free item code that is a part falls back to a library accessory by name |
| Seed import (strict) | `sorento_crm_backend/scripts/import_product_combos.py:592,642-649` | `_free_resolve` refuses parts; an existing part is noted "already a part" and dropped |
| Copy to products (#2284) | `sorento_crm_backend/app/services/product_combo_service.py:514` | drops only a free item that is the target itself; parts already copy |
| UI picker | `.../products/[id]/components/AccessoryListField.tsx:223` | hides only the host; parts are offered, the save then fails on the API |

## Behaviour (pending the crew-ask answers)

1. Any part may also be a free item, by explicit pick only (never auto-added).
2. It stays in the parts list and the tag's parts section, and also shows in the FREE box.
3. LP / SP never change because of a free item.
4. Seed import and copy-to-products carry it.

The host product still cannot be its own free item.

## Change

- `accessory_service.py` `set_combo_list`: refuses only the host.
- `scripts/import_product_combos.py`: loose mode links a part's code as the product; strict
  `_free_resolve` no longer refuses parts and the "already a part" skip is gone.
- Copy-to-products and the tag render needed no change; tests pin both.
- UI: no change. The picker (`AccessoryListField.tsx:223`) already offers parts and hides the host.

## Existing data

A reseed never overwrites a free list that exists (`_has_free_list`). A combo seeded before this
lane keeps what it got: a library card named by the code (loose) or no tap at all (strict). Fix
such a combo by hand in its Combos card (e.g. the SRTBF11829 flyer combo, if it was already seeded).

## Tests

- `tests/test_combo_free_part.py`: API accepts a part, refuses the host; the tag shows the part in
  `parts` and in `combo.accessories` with LP/SP unchanged; copy-to-products keeps it.
- `tests/test_combo_free_part_import.py`: loose reseed links the product; strict create and strict
  existing combo both link it.
- Updated: `test_accessories.py::test_p1_a_combo_host_cannot_be_its_free_item`,
  `test_import_product_combos_strict_round2.py::test_ac_15c_...loaded_as_that_product`.
