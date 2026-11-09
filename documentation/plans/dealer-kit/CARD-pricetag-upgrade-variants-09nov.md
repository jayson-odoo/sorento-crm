# CARD: upgrade items on combo tags + one tag per product family with variant icons (PRICETAG-UPGRADE-VARIANTS, 9 Nov)

Behaviour card, design first.

## Owner rulings (9 Nov ~11:45)

- Q1 (a): upgrades stay the combo's existing upgrade parts; the Accessories box gains "Lists: Upgrades".
- Q2 (a): "SP with upgrade" is a placeable card field, off on the default card.
- Q4 (a): trap icons sit on `trap_length` values 150 / 200 / 250 and `trap_type` p_trap (spec=value rule).
- Q3 (~12:00, "all should be pulled and I can choose"): the WHOLE variant tree under the line's product, with a
  per-line chooser on the request line ("Variants on this tag", all ticked by default, the line's own product always
  on). The template only says "Product: All variants". The line stores the unticked members, so a variant added later
  joins ticked; a pinned tag freezes the members it printed. Supersedes F1 / F4 "direct variants" below.
- Q5 (a) (~12:00): the tag prints the line product's own hand-picked LP / SP; when ticked members' list prices differ
  the request line warns "Variants price differently: RM x to RM y" (warning only, never blocks).
