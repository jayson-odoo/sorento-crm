# CARD: price tags render every product and combo correctly (PRICETAG-COMBO-RENDER, 4 Nov)

Behaviour card. Read of `origin/main` 6795425a. Owner goal (4 Nov): the price tag shows every
product and every combo correctly; a sink combo with 1..5 taps and a basin + tap combo need each
tap's own picture and description, not one combo-level picture and paragraph.

Out of scope (owner): submit/approve lead times, deadlines, SOP checks.

## 1. Render-coverage table (today, on main)

Verdicts: **OK** renders correctly, **PARTLY** renders with something wrong, **CANNOT** no
template or data path can print it. Real-data columns marked *(data pending)* are filled from
the dev data request on PR #2172.

| # | Tag case (reference PDF) | Verdict | What is wrong | Where |
|---|---|---|---|---|
| 1 | Small 59 x 29, single product, LP or SP | CANNOT (no template) | No 59 x 29 template exists; the Small templates on dev are 95 x 44.5 (crew finding). Content itself (code, short description, one price via the `price` slot) is reachable. | template set; `price` slot `lib/dealer-kit/product-block.ts:377-385` |
| 2 | DIY 95 x 44, code + description + barcode + price | PARTLY | Layout exists; the barcode layer prints empty because only 1 of 15,442 products has a barcode (crew finding). Description blank when `price_tag_description` is blank (548 of 4,032 sink/tap/basin/BF/Cabana products have one; Cabana none). | barcode `product-block.ts:453-462`; description `:402`, `:435` |
| 3 | Big 105 x 148 ala carte, LP | PARTLY | No 105 x 148 template in the seeds (seeded sizes are 94 x 134.2 to 147.7 x 103.9, `scripts/tag_template_seed_docs.py:492-1065`). Single-product content resolves correctly; description gap as row 2. | seeds |
| 4 | Big ala carte, SP (struck LP + SP) | OK when the line is on SP and a promotion prices it | Same template gap as row 3. | `price-badge.ts:183-233`; `price` slot |
| 5 | Wash basin ala carte | OK (same as 3/4) | Description gap. Art basin template is 124.6 x 87.6 (`tag_template_seed_docs.py:659`). | |
| 6 | Wash basin combo: basin + tap + FOC | PARTLY | Tap is a part, so `subjectPart: n` can reach its photo/code/description (`product-block.ts:214-226`), but only at a fixed index and fixed position; no shipped template sets `subjectPart` (crew finding). FOC is free text only (`product_combos.free_items`, `app/models/product_combo.py:74`), printed through `included_accessories` (`tag_data_service.py:972-975`): no FOC picture, FOC code not checked against the catalogue. Combo with no stored SP prints the SUM of parts as the price (`tag_data_service.py:853-883`, kept by `pricing.py:722-723`). Basin + tap combos with FOC (SRTWB1419-BL + SRTWT7449) do not exist on dev (crew finding). | |
| 7 | Kitchen sink ala carte, LP / SP | OK | Seeded `sink-ala-carte` 125.9 x 88.6 (`tag_template_seed_docs.py:619`). Description gap. | |
| 8 | Kitchen sink combo, 1 tap (fixed) | PARTLY | Seeded `sink-combo` template (`tag_template_seed_docs.py:491-617`) has three tap blocks (`:604-609`) with NO `subjectPart`, so each block prints the HOST sink's photo, code and specs, and each block's price badge prints the whole-tag total (`product-block.ts:214-216`, `:581-597`). Starter "Kitchen sink combo" template (`scripts/import_product_combos.py:283-296`) has one `combo_image` and text lists only: no tap photo. Sum-of-parts price when no combo SP (only 2 of 169 combos have SP). | |
| 9 | Kitchen sink combo, 2..5 taps (choose one) | CANNOT | The taps are one choice group; on the request they become ONE open part row (`lib/dealer-kit/price-tag-draft-lines.ts:138-160`). Per-tap pictures need a fixed layer per index; on a tag with fewer taps than blocks, a missing index prints the HOST again (no `strict_parts` on price tags, `product-block.ts:220-226`). `combo_choices` is a plain text list (`product-block.ts:255-290`); a text box drops lines that do not fit, no auto-fit (`lib/dealer-kit/text-layout.ts:1-14`), so 4-5 taps overflow. Option SPs blank leave a sum. | |
| 10 | Top up: "TOP UP RMxx, UPGRADE TO <code>" | PARTLY | Prints `UPGRADE` + `CODE description +RMxx` (`product-block.ts:294-304`): different wording, no picture of the upgrade product; the amount is missing on 43 of 44 upgrade parts because the 1 Nov import ignores prices (`scripts/import_product_combos.py:14-17`). | |
| 11 | Combo info line: full codes joined "+" | PARTLY | `set_members` prints one line per part, `+ CODE name dims` (`tag_data_service.py:724-751`), not `CODE+CODE+CODE`; an open group prints `ROLE: A / B / C`. | |
| 12 | "RMxxx NETT" combo price | PARTLY | A combo SP prints as a bare figure (`product-block.ts:366-372`); "NETT" can only be static template text, so it also prints on a line whose figure is the sum of parts. Only 2/169 combos carry a SP. | |
| 13 | Bathroom furniture set (cabinet + mirror cabinet + tap) | PARTLY | Combo-level picture + description works (owner: fine for BF). Price: SRTBF11829 + SRTMCB8083-BL + SRTWT6203-GM has SP 2099 only in an expired promotion, so today it prints the sum of parts. Starter template is A5 148 x 210 (`import_product_combos.py:266-281`), not 105 x 148. | |
| 14 | Combo seeded from flyer | PARTLY | 169 combos on dev, 162 from the 1 Nov flyer import, SRT only, no prices; Cabana hosts never imported; CKS7306+CB1520SS-DIY, KS6645-NL+CB1530SS-BL, SRTWB1419-BL+SRTWT7449 have no combo; SRTKS2432 has a different tap group to the current PDF (crew findings). Flyer reading extracts codes per page, not combos (`app/services/dealer_kit/flyer_reading_service.py`). | |

