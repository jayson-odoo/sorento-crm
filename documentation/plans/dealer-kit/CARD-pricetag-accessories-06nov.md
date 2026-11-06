# CARD: "Accessories included" box on price tags (PRICETAG-ACCESSORIES, 6 Nov)

Behaviour card. **Waiting for the owner's answers to Q1-Q5.** No mock or build before they land.

Owner (6 Nov ~09:45): tag 148 x 105 mm for sink SRTKS7846. In the middle, a rounded box with a "+"
badge and the header "ACCESSORIES INCLUDED", holding 3 stacked mini-cards (picture + name + spec):
CHOPPING BOARD; COLANDER 390x300x140, Depth: 160mm; DRAINER 390x300x140, Depth: 160mm. Not product
codes. Today the designer can only paste the whole box as a static picture.

## What exists today (measured)

Data:
- **Free text, two places, no pictures.** `price_tag_request_lines.included_accessories` (Text,
  `sorento_crm_backend/app/models/price_tag.py:254`) and `product_combos.free_items` (Text,
  `app/models/product_combo.py:74`, edited on the product page, `ProductCombosSection.tsx:610`). The
  tag reads the line's text, else the combo's (`app/services/dealer_kit/tag_data_service.py:973-975`,
  pinned path `:1816-1818`). The designer binds it to a TEXT layer through the slot
  `included_accessories` ("Accessories", `InspectorPanel.tsx:84`, `lib/dealer-kit/product-block.ts:472`).
- **Yes/no spec flags, no picture, no spec text.** `has_chopping_board` and `has_drainer` are
  derived from the product text (`app/services/product_spec_registry.py:246`, `:367`, labels at
  `:929`, `:1232`). There is **no colander flag**.
- A combo belongs to one host product (`product_combos.host_product_id`, `product_combo.py:59`),
  so "combo inherits from its product" needs no new link.
- **Nothing in AutoCount sync or the product tables holds an ordered, pictured accessory list.**
  `product_compatibility` is seat cover / mirror / shelf fit links between real SKUs
  (`app/models/product_compatibility.py:1-4`), not included items.
- Pictures: one pipeline already serves this kind of thing. A combo's own picture is an
  `attachments` row pointed at by `image_attachment_id` (`product_combo.py:68`, upload/replace
  in `app/services/product_combo_service.py:360-392`). Dealer Kit library assets accept
  `kind = icon | badge | ...` (`app/services/dealer_kit/asset_service.py:63`).

Designer:
- **"Add accessories strip" already exists, but static.** Toolbar button (`CanvasToolbar.tsx:323`)
  opens a product picker, then `buildAccessoriesStrip` (`lib/dealer-kit/product-block.ts:1209`)
  writes a title text plus one image + caption (the product CODE) per picked product into the
  template (`TagCanvasEditor.tsx:1289-1312`). Frozen at design time: same pictures on every tag.
- Draws today: rounded rectangle (`shape` with `cornerRadius`, `tag-template-types.ts:199-212`),
  text, image, fixed badge (`:223-226`), group (`:347-358`, a selection bundle, no layout).
  **No layer repeats a card per data item.** The nearest is `feature_icons`
  (`tag-template-types.ts:336-345`): one shared rule `featureIconsFor` + `featureIconFit`
  (`lib/dealer-kit/feature-icons.ts:34`, `:83`) used by the editor canvas, the request preview and
  print (`TagSheetRenderer.tsx:61`, `:1278`), with the "N of M icons do not fit this box" inspector
  warning (`InspectorPanel.tsx:1868-1915`) and the sheet toast (`feature-icon-drops.ts`,
  `useFeatureIconDropToast.ts:16`). This lane copies that pattern.

## Proposed behaviour

R1. **Accessories library (master data).** One Accessory = picture (optional) + name (required,
    e.g. "COLANDER") + spec (one short line, optional, e.g. "390x300x140, Depth: 160mm"). Created
    once, reused on any number of products. List + modal create/edit + deferred-action delete per
    the CRUD standard; an accessory in use on a product cannot be deleted (it lists the products).
