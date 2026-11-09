# PLAN: a combo part can also be its free item (COMBO-FREE-PART)

Status: Plan, behaviour card asked (crew-ask on the PR). Small fix track (no migration, no auth change).

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