Canvas, preview and PDF agree today: text breaks once in `textLayerLines` for both surfaces
(`lib/dealer-kit/text-layout.ts:1-14`) and the print page resolves through the same
`layerText` / `resolveSlotText` (`app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer.tsx:33-36`).
Any new layer must keep that single path.

## 2. Behaviour card

### Rules (proposed)

R1. **Component list layer.** A new template layer, "Component list", holds one repeated block
    per item of the combo. Item order: host, fixed parts ("+"), the options of each choice group
    ("OR" between them), free items ("FOC"), upgrades ("TOP UP"). Each block shows, as the
    designer switches on: picture, full code, tag description, LP, the option's own SP, and a
    connector label ("+", "OR", "FOC", "TOP UP RM 150"). The designer places ONE block; the layer
    repeats it across its box (row or column, designer's pick), cells share the box equally, so
    1..5 items always fit; type shrinks to a floor (6 pt) and a description longer than its cell
    is cut with an ellipsis, never dropped silently. The designer chooses which item kinds the
    layer shows (for example a second list only for FOC).
R2. **One renderer.** The block layout is one pure function in `lib/dealer-kit/` called by the
    canvas, the live preview and the PDF print page, the same way `textLayerLines` is today, so
    the three cannot disagree.
R3. **Description per component** comes from that product's `price_tag_description`; blank
    falls back to the product name, and the request flags "No tag description" on the line so it
    is seen before printing. The combo's own description stays for the combo-level layers
    (bathroom furniture keeps working as today).
R4. **FOC and upgrades are catalogue products, not text.** A FOC is a combo part marked free
    (new column `product_combo_parts.is_free`); an upgrade is a part marked upgrade with its
    top-up amount (exists). `free_items` text stays readable for old combos and is shown as
    "FOC (text, not linked)" in the combo card until replaced. Catalogue-only codes: a FOC code
    must resolve to a product.
R5. **Prices.** Combo SP ("RM 949 NETT"), per-option SP and top-up amount are stored on the
    combo (columns exist: `product_combos.sell_price`, `product_combo_parts.sell_price`,
    `topup_amount`). A combo line never prints a sum of its parts: with no combo SP, no picked
    option SP and no typed line price, the price slot prints nothing and Submit refuses the line
    ("No combo price. Enter the selling price or set it on the combo."). An ala carte line is
    unchanged. Top-up prints "TOP UP RM 150, UPGRADE TO SRTKT71SS".
R6. **Combo info line.** A new slot "Combo codes" prints the full codes joined with "+", the
    open group as "(A / B / C)": `SRTKS7061+SRTKT1862SS`.
R7. **Re-seed combos from the current flyers, Cabana included.** A script reads each current
    flyer PDF (promotion attachments with an end date on or after today) page by page through
    the existing AI document read (semantic, no regex, 28 Oct ruling), returns combos (host,
    parts, choice groups, FOC, upgrades, prices) per page, resolves every code through the one
    product resolver, and writes a review report: one row per combo with status `new`,
    `matches`, `differs` (what differs), `unsure` (why) and the flyer page. Nothing is written
    until the owner approves the report; then `--apply` loads it through `ProductComboService`,
    prices included. Existing combos are updated in place; a combo the flyer no longer shows is
    reported, never deleted.
R8. **Templates.** Ship three combo templates built on the component list: Big 105 x 148 sink
    combo (1..5 taps), Big 105 x 148 basin combo (basin + tap + FOC), and the bathroom furniture
    set; plus a Small 59 x 29 single-product template. The seeded `sink-combo` template's three
    unbound tap blocks (which print the host sink three times) are replaced by one component list.
R9. **Gaps report.** The re-seed report also lists every combo product with no tag description,
    no picture or no barcode, per brand, so marketing can close them before printing.

### Examples (real codes from the reference PDF and dev)

E1. Sink + taps, choose one: SRTKS7061 + SRTKT1862SS, FOC as on the flyer, SP RM 849 NETT.
    Component list: [SRTKS7061 picture/code/description] + [SRTKT1862SS ...] OR [the other taps of
    the group], FOC block(s), price "RM 849 NETT". Today on dev: combo and FOC match, SP missing
    (prints the sum), SRTKT71SS stored as a choice where the flyer has "+150 top up": the re-seed
    report lists it as `differs`.
E2. Basin + tap + FOC: SRTWB1419-BL + SRTWT7449-BL / -RG, FOC SRTW5102-BL. Component list: basin,
    "+", tap in two finishes "OR", "FOC" block with SRTW5102-BL's picture. Today: no combo at all
    (re-seed reports `new`).
E3. Five-tap sink: *(dev data pending: largest tap group)*. Five cells across the 105 mm box,
    about 19 mm each; descriptions cut with an ellipsis at the floor size.
E4. Top-up: SRTKS7061 with SRTKT71SS: "TOP UP RM 150, UPGRADE TO SRTKT71SS" with SRTKT71SS's
    picture in its own block.
E5. Bathroom furniture set: SRTBF11829 + SRTMCB8083-BL + SRTWT6203-GM, SP RM 2099. Combo-level
    picture and description as today, price from the combo SP once the re-seed sets it (today it
    is only in an expired promotion, so the tag prints the sum).

### Edge cases

- A part with no picture: its cell shows the code on a blank tile, never the host's picture.
- More than 5 items in one list: cells keep shrinking to the floor; past 8 the layer prints the
  first 7 and "+N more" and the request flags the line.
- A choice group the salesperson picked: the list shows only the pick (as `combo_choices` does).
- Cabana (no system SP): combo SP comes only from the flyer or a typed price (R5 refusal applies).
- An expired flyer: combos stay; their prices are not changed by the re-seed of a newer flyer
  unless that flyer shows the same combo.

### Questions (each with a recommendation)

Q1. A sink with 2..5 tap choices: one tag showing all taps side by side, or one tag per tap
    (today's auto-split)? Recommend: one tag with all taps, because that is how the reference
    PDF and the flyer print it.
Q2. A combo line with no combo price: refuse Submit (R5), or print the summed LP with no NETT?
    Recommend: refuse Submit, because a wrong figure on a shelf tag is the worst failure.
Q3. FOC: store as combo parts marked free (R4) and retire the free-text field once the re-seed
    has linked them? Recommend: yes, because FOC needs a picture and a catalogue code.
Q4. Re-seed when a flyer's combo differs from the stored one (SRTKS2432's tap group): update the
    stored combo to the current flyer after your report approval, or keep both? Recommend: update
    to the current flyer, listed as `differs` in the report you approve.
Q5. Tag description and barcode gaps: where should the missing text and barcodes come from?
    Recommend: description proposed from the flyer read into the same review report (you approve);
    barcodes reported only until you name a source (supplier list or AutoCount).
