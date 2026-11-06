# CARD: "Accessories included" box on price tags (PRICETAG-ACCESSORIES, 6 Nov)

Behaviour card. **Answered by the owner 6 Nov ~10:00; "Owner rulings" and "Rules (v2)" below win
over the original proposal (kept further down for the record).** Mock:
`pricetag-accessories-mock.html` (same folder). No build before the owner approves the mock.

## Owner rulings (6 Nov ~10:00)

Four real tags for **SRTKS7061-BL**: Ala Carte (no accessories box); Combo with 1 tap (box headed
"FREE" with DRAINER + PULL OUT DRAINER, vertical, beside the tap); a variant of it; Combo with 2 taps
(box headed "ACCESSORIES INCLUDED", HORIZONTAL row DRAINER, PULL OUT DRAINER, under the sink).

- Q1: lists live on BOTH the product and the combo, **independently**. A product often has none
  while its combo has free items, so a combo does **not** inherit the product's list.
- Q2 (a): whoever may edit products; library under Master Data > Products.
- Q3: each box is set **vertical OR horizontal** (both are on real tags).
- Q4 (a): one free short spec line.
- Q5: **MERGE with what exists.** Combo "Free items" and the request-line included text become this
  one system: existing values migrate into library items + lists (de-duplicated by name), one source
  of truth, no two parallel features.
- Header text and the optional "+" badge are **set per box on the template** ("FREE" vs
  "ACCESSORIES INCLUDED").

## Owner addendum (6 Nov ~10:45): free items can be real products

Example: wash basin combo SRTWB7065 + SRTWT7202 tap + a "FREE" box holding SRTW5000 (Popup Waste
80mm (w/o Overflow) Brass, LP: RM 68). Measured first: combos do NOT model free components
(`ProductComboPart` is fixed / choice / upgrade only; a fixed part never prices into a combo tag,
`pricing.py:666`), so there was no list of free products to reuse. Built:

A13. A list entry (product list or combo list) is EITHER a library accessory OR a catalogue
     product. A product entry's code, description (else name), lead photo and list price are read
     live; its card prints code, description and "LP: RM 68". Same box, same direction, header
     per box.
A14. One list of free products: a product that is already a part of the combo, or the host itself,
     cannot also be its free item (422).
A15. The free-text move and the combo importer turn a piece whose first word is a product code of
     the same company ("SRTW5000 Popup waste") into a PRODUCT entry; anything else is a library
     accessory.
A16. The "+" badge is drawn (on/off and colour per box), not a library picture.

## Measured for the merge

- Combo "Free items" is a 2000-char free text box on the product page
  (`ProductCombosSection.tsx:607-613`), saved by `product_combo_service.py:288-289`, sent to the tag
  as `combo.free_items` (`tag_data_service.py:1214`).
- The request-line text `included_accessories` has **no screen that writes it**: the portal form
  always sends `''` (`app/(auth)/portal/components/PriceTagRequestForm.tsx:1013`); only the API
  payload (`price_tag_request_service.py:535`) and the revision carry-over
  (`portal_revision_service.py:514-556`) touch it. Its only reader is the tag ("line text wins, else
  combo free items", `tag_data_service.py:973-975`, `:1816-1818`).
- Templates bind the text slot `included_accessories` ("Accessories") to a text layer
  (`InspectorPanel.tsx:84`, `product-block.ts:472`); the seeded sink combo uses it as the strip title.

## Rules (v2, after the rulings)

A1. **Accessories library** (Master Data > Products > Accessories): picture (optional, attachments
    pipeline like the combo picture), name (required, unique per company ignoring case), spec (one
    short line, optional). DataGrid + modal create/edit + deferred-action delete; delete refused while
    a product or combo lists it (the message names them).
A2. **Two independent lists**, each ordered by drag, picked from the library (create-in-place from
    the picker allowed): "Accessories included" on the product page Overview, and "Free items" on each
    combo block (replaces the free text box). A combo never falls back to its host product's list.
A3. **Which list a tag shows:** a combo tag shows the combo's list; an Ala Carte tag shows the
    product's list. Empty = no box.
A4. **Designer layer "Accessories"** (replaces "Add accessories strip"): per box on the template
    `direction` vertical | horizontal, header text (default "ACCESSORIES INCLUDED"), "+" badge on/off
    (+ its picture from the Badge library), fill, border colour/width, corner radius, header font
    size/colour, card picture size, name/spec font size, gap, and "Reads from" (main item or a combo
    position, like a photo layer).
A5. **Cards in list order;** vertical stacks top to bottom, horizontal runs left to right. Fewer
    cards = the box closes up from the bottom (vertical) or the right (horizontal); its top-left
    corner stays put; other layers never move.
A6. **Too many:** only WHOLE cards print. Inspector: "2 of 5 accessories do not fit this box. Make
    the box bigger or the cards smaller." Sheet toast per tag, the same hook feature icons use.
A7. **No list / empty list:** frame, header and badge do not print. Designer without a preview
    product draws 2 sample cards so the box can be styled.
A8. **No picture:** name + spec take the card's full width (vertical) or the picture's space
    (horizontal); nothing grey prints.
A9. **Pinned tags freeze the list** like every other product fact; library edits reach a tag when it
    is re-pinned.
A10. **One layout function** (`accessoryBoxLayout`) for canvas, request preview and print.
A11. **One source of truth:** the old text slot `included_accessories` stays bindable so existing
    templates keep printing, but its text is now built from the list ("DRAINER, PULL OUT DRAINER").
    The request line no longer carries its own text (no screen ever wrote it).
A12. **Migration (one-off data move, additive schema):** every non-blank combo `free_items` and
    request-line `included_accessories` is split into items (on line breaks, and on commas/"+"
    between items, Q-M1), trimmed, de-duplicated by name ignoring case into the library (name =
    the piece, spec empty, no picture), and attached in their written order: combo text -> that
    combo's list; line text -> the line's combo list if it has a combo and that list is empty, else
    the line's product list if empty; anything that would overwrite a different list is written to
    the migration report instead. Old columns stay in the DB (additive only), unread; a later lane
    drops them.

## Open before build (in the mock crew-ask)

Q-M1. Splitting old free text: (a) **split on line breaks, commas and " + "** (recommended; crew to
      paste the distinct values first so a spec such as "390x300x140, Depth: 160mm" is not cut) /
      (b) each old text becomes ONE item as written.
Q-M2. Horizontal card size: (a) **every card the same width, set on the box** (recommended; matches
      the 2-tap tag) / (b) each card as wide as its name.

Crew, measure on the dev DB for Q-M1:

```sql
SELECT 'combo' AS src, free_items AS txt, count(*) FROM product_combos
 WHERE coalesce(trim(free_items), '') <> '' GROUP BY free_items
UNION ALL
SELECT 'line', included_accessories, count(*) FROM price_tag_request_lines
 WHERE coalesce(trim(included_accessories), '') <> '' GROUP BY included_accessories
ORDER BY 1, 3 DESC;
```

---

# Original proposal (superseded where the rulings differ)

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