R2. **Product page gets an "Accessories included" section:** pick accessories from the library,
    drag to order. Empty state when none.
R3. **A combo shows its host product's accessories** unless the combo has its own list (Q1).
R4. **New designer layer "Accessories included"** (toolbar button; replaces the static strip, Q5).
    One box styled with the existing inspector controls: fill, border, corner radius, header text
    + font/colour, optional badge picture top-left (the "+"), card picture size, name and spec
    font/colour, gap. It reads one product on the tag, like a photo: the main item or a combo
    position ("Reads from").
R5. **Cards stack top to bottom in the product's order** (Q3); fewer accessories = the box
    shrinks from the bottom (header and top edge stay put; other layers do not move).
R6. **Too many to fit:** as many WHOLE cards as fit are printed, the rest dropped, never cut in
    half. Inspector: "2 of 5 accessories do not fit this box. Make the box taller or the cards
    smaller." Sheet: the same toast feature icons use, per tag ("Tag 2a: 2 accessories do not fit").
R7. **No accessories: the whole box (frame, header, badge) does not print.** In the designer with
    no preview product it shows 3 sample cards so it can be styled.
R8. **Accessory without a picture:** the card keeps its height and the name + spec take the full
    card width (no grey placeholder printed).
R9. **A requested tag freezes its accessory list when the tag is pinned**, like every other
    product fact on the tag; editing the library later does not change an already-pinned tag
    until it is re-pinned.
R10. **One function lays out the box** for canvas, request preview and print (like
    `featureIconFit`), so the three cannot disagree.
R11. Nothing about the existing free text changes: the "Accessories" text slot and the request
    line / combo free text keep working as today (Q5).

## Examples

1. **SRTKS7846 (owner's):** CHOPPING BOARD (no spec); COLANDER, "390x300x140, Depth: 160mm";
   DRAINER, "390x300x140, Depth: 160mm". Box 3 cards tall on the 148 x 105 mm tag.
2. and 3. **Two more real products:** not measurable from the cloud sandbox (no dev DB here, by
   contract). Crew, run on the dev DB and paste back the first two rows that look right:

   ```sql
   SELECT p.product_code, p.product_name
   FROM products p
   WHERE p.is_active
     AND (p.product_name ILIKE '%CHOPPING BOARD%' OR p.product_name ILIKE '%COLANDER%'
          OR p.product_name ILIKE '%DRAINER%' OR p.description ILIKE '%COLANDER%')
   ORDER BY p.product_code LIMIT 20;
   ```
   Expected shapes: a sink with 1 accessory (chopping board only: box 1 card tall) and a sink
   with 4+ (box shows what fits, R6 warning).

Edge cases: no accessories (R7); 5+ accessories (R6); accessory without picture (R8); accessory
without spec (name only, card keeps its height); combo with no own list and a host with none (R7);
the same accessory twice on one product (refused when picking).

## Questions (answer with the letter; recommendation first)

Q1. Where is the list attached?
    (a) **On the product; a combo uses its host product's list unless it has its own**
        (recommended: one place to maintain, combos that add a free item can still differ).
    (b) Product only, combos always inherit.
    (c) Combo only.
Q2. Who maintains the accessories library and the product lists?
    (a) **Whoever may edit products (same permission as the product page)**, library under
        Master Data > Products > Accessories (recommended: no new role, it is product data).
    (b) Dealer Kit / marketing only, library under Dealer Kit.
Q3. Card stacking:
    (a) **Vertical only, as on your SRTKS7846 tag** (recommended: build horizontal when a template
        needs it).
    (b) A per-layer setting, vertical or horizontal.
Q4. Spec text:
    (a) **One free short line per accessory** ("390x300x140, Depth: 160mm") (recommended: prints
        exactly what you type; nothing to calculate).
    (b) Structured fields (W x D x H, depth) formatted by the tag.
Q5. The old ways:
    (a) **Keep the free-text "Accessories" slot and combo "Free items" as they are; remove the
        static "Add accessories strip" button** (recommended: two buttons making the same box
        would confuse; templates already using the static strip keep their layers untouched).
    (b) Keep the static strip button too.
    (c) Also retire the free text and move everything to the library.
