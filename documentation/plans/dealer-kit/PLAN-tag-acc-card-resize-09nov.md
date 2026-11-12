# PLAN: accessories box preview vanishes when small; resizable cards; card text fields and style (TAG-ACC-CARD-RESIZE)

Status: Built, reviewer READY, awaiting owner hand test (not merged). Track: standard (diff over 300 lines, no migration, no auth/RBAC, no new ingest).

## Journey
Owner, Dealer Kit > Tag Templates designer (template BF_SP, tag size BF_LP 98x140 mm, combo template):
1. Resizing the accessories box small makes the preview vanish (only the "Accessories" placeholder shows).
2. The white card backgrounds inside the box cannot be resized.
3. (22:15) A card Text element needs the flexibility of a normal text box: price tag description, list price, free text with fields.
4. (22:30) The Top-up text (any card Text) must style its background like the header text.
5. (22:35) Fields like the price tag description must work on Upgrades cards too.

## Root cause (1)
`cardBoxLayout` (`sorento_crm_frontend/lib/dealer-kit/accessory-card.ts`) clamped the scale at `shrinkMin`
(70%) and returned an empty layout when one card at 70% did not fit across (`cardCross * scale > availCross`)
or along (`shown === 0`); the grid path the same. The canvas then drew the dashed "Accessories"
placeholder (`KonvaTagLayer.tsx` DesignedAccessoriesContent `box.shown === 0`) and print drew nothing
(`TagSheetRenderer.tsx` renderDesignedAccessories).

## Rulings (owner, 9 Nov ~22:30, all recommendation (a))
- Q1: a box too small for one card at `shrinkMin` keeps shrinking to the size one whole card fits at, floor
  35% (`CARD_SHRINK_FLOOR`); below the floor one card at the floor, clipped to the box (`clipped`). Never blank.
  Only boxes that drew nothing before change, so every existing printed layout is pixel-identical.
- Q2: "+N" chip for dropped cards on the editor canvas only (`accessoryDropMarker` on the editor's display); print unchanged.
- Q3: Edit card mode, no element selected: the card frame has resize handles (right, bottom, corner) that set
  `card.width_mm/height_mm` for every card; elements keep their mm. Inspector shows Card width / Card height
  for a designed card. Card fill Transparent was already a swatch.
- Q4: a card's fixed text resolves `{{product.*}}` per item through the shared `renderMergeFields` /
  `renderPriceTagDescription` (`lib/dealer-kit/merge-fields.ts`) with the item as the bound product
  (`accessoryBinding`); "Insert field" opens the normal `InsertFieldDialog` (Product group). A sole
  `{{product.price_tag_description}}` keeps its rich formatting, as `layerRichBlocks` does on the main canvas.
  Per item: catalogue product = code, name, list price, sell price (offer, else empty), spec lines, price
  tag description (backend `tag_product_entry`); upgrade = the same from its slot row (`upgradesOf`);
  library accessory = name, and its spec as both description and spec lines; anything else prints nothing,
  and a line whose fields are all empty is dropped with no gap. Existing fixed choices unchanged.
- Style (22:30): a card Text element gets the header's controls: TypographyControls with line height and
  padding, Background (ColorPicker, Transparent = none) and Corner Radius. `cardTextBox` gives canvas and
  print the same background rect and padded text box; nothing stored = the element rect, as before.

## Tests
- `lib/dealer-kit/accessory-card.test.ts` (small-box rule), `lib/dealer-kit/accessory-card.fields.test.ts`
  (fields, rich, upgrades, `cardTextBox`), `AccessoryEditOverlay.card-resize.test.tsx` (frame handles),
  `components/dealer-kit/AccessoriesCardResizeParity.test.tsx` (canvas = print), backend
  `tests/test_accessory_card_fields.py`.

## Later (not built)
- An editable shrink minimum (still the plan's later item); the "Shrink to fit, smallest 70%" note stays.
