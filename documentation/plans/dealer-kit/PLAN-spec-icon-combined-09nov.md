# PLAN: price tag icon linked to a combination of spec values (SPEC-ICON-COMBINED, 9 Nov)

Status: Build (owner answered 9 Nov ~22:55; Q2 still open, building on rec (a)). Red-first tests next. Track: standard lane, size M (one additive migration, so not the small fix track).

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

## Owner rulings (9 Nov ~22:55, via crew)

- Q1 UNION: a condition-carrying icon never suppresses single-value icons. Every icon whose rule
  matches prints (S/150 prints both "S trap" and "S trap 150mm" when both are linked).
- Q2 order: building on rec (a), the slot of the value the icon is set on. Being re-explained to the
  owner; adjust if he picks (b) (the earlier of the specs involved).
- Q3 (b) N: the condition is an AND over N other spec values, not only one.
- Q4 (a): any condition value missing means the icon does not print and takes no space; every other
  icon prints as usual.
- Q5 (a) plus a visible reason: the Specifications tab shows the icon on its host row only when every
  condition value is held, with a small visible hint naming them, e.g. "shown because Trap = S trap".

## Rule (as ruled)

R1. On Values and words > Icons (`ValuesAndWordsTab.tsx:405-486`), each icon chip on a value gets an
    optional "Only with" list: N rows of (other spec, one of its values), all must hold. Set in a small
    popover on the chip with `SearchableSelect`s; no layout change, no Lavish mock.
R2. Storage: one new JSONB column `product_spec_registry.value_icon_conditions`
    `{value: {icon_id: [{spec_key, value}, ...]}}`, NOT NULL default `{}` (additive migration). An icon
    with no entry is today's single-value link, byte for byte (5 Nov rulings untouched).
R3. Wire: `FeatureIconOut` gains `conditions: [{spec_key, value}]` (default `[]`), emitted by
    `feature_icon_rules` at the host value's slot. `featureIconsFor` prints an icon only when the
    host value matches AND every condition's raw value matches (same raw text rule, numeric through
    `numeric_value_text`). Union: no suppression. Dedupe by asset id stays (first matching slot wins).
R4. Validation (`clean_value_icons` / registry PATCH, same `dealer_kit.library.manage` gate):
    condition key must be an active registry key other than the host key, unique within the icon;
    value must be one of `spec_value_keys(partner)` for enum/boolean, a number for numeric (stored
    normalised); at most 5 conditions per icon; conditions only for (value, icon) pairs present in
    `value_icons`; dropped with their icon (remove, prune, value delete). Another company's hidden icon
    keeps its stored conditions (same carry-forward as its id).
R5. Registry GET returns `value_icon_conditions` filtered to the visible (value, icon) pairs.
R6. Specifications tab: `iconsFor(row, rows)` matches against the product's whole spec rows; a
    condition-carrying icon shows on its host row only, with a muted hint "shown because <Label> =
    <display value>[, ...]" built from the product's own rows.

## Test list (red first)

Backend (pytest, `tests/test_feature_icons_combined.py`):
- B1 `feature_icon_rules` emits `conditions` for a conditioned icon and `[]` for a plain one, at the
  host value's slot (order unchanged vs today for plain icons).
- B2 PATCH saves conditions; GET returns them; numeric partner "150.0" stored as "150".
- B3 refused: partner = host key, unknown/inactive key, enum value not in vocabulary, non-number for
  numeric, duplicate partner key, more than 5, condition for an icon not on that value.
- B4 removing the icon from the value, or deleting/suppressing the value, drops its conditions.
- B5 PATCH without `dealer_kit.library.manage` is 403.
- B6 single-value links unchanged: a PATCH with only `value_icons` leaves rules exactly as before.
Frontend (vitest):
- F1 `featureIconsFor`: S/150 prints both "S trap" and "S trap 150mm" (union); S/200 only "S trap";
  P/150 not "S trap 150mm"; S with no length not the combined one; 3-spec AND needs all three.
- F2 `variantFeatureIcons` with a conditioned icon matches per member, never across members.
- F3 Specifications tab: host row shows the icon + hint "shown because Trap = S trap" only when the
  partner row is held; partner row itself shows nothing extra.
- F4 Values and words: chip "Only with" popover adds/removes a condition; draft PATCH carries it.
Kill tests: drop the condition check in `featureIconsFor` (F1 red); store numeric partner unnormalised
(B2 red); show the icon on the partner row too (F3 red).

## Examples (codes from committed fixtures sourced from the prod copy; the cloud sandbox cannot read
## sorento_prod_1104, so which icons dev holds today is assumed from crew's workaround)

Setup after the change: "S trap" on trap_type = s_trap, "P trap" on p_trap, "S trap 150mm" on
trap_length = 150 with Only with trap_type = s_trap. Today (workaround): "S trap 150mm" on
trap_length = 150, nothing on s_trap.

| Product | Trap / length | Today prints | After |
| --- | --- | --- | --- |
| SRTWC286-SH-150 | S, 150 | S trap 150mm | S trap, S trap 150mm (union, Q1) |
| SRTWC286-SH-200 | S, 200 | no trap icon | S trap |
| SRTWCX8840-S-RL | S, 250 | no trap icon | S trap |
| SRTWC286-SH-NEW-P | P, 180 | P trap (if set) | P trap |
| SRTWCY8608 (cistern) | S, no length | no trap icon | S trap; combined not printed, no space |

A P trap held at 150 mm would print "S trap 150mm" today; after, it prints only P trap.

## Questions (crew-ask on #2291, answered above)

1. Combined icon matches: suppress the single icons of BOTH its values (rec), or print all.
2. Order: at the slot of the value it is set on (rec), or at the earlier of the two specs.
3. Two specs only (rec), or N.
4. Only one value present: no combined icon, no space, singles print as usual (rec).
5. Specifications tab: show the combined icon on its host row only when the partner value is also
   held (rec), or on both rows, or not at all.
