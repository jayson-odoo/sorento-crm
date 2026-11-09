# PLAN: price tag upgrade items on combos + one tag per product family with variant icons

Status: PR+CI (built; reviewer fix round 1 done, security READY, cloud browser pass a-f PASS, print not reachable in the sandbox; owner hand test pending). Track: full (migration + payload + designer + request line).

Lane: PRICETAG-UPGRADE-VARIANTS. Behaviour card: `CARD-pricetag-upgrade-variants-09nov.md` (U1-U9, F1-F8 + owner rulings
at the top win). UAC: `pricetag-upgrade-variants-acceptance-criteria.md`. Mock: `pricetag-upgrade-variants-mock.html` (v3).

Paths: BE = `sorento_crm_backend/`, FE = `sorento_crm_frontend/`. Existing tags must print byte-for-byte the same: every new
prop is optional and absent means today's behaviour.

## Slices (one lane, one PR)

- S1 Upgrades box (FE lib + renderers + designer), BE slot rows gain `topup_amount`, print media for card icons.
- S2 Free "Upgrade top-up" / "SP with upgrade" text slots.
- S3 Family tag: payload `variants`, feature icons "All variants", request line chooser + migration, Q5 warning.
- S4 Numeric spec values carry icons (Product Specifications screen + `spec_value_keys`), raw number normalised.

## S1 Upgrades box

FE `lib/dealer-kit/tag-template-types.ts`:
- `AccessoriesLayerProps.list?: 'free' | 'upgrades'` (absent = 'free').
- `CardField` += `'topup' | 'price_with_upgrade'`.
- `CardElement.kind` += `'feature_icons'` with `iconSize_mm?`, `gap_mm?` (defaults 4.6 / 0.8), `align` reused.
- `CardElement.prefix?: string`: printed before a field value when the value is non-empty ("TOPUP ").
- `TagAccessory.kind` += `'upgrade'`; `TagAccessory` += `topup_amount?: number | null`,
  `price_with_upgrade?: number | null`, `specs?: TagSpecValue[]`.
- `TagPartData.topup_amount?: number | null` (upgrade slot rows).

FE `lib/dealer-kit/accessory-box.ts`:
- `upgradesOf(data)`: `comboOf(data)` (line.combo or product.combo); its `upgrades` NOT `picked`, in combo order; each mapped
  to a TagAccessory `{kind:'upgrade', id: product_id, code, name: description, list_price, image, images, specs,
  topup_amount, price_with_upgrade}` where list_price / image / specs come from the slot row with the same product_id in
  `slots.upgrades` (line.slots or product.slots; image = first image, primary first), and
  `price_with_upgrade = priceBadgeInput(data).offerPrice + topup_amount` (null when either is null). No combo -> [].
- `accessoriesOf(data, layer)`: when `layer.props.list === 'upgrades'` return `upgradesOf(data)` (ignores subjectSlot /
  subjectPart). Every caller (canvas `layerDisplay`, print `TagSheetRenderer`, drop toast `accessory-drops.ts`) gets it free.
  `priceBadgeInput` lives in product-block.ts which imports accessory-box: put `upgradesOf` in product-block.ts (or a new
  `upgrade-items.ts`) and branch in accessoriesOf without an import cycle; one function either way.

FE `lib/dealer-kit/accessory-card.ts`:
- `cardFieldValue`: `topup` -> `formatTagPrice(topup_amount)` (null when null); `price_with_upgrade` likewise.
- `cardElementsFor(item, card, featureIcons?)`: a text element with a field gets `prefix + value`; a `feature_icons`
  element resolves `icons = featureIconsFor(item.specs, featureIcons)` and is DROPPED (closes up, V7) when empty.
  `cardElementsForDesign` draws feature_icons with the sample/own icons, never dropped.
- `defaultUpgradeCard()`: card 71 x 21.5 mm: picture (1,1.5,14,19), text Top-up prefix "TOPUP " bold 10.8pt #B91C1C at
  (17,1), code bold (17,5.6), name (17,9.2), price LP (17,12.2), feature_icons (17,15.2,50,5). `price_with_upgrade` is NOT
  on it (Q2 a). `accessoryDesignSamples` gets an upgrade sample for the designer when list = upgrades.
- `newCardElement('feature_icons')` and a Field menu entry for Top-up and SP with upgrade (prefix defaults "TOPUP " and
  "SP with upgrade ").

