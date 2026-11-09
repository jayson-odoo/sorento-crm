# PLAN: price tag icon linked to a combination of spec values (SPEC-ICON-COMBINED, 9 Nov)

Status: Plan, behaviour card filed (crew-ask on PR #2291), waiting on the owner. No code before the
answers. Track: standard lane, size M (one additive migration, so not the small fix track).

Owner, 9 Nov: an icon "S trap 150mm" means trap type = S AND outlet length = 150 mm. Today an icon
hangs on ONE spec value (ruling 5 Nov). Owner OK'd a proper rule: an icon can be linked to a
COMBINATION of spec values (two specs, both must match).

## What exists today (measured)

- Storage: `product_spec_registry.value_icons` = `{value: [icon asset id, ...]}`, plus
  `icon_order` for the key's slot (`sorento_crm_backend/app/models/product_spec.py:162-168`).
- Resolver: `feature_icon_rules` flattens to `[{id, name, spec_key, values: [value]}]` in the one
  sequence (keys by icon_order, values in key order, icons in admin order)
  (`sorento_crm_backend/app/services/dealer_kit/asset_service.py:544-603`); saves validated by
  `clean_value_icons` (`asset_service.py:666`).
- Matcher used by canvas, request preview and print: `featureIconsFor`
  (`sorento_crm_frontend/lib/dealer-kit/feature-icons.ts:35`), `variantFeatureIcons` (`:61`),
  `iconsForSpecValue` (`:83`) for the product Specifications tab
  (`.../products/hooks/useSpecValueIcons.ts:27`, `.../products/[id]/components/SpecValueIcons.tsx:21`).
- Where icons are set: Master Data > Product Specifications > key > Values and words, Icons column
  (`.../product-specifications/components/record/ValuesAndWordsTab.tsx:405-486`), picker
  `AssetPickerDialog` (`app/(protected)/dealer-kit/tag-templates/components/AssetPickerDialog.tsx`),
  gated by `dealer_kit.library.manage`.
- The specs: `trap_type` enum `s_trap` / `p_trap`; `trap_length` numeric mm, "independent of
  trap_type" (`app/services/product_spec_registry.py:1161-1186`).

## Proposed rule

R1. On the Icons cell of a value (e.g. Trap outlet length = 150), each icon chip gets an optional
    "Only with" condition: one other spec + one of its values (Trap = S trap). Set with two
    `SearchableSelect`s (`components/common/SearchableSelect`) in a small popover on the chip; no
    new screen, no layout change, so no Lavish mock.
R2. Stored beside `value_icons` in one new JSONB column `value_icon_conditions`
    `{value: {icon_id: {spec_key, value}}}` (additive migration). An icon without a condition is a
    single-value link exactly as today (5 Nov rulings untouched).
R3. The resolver sends the condition on the icon (`with: {spec_key, values}`); `featureIconsFor`
    prints it only when the product holds BOTH raw values.
R4. When a combined icon prints, the single-value icons of those two values do not (Q1).
R5. Only one of the two values present: the combined icon is not printed and takes no space; that
    value's own single icons print as today (Q4).
R6. The product Specifications tab shows the combined icon on the row it is set on, only when the
    product also holds the partner value, so the tab never disagrees with the tag (Q5).

## Examples (codes from committed fixtures sourced from the prod copy; the cloud sandbox cannot read
## sorento_prod_1104, so which icons dev holds today is assumed from crew's workaround)

Setup after the change: "S trap" on trap_type = s_trap, "P trap" on p_trap, "S trap 150mm" on
trap_length = 150 with Only with trap_type = s_trap. Today (workaround): "S trap 150mm" on
trap_length = 150, nothing on s_trap.

| Product | Trap / length | Today prints | After |
| --- | --- | --- | --- |
| SRTWC286-SH-150 | S, 150 | S trap 150mm | S trap 150mm (S trap single suppressed) |
| SRTWC286-SH-200 | S, 200 | no trap icon | S trap |
| SRTWCX8840-S-RL | S, 250 | no trap icon | S trap |
| SRTWC286-SH-NEW-P | P, 180 | P trap (if set) | P trap |
| SRTWCY8608 (cistern) | S, no length | no trap icon | S trap; combined not printed, no space |

A P trap held at 150 mm would print "S trap 150mm" today; after, it prints only P trap.

## Questions (crew-ask on #2291)

1. Combined icon matches: suppress the single icons of BOTH its values (rec), or print all.
2. Order: at the slot of the value it is set on (rec), or at the earlier of the two specs.
3. Two specs only (rec), or N.
4. Only one value present: no combined icon, no space, singles print as usual (rec).
5. Specifications tab: show the combined icon on its host row only when the partner value is also
   held (rec), or on both rows, or not at all.