- Mock: `pricetag-upgrade-variants-mock.html` (v2: owner asked "are we reusing our upgrade field?"; yes, the box
  names its source, the combo's existing upgrade parts, product page > Combos). No code until the mock is approved. Plan:
`PLAN-pricetag-upgrade-variants-09nov.md` (same folder). Paths: BE = `sorento_crm_backend/`,
FE = `sorento_crm_frontend/`.

## Owner's ask (9 Nov ~11:40)

Two sample tags.
1. Combo SRTKS2432 sink (LP RM 1,150) + SRTKT1862SS tap (LP RM 285), FREE drainer + chopping
   board, an "UPGRADE" box "TOPUP RM 150" SRTKT71SS pull-out shower mixer (LP RM 440) with its own
   feature icons, SP RM 949 NETT, icons SUS304 / nano / 25-year warranty / anti-bacteria.
2. One tag for WC SRTWC8354-SH (LP RM 1,750, SP RM 799 NETT) with icons 6" S-trap 150mm,
   8" S-trap 200mm, 10" S-trap 250mm, P-trap 180mm, UF seat cover. Codes behind it:
   SRTWC8354-SH-150, -SH-200, -SH (= 250), -SH-P.

## What exists today (measured)

### Upgrades are already modelled on the combo (this is NOT a new concept)

- A combo part is fixed, a choice option, or an **upgrade**: `ProductComboPart.is_upgrade` +
  `topup_amount` (BE `app/models/product_combo.py:136-140`). An upgrade is a real catalogue
  product (`part_product_id`, `:131`), so its code, description, lead photo, LP and specs are
  already live data. Edited on the product page combo block (FE
  `app/(protected)/master-data-management/products/[id]/components/ProductCombosSection.tsx:275-303`,
  `:496`), saved by `app/services/product_combo_service.py:503-555`.
- Price: a PICKED upgrade adds its top-up to the combo SP (`app/services/dealer_kit/pricing.py:679-714`).
  An upgrade on offer but not picked leaves SP alone (sample 1: SP RM 949, top-up shown beside it).
- Tag payload: `combo.upgrades = [{product_id, code, description, topup_amount, picked}]`
  (`app/services/dealer_kit/tag_data_service.py:1207-1215`) and `slots.upgrades` = one full product
  row per upgrade (`_line_slots`, `:1093-1097`; editor preview `_preview_slots`, `:1101-1125`).
  The slot row is `_part_row` (`:692-740`): code, name, specs (so feature icons), images, LP, SP.
  **It carries no `topup_amount`.**
- Designer: any layer can read "Upgrade N" (`SubjectSlot {kind:'upgrade', index}`, FE
  `lib/dealer-kit/tag-template-types.ts:153-157`; positions from `comboPositions`,
  `lib/dealer-kit/combo-slots.ts:104`). A text slot "Combo Top-ups" prints `UPGRADE` + one line per
  upgrade on offer, nothing once one is picked (`lib/dealer-kit/product-block.ts:325-375`,
  `InspectorPanel.tsx:91`).
- Fit: a template reading Upgrade N needs N upgrades (`combo-slots.ts:41-66`, BE
  `app/services/dealer_kit/template_needs.py:62-114`); a plain template fits every combo (`:46`).
- So sample 1 can almost be built today by hand-placing layers on "Upgrade 1" (photo, code, LP,
  feature icons). What is missing: the "TOPUP RM 150" figure, a styled repeating box for 1..n
  upgrades, and an "SP with this upgrade" figure.

### Free items / accessories (the box we reuse)

- Library `accessories` (`app/models/accessory.py:40`) with pictures (`:72`) and colours (`:99`);
  two independent lists `product_accessories` (`:116`) and `product_combo_accessories` (`:160`),
  an entry is a library accessory OR a catalogue product (`app/services/accessory_service.py:203-262`).
  Tag payload `TagAccessory` (FE `tag-template-types.ts:883`), read by `accessoriesOf`
  (`lib/dealer-kit/accessory-box.ts:99`).
- Designer layer `accessories`: one box, card designed inside the Tag Template designer
  (`CardLayout`/`CardElement`, `lib/dealer-kit/accessory-card.ts`), one layout function
  `cardBoxLayout` (`:70`) for canvas, preview and print, fields picked by `cardFieldValue`
  (`:216`), empty field hides and lifts the elements under it (`cardElementsFor`, `:322`), whole
  cards only + drop warning (`cardDropped`, `:202`), saved box designs = accessories templates.

### Product family and variants

- **Two different "families" exist.** `products.family_code` = the code before the first dash
  (`app/services/product_family.py:21-27`, column `app/models/product.py:311-314`): SRTWC8354 for
  every SRTWC8354-* code, too coarse for a tag. `products.variant_of_id` = the variant graph, each
  code points at its longest existing boundary-prefix parent (`product.py:295-305`,
  `app/services/variant_link_service.py:73-101`), hand-curatable (`variant_link_manual`). For this
  family: -SH-150, -SH-200, -SH-P, -SH-UF point at SRTWC8354-SH; -SH-UF-150 / -UF-200 / -UF-300
  point at -SH-UF (codes from `documentation/plans/_archive/master-data/PLAN-flyer-family-proposals.md:170-187`).
- A variant carries no "variant attribute" column. What tells them apart is their **specs**:
  `trap_type` (enum s_trap / p_trap, `app/services/product_spec_registry.py:1146-1157`),
  `trap_length` (numeric mm, `:1162-1172`, read from "S-TRAP 200MM"), `seat_material` (uf from
  "-UF" in the code or "UF ... SEAT" on the flyer, `:357-365`).
- Discontinued = `products.is_discontinued` (`product.py:361`); `is_active` separately.

### Spec -> feature icon rule

- Icons live on the spec VALUE: `product_spec_registry.value_icons` JSONB `{value: [asset ids]}`
  + `icon_order` (`app/models/product_spec.py:165-168`), set on Master Data > Product
  Specifications. `feature_icon_rules` flattens them in one display order
  (`app/services/dealer_kit/asset_service.py:470-530`); the FE matches on the spec's RAW value
  (`featureIconsFor`, `lib/dealer-kit/feature-icons.ts:34-52`; raw text `tag_data_service.py:311-315`).
- **Gap:** only boolean keys and keys with an allowed-value list can carry icons
  (`spec_value_keys`, `asset_service.py:455-466`). `trap_length` is numeric, so "150 mm -> 6" icon"
  cannot be set today.

## Proposed behaviour

### (a) Upgrades on a combo tag

U1. **One source of truth: the combo's upgrade parts.** No new accessory kind "upgrade": the combo
    already holds upgrades with a top-up and prices them (owner rule from 6 Nov: merge, no two
    parallel features). An upgrade is a catalogue product, so its code, description, picture, LP
    and feature icons are read live, exactly like a product free item.
U2. **The Accessories box gains "Lists: Free items | Upgrades"** (inspector, default Free items so
    every saved box prints as today). An Upgrades box reads the combo's upgrades on offer, in combo
    order, one card each, header default "UPGRADE". Same card designer, same layout function, same
    whole-cards-only + drop warning, same accessories templates.
U3. **New card fields for an upgrade card:** `Top-up` ("TOPUP RM 150"; prefix text editable on the
    element), `SP with upgrade` (combo SP + top-up, "RM 1,099"), and a `Feature icons` card element
    (that upgrade's own icons through `featureIconsFor`, missing icons take no space). Existing
    fields reused: picture, code, name (= description), spec, price (LP: RM 440). On a free-items
    box these fields are empty, so they hide.
U4. **Several upgrades:** one card per upgrade, in combo order. 0 upgrades on offer: the box prints
    nothing (frame, header, badge) and takes no space.
U5. **A picked upgrade** is part of the package: it leaves the box (it is now priced into SP, rule
    `pricing.py:713-714`), as "Combo Top-ups" already does. Box with nothing left prints nothing.
U6. **Fit:** an Upgrades box never makes a template "need" an upgrade (it is a list, like free
    items), so a template with one still fits a combo with none. Hand-placed "Upgrade N" layers keep
    their current fit rule.
U7. **Hand-placed layers too:** the text slots `Upgrade top-up` and `SP with upgrade` become
    bindable on an "Upgrade N" position (for templates that do not use the box), and the slot row
    gains `topup_amount`. One formatter shared with the card, so both print the same words.
U8. **Pinned tags freeze** the upgrades and their figures like every other fact; top-up edits reach
    a tag when it is re-pinned.
U9. Discontinued upgrade: stays on the tag and pickable (ruling 7 Nov 2a), grey hint in pickers only.

"More extensibility", what this covers and what it does not:
- Several upgrades per combo: yes (U4). Upgrade with its own icons / picture / LP: yes (U1, U3).
- SP-with-upgrade display: available as a field, the owner decides if it shows (Q2).
- "Upgrade of which line" (SRTKT71SS replaces the SRTKT1862SS tap): not built. Today the top-up is
  added to the package price whatever it replaces, and the sample tag does not print "replaces".
  Trigger to build it: a tag that must print "instead of X", or a combo with two upgrades for two
  different lines whose SP-with-upgrade must not stack. Then: `replaces_part_id` on the upgrade part.
- Per-combo text / picture overrides on an upgrade card (like the accessory entry pencil): not
  built; trigger = a tag that must say something other than the product's own description.

### (b) One tag per product family, with variant icons

F1. **Family = the line's product and its variants in the variant graph** (`variant_of_id`), never
    `family_code` (that would pull every SRTWC8354-* model). How deep: Q3.
F2. **The feature icons layer gains "Reads from: All variants"** (beside Main / combo positions). It
    shows the union of each member's icons, in the one registry order, each icon once. So the four
    trap icons come from the four variants, and a spec they share (UF seat cover) shows once. Same
    spec=value, one-layer rule; no per-product hard-coding; missing icons take no space; the layer's
    existing size / gap / align and drop warning apply.
F3. **Who maps value -> icon:** the admin, once per spec value, on Master Data > Product
    Specifications (where icons are set today). For the WC: `trap_length` 150 -> 6" S-trap,
    200 -> 8", 250 -> 10"; `trap_type` p_trap -> P-trap 180mm; `seat_material` uf -> UF seat cover.
    Build: a numeric key offers the values that actually occur on products (distinct, sorted) so
    one can carry an icon (Q4). Every other WC family gets the same icons with no extra work.
F4. **No new request flow.** The dealer picks the family's base code (SRTWC8354-SH) on the line as
    today; a layer on "All variants" pulls the rest. Code, name, picture and price layers keep
    reading the line's own product. Picking a child code (SRTWC8354-SH-150) makes "All variants"
    that product and the ones under it (just itself for a leaf).
F5. **Discontinued or inactive variant:** its icons leave the union (unless a live member gives the
    same icon). **Not in stock:** still shown; a tag is a catalogue claim, stock moves daily.
F6. **Price:** the tag prints the line product's own LP / SP (hand-picked LP / SP / "LP & SP" as
    today). Members priced differently: Q5.
F7. **Pinned tags freeze the member list and its icons.** A variant added later reaches the tag on
    re-pin.
F8. Designer with no preview product: "All variants" draws the template's sample icons like a
    Main-bound layer does today.

## Examples (codes real; dev-DB values to confirm, see SQL)

1. **SRTKS2432 combo (sample 1).** Fixed part SRTKT1862SS, upgrade SRTKT71SS top-up RM 150, free
   items drainer + chopping board. Free-items box + Upgrades box (1 card: photo, "SRTKT71SS",
   description, "LP: RM 440", "TOPUP RM 150", SRTKT71SS's own icons). SP RM 949 unchanged; if the
   dealer picks the upgrade, SP becomes RM 1,099 and the Upgrades box prints nothing.
2. **SRTWC8354-SH (sample 2).** Members -SH (250), -SH-150, -SH-200, -SH-P, -SH-UF (+ -SH-UF-150 /
   -200 / -300 one level deeper). With Q3 (a) the union is 6" / 8" / 10" S-trap, P-trap 180, UF
   seat cover = the owner's five icons. With the whole tree, a live -SH-UF-300 would add a 12"
   S-trap 300mm icon the owner's tag does not print.
3. **SRTKT71SS tap family** (variants -BL, -GM, -GY per the archived variant-graph plan): a family
   tag here shows colour icons only if the finish spec values carry icons; nothing to set up if not.
4. **SRTKS7061-BL combos (6 Nov tags):** no upgrades -> an Upgrades box on the template prints
   nothing and the template still fits (U4, U6).
5. **SRTWB7065 + SRTWT7202 + free SRTW5000:** free product item unchanged; no upgrade box.

Crew, run on the dev DB and paste back (read-only):

```sql
-- family members, their trap / seat specs, price and status
SELECT p.product_code, par.product_code AS variant_of, p.is_active, p.is_discontinued,
       p.list_price, s.values->'trap_type' AS trap_type, s.values->'trap_length' AS trap_length,
       s.values->'seat_material' AS seat
FROM products p
LEFT JOIN products par ON par.id = p.variant_of_id
LEFT JOIN product_specifications s ON s.product_id = p.id
WHERE p.product_code ILIKE 'SRTWC8354-SH%'
ORDER BY p.product_code;
-- the SRTKS2432 combo parts
SELECT c.name, pp.product_code, cp.choice_group, cp.is_upgrade, cp.topup_amount, cp.sell_price,
       c.list_price, c.sell_price
FROM product_combos c JOIN products h ON h.id = c.host_product_id
JOIN product_combo_parts cp ON cp.combo_id = c.id JOIN products pp ON pp.id = cp.part_product_id
WHERE h.product_code ILIKE 'SRTKS2432%' ORDER BY c.name, cp.sort_order;
-- how many combos carry upgrades today, and how trap_length is stored (number or text)
SELECT count(DISTINCT combo_id) FROM product_combo_parts WHERE is_upgrade;
SELECT jsonb_typeof(values->'trap_length') t, values->>'trap_length' v, count(*)
FROM product_specifications WHERE values ? 'trap_length' GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20;
```

(`product_specifications.values` JSONB, `app/models/product_spec.py:238-252`.)

## Edge cases

- Combo with 0 upgrades / all upgrades picked: Upgrades box prints nothing (U4, U5).
- 3 upgrades in a box sized for 1: whole cards only, the existing drop warning and sheet toast.
- Upgrade with no top-up set: the Top-up field hides; SP with upgrade hides (no figure to add).
- Combo with no SP: SP with upgrade hides (nothing to add to).
- Upgrade that is also a free item or a fixed part of the same combo: already refused (A14, 422).
- Family member with no trap spec read: contributes no trap icon; nothing printed in its place.
- Two members giving the same icon (-SH and -SH-UF both 250 mm): shown once.
- trap_length stored as 150 vs 150.0 vs "150": raw text must match the value the icon is set on;
  the build normalises numeric raw to its shortest form ("150") on both sides.
- An S-trap icon keyed on length alone would also fire for a P-trap of the same length (none
  measured in this family: -SH-P is 180). Q4 (b) removes the risk.
- A family whose members are all discontinued: the layer prints the line product's own icons only.
- Line names a leaf variant: "All variants" = itself (F4).
- Old templates and pinned rows: no layer reads "All variants" or an Upgrades box until a designer
  sets one, so every existing tag prints the same.

## Questions (answer with the letter; recommendation first)

Q1. Where do upgrades live?
    (a) **The combo's existing upgrade parts; the Accessories box gains "Lists: Upgrades"**
        (recommended: one source of truth, already priced, reuses the card designer).
    (b) A new "upgrade" kind of accessory list entry with its own top-up (a second place to keep
        upgrades in step with the combo's pricing).
Q2. "SP with upgrade" (RM 1,099) on an upgrade card:
    (a) **A field the designer can place; off on the default card** (recommended: your sample shows
        only TOPUP RM 150).
    (b) Always printed under the top-up.
Q3. Which variants does "All variants" include?
    (a) **The line's product and its direct variants** (recommended: on the archived codes it gives
        exactly your five icons: -150, -200, -P, -UF and the base).
    (b) The whole tree under it (adds -SH-UF-150 / -200 / -300; a 300 mm icon would appear).
    (c) A hand-picked "Tag variants" list on the product page.
Q4. Trap-size icons:
    (a) **Icons on `trap_length` values (150 / 200 / 250) plus `trap_type` p_trap** (recommended:
        reuses the spec=value rule; a numeric key just offers the values products actually have).
    (b) A new derived enum spec "Trap" (s_150, s_200, s_250, p_180) so S and P can never mix.
Q5. Family members priced differently:
    (a) **Print the line product's own price; the request line warns "Variants price differently:
        RM x to RM y"** (recommended: LP / SP stay hand-picked, nothing guessed).
    (b) Print "from RM x" (the lowest).