Renderers (one rule each, same input): `KonvaTagLayer.tsx` `CardElementNode` and `TagSheetRenderer.tsx` card element draw
`feature_icons` as a packed row with `featureIconRow` inside the element rect, url from the asset map the layer already uses
for feature icons. Both get the FeatureIcon rules the same way the feature_icons layer gets them.

Designer (`InspectorPanel.tsx` AccessoriesInspector): "List" segmented Free items | Upgrades; switching to Upgrades on a box
with no card sets `card = defaultUpgradeCard()` and, if headerText is the default, headerText "UPGRADE" (one undo step);
a note "Source: this combo's upgrade parts (product page > Combos)". Card element inspector: "Shows" lists Top-up and SP
with upgrade, "Text before the figure" edits `prefix`. Card mode toolbar gains "Feature icons". Top-up is an ordinary
element: drag, resize, X/Y, delete (existing card editing).

BE:
- `tag_data_service._line_slots` and `_preview_slots` upgrade rows gain `topup_amount` (the part's top-up).
- `asset_service.doc_has_feature_icons`: also true when an accessories layer's `card.elements` has kind `feature_icons`,
  so `design_media` sends the icon rules + signed asset urls for print and the request preview.
- Doc schema: if accessories props / card elements are validated anywhere (grep `price_tag.py` and the doc validators),
  accept the new keys.
- Fit: `template_needs` (BE) and `comboShape` / needs (FE) do NOT count an Upgrades box (it carries no subjectSlot).

## S2 Free top-up layer

- Slot bindings `upgrade_topup` ("Upgrade top-up") and `sell_price_with_upgrade` ("SP with upgrade"), group Combo, FE
  `SlotBinding` + `SLOT_BINDING_OPTIONS` + BE `SLOT_BINDINGS`.
- `resolveSlotText`: when the layer's subjectSlot is `{kind:'upgrade', index}`: the row `partAtSlot(slots, slot)`; if the row
  is `chosen` (picked) or has no `topup_amount` -> ''. `upgrade_topup` -> prefix + `formatTagPrice(topup, showCurrency)`;
  `sell_price_with_upgrade` -> prefix + price of (offerPrice of the tag + topup). Not on an upgrade position -> ''.
  `TextLayerProps.prefix?: string` (used only by these two slots), set to "TOPUP " / "SP with upgrade " when the slot is
  chosen in the inspector. Same `formatTagPrice` as the card, so both print the same words.
- A layer on Upgrade N keeps today's fit rule (needs N upgrades); the inspector shows the warning from mock state H.

## S3 Family tag

Migration `ptag_0020_variant_excl` (additive, down_revision = main's head at build start):
`price_tag_request_lines.excluded_variant_ids JSONB NOT NULL DEFAULT '[]'`.

BE:
- `variant_service.variant_members(db, product_id)`: every product under `product_id` in the `variant_of_id` tree (any
  depth, cycle-safe, same company scope), ordered by product_code, each `{product_id, code, name, list_price,
  is_discontinued, is_active}`. Excludes the product itself.
- Tag payload: line data and product (designer preview) data gain `variants: [{product_id, code, specs}]` = members that are
  active, NOT discontinued, and (lines only) not in `excluded_variant_ids`. `specs` via the same `product_specs` builder
  (with `raw`). Pinned rows freeze it with the rest; a row pinned before reads absent (= none).
- Line API: create / update / revise accept `excluded_variant_ids: list[str]` (default []): de-duplicated; an id that is not a
  member of the line product's tree, or the line product itself -> 422 `NOT_A_VARIANT`. Response returns it. Revision
  carry-over copies it.
- Chooser lookup: `GET /api/v1/dealer-kit/price-tag-requests/variant-members/{product_id}` (staff, dealer kit request view
  permission) AND the portal equivalent next to the portal's other product lookups, both returning
  `{members: [{product_id, code, name, list_price, is_discontinued}], own_list_price}` (live and discontinued, inactive
  left out). Scoped like the other product lookups.

FE:
- `SubjectSlot` += `{kind:'variants'}`; BE `SubjectSlotDoc` += `SlotVariants`. Offered only on a feature_icons layer, label
  "All variants". `subjectOf` treats it as the main subject for any other use; `comboPositions` / needs ignore it.
- `feature-icons.ts`: `variantFeatureIcons(memberSpecs: TagSpecValue[][], icons)`: per member `featureIconsFor`, union of ids,
  returned in the input `icons` order, each once. The feature_icons layer on "All variants" = `variantFeatureIcons([own
  specs, ...data.variants.map(v=>v.specs)], icons)` in canvas, request preview and print (one helper both renderers call).
- Request line (`components/dealer-kit/PriceTagLinesTable.tsx` + portal service): "Variants on this tag"
  SearchableMultiSelect, shown when the line product has members, all ticked by default, the line's own product listed and
  locked on, discontinued shown with a grey "Discontinued" hint and not counted. Stores the UNTICKED ids in
  `excluded_variant_ids`. Label "N of M ticked".
- Q5 warning under the line's price: when the list prices of the line product + ticked live members differ:
  "Variants price differently: RM x to RM y" (min, max, `formatTagPrice`). Warning only.

## S4 Numeric spec values with icons

- BE `asset_service.spec_value_keys(row)`: a `numeric` key returns the distinct values products hold for it
  (`product_specifications.values ->> key`, normalised: 150, 150.0 and "150" -> "150"), sorted numerically. The value-icons
  PUT accepts them.
- `tag_data_service._spec_raw_text`: a number that is a whole number prints without ".0" (150.0 -> "150"); other numbers
  `str()`. Booleans unchanged.
- FE `ValuesAndWordsTab.tsx`: a numeric key shows those values as rows with the same Icons column (no add / rename of values).

## crew-migration SQL (shared dev DB)

```sql
ALTER TABLE price_tag_request_lines ADD COLUMN IF NOT EXISTS excluded_variant_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
```

## Test list (tester writes these red first)

BE (pytest, Postgres, `tests/_pg_fixture.py`, seed own chain):
1. Upgrade slot rows carry `topup_amount` on a line and in the editor preview (`_preview_slots`).
2. `doc_has_feature_icons` true for an accessories layer whose card has a feature_icons element; false otherwise.
3. `variant_members`: SRTWC8354-SH tree (-150, -200, -P, -UF, -UF-150, -UF-200, -UF-300; -UF-* under -UF) returns all 7,
   ordered; a cycle does not loop; another company's product never appears.
4. Tag payload `variants`: excludes discontinued, inactive and `excluded_variant_ids`; each has specs with `raw`.
5. Line create / update: `excluded_variant_ids` round trip; non-member -> 422 NOT_A_VARIANT; the line product itself -> 422.
6. Chooser lookup returns members with list prices and discontinued flags; 403 without permission.
7. `spec_value_keys` for numeric trap_length = distinct normalised values; value-icons PUT accepts "150".
8. `_spec_raw_text(150.0) == "150"`, `(150.5) == "150.5"`, bools unchanged.
9. Migration: column exists with default [] (migration test pattern of ptag_0019).

FE (vitest):
1. `upgradesOf`: SRTKS2432 combo with SRTKT71SS upgrade (top-up 150, LP 440, SP 949) -> one item: code, name, LP 440,
   topup 150, price_with_upgrade 1099, image and specs from the slot row; picked upgrade -> []; no combo -> [].
2. `accessoriesOf` with `list:'upgrades'` returns upgradesOf; without `list` unchanged (existing tests stay green).
3. `cardFieldValue` topup / price_with_upgrade; `cardElementsFor` prefix "TOPUP " -> "TOPUP RM 150"; empty topup drops the
   element and closes up; feature_icons element resolves icons and drops when none.
4. `defaultUpgradeCard` has no price_with_upgrade element; has topup, code, name, price, picture, feature_icons.
5. `resolveSlotText` `upgrade_topup` on Upgrade 1 -> "TOPUP RM 150"; picked -> ''; not on an upgrade position -> '';
   `sell_price_with_upgrade` -> "SP with upgrade RM 1,099".
6. `variantFeatureIcons`: union in rule order, each once; discontinued already filtered by payload; leaf (no variants) =
   own icons.
7. Render accuracy: the same card + item through `cardElementsFor` gives identical element rects for canvas and print
   (both renderers call it); a snapshot-free assertion that KonvaTagLayer and TagSheetRenderer draw the same number of
   feature icons for the upgrade card and for an "All variants" layer.
8. InspectorPanel: List segmented control switches to Upgrades and seeds the default card; card element Shows offers Top-up
   and SP with upgrade; feature icons layer Product select offers "All variants".
9. PriceTagLinesTable: chooser lists members all ticked, line product locked, unticking sends `excluded_variant_ids`;
   Q5 warning text with min / max list price; hidden when prices are equal.
10. ValuesAndWordsTab: numeric key lists values with the Icons column.
