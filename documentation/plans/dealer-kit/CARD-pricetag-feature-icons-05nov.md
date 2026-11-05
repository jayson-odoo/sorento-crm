# CARD: feature icons on price tags (hot / cold / mixer, SUS 304, warranty, anti-bacteria) (PRICETAG-DESIGNER-GAPS item 3, 5 Nov)

Behaviour card. **Answered by the owner 5 Nov ~17:45; see "Owner rulings" below, which win over
the proposal where they differ.**

Owner (5 Nov): "how do we cater all these logos ah like there is one heat logo is for hot mixer tap, one
cold logo is for cold mixer tap then i think if it is mixed then heat cold also will come out". The
printed flyer tag also carries a row of badges: SUS 304, warranty 25 years, anti-bacteria.

## What exists today (measured)

- **Hot / cold is already product data.** Spec key `water_supply`, enum `cold_only` | `mixer`
  (`sorento_crm_backend/app/services/product_spec_registry.py:818-832`), stored per product in
  `product_specifications.values` JSONB (`app/models/product_spec.py:231-264`). It is derived from
  the product text ("COLD TAP" -> `cold_only`, 878 products; "MIXER TAP"/"MIXER" -> `mixer`, 348)
  (`app/services/product_spec_derivation.py:255-259`). There is **no hot-only value**: "BASIN HOT
  TAP" only sets `product_type=basin_tap` (`product_spec_derivation.py:196`).
- **SUS 304 is product data.** Spec key `steel_grade`, enum `304` | `201`
  (`product_spec_registry.py:964-976`), derived from "SUS 304", "S/STEEL 304" etc.
- **Warranty is a product column, not on the tag.** `products.warranty_months`
  (`app/models/product.py:334`); the tag payload does not carry it
  (`app/services/dealer_kit/tag_data_service.py:333-368`).
- **Anti-bacteria exists nowhere** in product data, the spec registry, seeds or migrations.
- **Every product and every combo part already reaches the tag with its specs.** `product_tag_data`
  returns `specs: [{key, label, value, unit}]` (`tag_data_service.py:258-298`), where `value` is the
  DISPLAY text (title-cased), not the raw enum. Combo parts go through the same builder
  (`_part_row`, `tag_data_service.py:671-722`), and a layer picks a part with `subjectSlot`
  (`lib/dealer-kit/product-block.ts:255-288`), the same way a part's photo is placed today.
- **Icons have a home already.** Dealer Kit assets accept `kind = 'icon'`
  (`app/services/dealer_kit/asset_service.py:63`), with upload and pick in `AssetPickerDialog`.
- **No layer chooses a picture by data.** The `badge` layer always draws its one fixed asset
  (`lib/dealer-kit/tag-template-types.ts:219-222`); the inspector's `badges` slot binding resolves to
  nothing (`product-block.ts:504`).

## Proposed behaviour

R1. **New layer: "Feature icons".** Placed and sized like any layer. It belongs to one product on the
    tag: the main item, or a combo position (same "Reads from" picker a photo layer has). So on a
    "Kitchen sink with 1 tap" tag the designer drops the icon row next to the tap photo and points it
    at the tap's position; it shows the TAP's icons, not the sink's.
R2. **Rules: fact -> icon.** Each rule says "when <spec> is <value>, show <icon>". Icons are uploaded
    once to the Dealer Kit asset library as kind Icon. Starter rules the owner would set up:
    - Water supply = Cold only -> cold icon
    - Water supply = Mixer -> hot icon + cold icon (Q2)
    - Steel grade = 304 -> "SUS 304" icon
    - Warranty = 25 years -> "25 years warranty" icon (needs Q3)
R3. **Icons line up left to right** in rule order, each scaled to the row height, a small gap between.
R4. **Matching uses the raw value** (`mixer`, not the display text "Mixer"), so renaming a label never
    silently drops an icon. The tag payload gains the raw value next to the display one.
R5. **Missing data:** a product with no matching fact shows no icon for it (Q5). In the designer an
    empty row shows a dashed outline labelled "Feature icons" so it can still be placed; print shows
    nothing.
R6. Same rule in canvas, preview and print: one shared function picks the icons, used by the editor
    canvas and `TagSheetRenderer`, so they cannot disagree.

## Questions (answer with the letter; recommendation first)

Q1. Where do the rules live?
    (a) **Inside the icon layer of each template** (recommended): no new table, no new admin screen;
        copy the layer to reuse it on another template. Simplest thing that works for 3 templates.
    (b) One shared "Icon rules" list in Dealer Kit that every template's icon layer follows.
        Build when a rule has to change on many templates at once.
Q2. A mixer tap shows:
    (a) **The hot icon and the cold icon side by side** (recommended; your words "heat cold also will
        come out").
    (b) One dedicated mixer icon.
Q3. Warranty icon:
    (a) **Bring the product's existing warranty (months) onto the tag and match on it** (recommended;
        `products.warranty_months` already exists).
    (b) A plain fixed badge you place by hand on the template.
Q4. Anti-bacteria has no product data anywhere:
    (a) **A fixed badge placed by hand on templates for those products** (recommended until it varies
        per product on the same template).
    (b) A new product spec "Anti-bacteria (yes / no)" filled per product, then a rule like the others.
Q5. When a product lacks one of the facts:
    (a) **The remaining icons close up to the left, no gap** (recommended).
    (b) Each icon keeps a fixed spot and the gap stays empty.

Hot-only: no product carries a hot-only fact today (`water_supply` has no such value), so no hot-only
rule is proposed. Say so if hot-only taps exist and need their own icon.

## Owner rulings (5 Nov ~17:45 MYT, final)

- **Q1: the rule lives ON the icon asset.** A Dealer Kit asset of kind Icon carries "show when
  <spec> is <value(s)>" (e.g. `water_supply` = `cold_only`; `steel_grade` = `304`). No per-template
  rule copies, no separate rules screen. The template has ONE "Feature icons" layer, bound to the
  main item or a combo position, that shows every icon whose rule matches that product's specs.
- **Q2 (a):** a mixer shows the hot AND the cold icon. With the rule on the asset this is: the cold
  icon shows for `cold_only` or `mixer`, the hot icon shows for `mixer`.
- **Q3:** warranty is a static asset the designer places (no `warranty_months` rule).
- **Q4:** anti-bacteria is a static asset the designer places.
- **Q5:** a missing fact takes no space; matching icons close up. The designer adjusts the layer:
  position / size, icon size, spacing, order.

## Build (revised by the rulings)

B1. `dealer_kit.asset` gains `show_when_spec_key` (nullable) and `show_when_values` (text array,
    nullable). Only an Icon may carry them; both or neither. Edited on the asset in the Dealer Kit
    asset library.
B2. The tag payload's `specs[]` gains `raw` (the stored value, e.g. `mixer`) beside the display
    `value`, so matching never depends on a label (R4).
B3. Layer kind `feature_icons`: props `iconSize_mm`, `gap_mm`, `align` (left / centre / right), `order`
    (asset ids the designer has put first; the rest follow by name), plus the usual subject
    (`subjectPart` / `subjectSlot`). Icons sit in one row inside the layer box.
B4. One pure function `featureIconsFor(product specs, icon library, order)` picks the icons; the
    canvas, the request preview and the print page all call it. Icon pictures reach the print page
    through the same asset URL map every other asset layer uses.
