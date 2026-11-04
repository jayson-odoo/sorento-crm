# CARD: price tags render every product and combo correctly (PRICETAG-COMBO-RENDER, 4 Nov)

Behaviour card. Read of `origin/main` 6795425a. Owner goal (4 Nov): the price tag shows every
product and every combo correctly; a sink combo with 1..5 taps and a basin + tap combo need each
tap's own picture and description, not one combo-level picture and paragraph.

Out of scope (owner): submit/approve lead times, deadlines, SOP checks.

Owner answers 4 Nov ~20:55 MYT (card v1): one template per tap count, salesperson picks the
combo then WHICH taps; a combo with no SP behaves like a product with no SP (salesperson types
it); free items, certificates and logos are static template assets; a flyer that differs updates
the combo record; tag description and barcode data are complete in production (out of scope);
small and DIY tags are fine (out of scope).

Owner Lavish note on mock v4 (4 Nov): "this is kitchen sink only ... make this more flexible and
general". So nothing below is sink- or tap-specific: the combo record names its own groups, a
template points at positions in the combo, and its needs are read from its layers (R1-R3).

Existing rulings this card keeps: no Submit (Approve / Escalate / Save Draft, #2101); LP or SP
per line, LP never typed, SP typed only with no promotion, no minimum price on tags (#2158);
Cabana has no selling price (#2104); combos are saved catalogue records, never made on the fly.

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
| 14 | Combo seeded from flyer | PARTLY | 169 combos on dev, 162 from the 1 Nov flyer import, SRT only, no prices; Cabana hosts never imported; CKS7306+CB1520SS-DIY, KS6645-NL+CB1530SS-BL (system code CB1530SS-BL-DIY), SRTWB1419-BL+SRTWT7449 have no combo; SRTKS2432 has a different tap group to the current PDF (crew findings). Flyer reading extracts codes per page, not combos (`app/services/dealer_kit/flyer_reading_service.py`). | |

Canvas, preview and PDF agree today: text breaks once in `textLayerLines` for both surfaces
(`lib/dealer-kit/text-layout.ts:1-14`) and the print page resolves through the same
`layerText` / `resolveSlotText` (`app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer.tsx:33-36`).
Any new layer must keep that single path.

## 2. Behaviour card (v2, after the owner's answers)

### Rules

R1. **No combo types; the combo record says what it is made of.** A combo (existing Combos card,
    `ProductCombosSection.tsx`) is: a main product, its fixed parts (part with no choice group),
    its choice groups (parts sharing a group name the combo itself gives: "Kitchen tap", "Tap
    colour", "Basin"), and its upgrades (part ticked Upgrade, with a top-up). Nothing in the code
    knows "sink" or "tap"; the names on tags and pickers are the combo's own group names.
R2. **A template layer points at a position in the combo**, through the designer's existing
    "Product" select (`InspectorPanel.tsx` SubjectInspector): "Main product", "Fixed part n",
    "<group n>, pick k", "Upgrade n". Groups and fixed parts are numbered in the order the Combos
    card lists them. With a combo previewed, the select shows that combo's own names and codes
    ("Kitchen tap, pick 2: SRTKT1863SS"); with none, "Choice group 1, pick 2". Any layer kind
    can take it (picture, text, price), so one template can draw any shape. Old templates keep
    `subjectPart` and print as today.
R3. **A template's needs are read from its own layers** ("2 fixed parts, 3 from choice group 1,
    upgrade 1"); no type column. They show where a person decides:
    - on the combo's template picker (`ComboTemplatesPicker.tsx`), each template's description
      reads its needs in THIS combo's names ("105 x 148 mm. Needs 3 from Kitchen tap"), and a
      template the combo cannot fill is listed disabled with the reason ("Needs 3 from choice
      group 1; Kitchen tap has 2");
    - on the request line's Template select, the same description.
R3b. **The salesperson picks per group, exactly what the template needs.** The request line
    already shows one row per choice group, labelled with the combo's group name, and fixed parts
    as plain rows (`PriceTagLinesTable.tsx` PartRow). A group the template needs 1 from keeps
    today's single select; a group it needs k >= 2 from uses the existing `SearchableMultiSelect`
    with one new prop `max` (hides "Select all", disables the rest at k), pick order = print
    order, placeholder "Pick 3". The hint row names the group: "Kitchen tap: pick 1 more." and
    Approve's existing reason says the same. A group the template does not use stays as today.
    Stored as resolved line parts sharing the group's role (`price_tag_request_line_parts`); no
    new table.
R4. **Each pointed-at product prints its own picture, full code, tag description and its own LP**
    from the product master (owner Q-B, 4 Nov). A position the line has not filled prints an
    empty tile, never the main product (today a missing index falls back to the host,
    `product-block.ts:220-226`).
R5. **Combo price, never calculated** (owner Q-A, 4 Nov). The tag's combo price is the combo's
    stored price or nothing; the sum of parts is never printed, on LP or SP lines.
    - SP line, combo with no stored SP: behaves like a product with no SP; the salesperson types
      it in the existing Selling price cell (#2158). Untyped: the cell and the tag stay empty and
      Approve is off.
    - LP line, combo with no stored LP: the List price cell and the tag's price stay empty
      (LP is never typed); Approve is off with "No combo list price for line 1. Escalate it to
      marketing." beside it; Escalate stays.
    Today both fall back to the sum (`tag_data_service.py:853-883`, `pricing.py:722-723`); that
    fallback is removed for combo lines only. Ala carte lines are unchanged.
R6. **Free items, certificates, logos are template assets** the designer places (existing image
    asset layers). No FOC modelling; `product_combos.free_items` text is left as it is.
R7. **Top-up.** Unchanged in storage (`is_upgrade`, `topup_amount`). Prints in the reference
    wording "TOP UP RM 150, UPGRADE TO SRTKT71SS"; a template may also place the upgrade's
    picture with a subject "Upgrade k".
R8. **Combo codes line.** A slot "Combo codes" prints the full codes joined with "+":
    `SRTKS7061+SRTKT1862SS+SRTKT1863SS+SRTKT1871SS` for a 3-tap tag.
R9. **How we get every combo: re-seed from the current flyers, Cabana included.** A script reads
    each current flyer PDF page through the existing AI document read (semantic, 28 Oct ruling)
    and returns, per combo on the page: the main product, fixed parts, choice groups WITH their
    name taken from the flyer's own wording (a "choose one of these taps" block becomes group
    "Kitchen tap"; the same code in two finishes becomes group "Tap colour"), upgrades with
    top-up, and prices. Every code resolves through the one product resolver; a discontinued
    product is listed, not loaded silently. The review report shows each combo's full shape
    (main, fixed, groups with names, upgrades, prices), its status (`new`, `matches`, `differs`
    with what differs, `unsure` with why) and the flyer page. After the owner approves it,
    `--apply` writes through `ProductComboService`: a combo that differs from the flyer is
    **updated to the flyer** (owner Q4), and links every template whose needs the combo can fill
    (R3). A combo the flyer no longer shows is reported, never deleted. Group names stay editable
    on the Combos card afterwards. **Cabana: no SP, option SP or top-up is ever written** (#2104);
    a flyer price read for one is listed as "not loaded".
R10. **Seeded templates, one per PDF shape**, all 105 x 148 on the R2 positions: "Sink + 1 tap"
    to "Sink + 5 taps" (1..5 from group 1, upgrade 1), "Basin + tap" and "Basin + tap, 2
    colours" (1 or 2 from group 1, free item asset placeholder), "Furniture set, 3 parts" (main +
    fixed 1 + fixed 2). The seeded "Kitchen Sink - Combo" (three blocks with no subject that print
    the sink three times, `scripts/tag_template_seed_docs.py:604-609`) becomes "Sink + 3 taps".
    Names are plain text a designer can change; nothing reads them.
R11. **One renderer.** The new positions resolve inside `subjectOf`, which the canvas, the
    preview and the PDF print page already share, so the three cannot disagree.

Out of scope (owner): small and DIY tags, tag description and barcode gaps, lead times.

### Examples (every combo shape in the reference PDF; exact system codes)

E1. Kitchen sink + 1..5 taps: SRTKS7061, group "Kitchen tap" (SRTKT1862SS and others), template
    "Sink + 3 taps" needs 3 from group 1. Line: one "Kitchen tap" multi-select, pick 3.
E2. Wash basin + tap + free item: SRTWB1419-BL + one tap; the free pop-up waste and any logo are
    picture assets on the template (R6). One option in the group resolves on the spot (today's
    D17), so the line shows the tap as a plain row; nothing to pick.
E3. Colour choice: SRTWB1419-BL with group "Tap colour" = SRTWT7449-BL / SRTWT7449-RG. Template
    "Basin + tap, 2 colours" needs 2 from group 1 (both colours side by side); template "Basin +
    tap" needs 1 (single select, dealer's colour).
E4. Bathroom furniture set: SRTBF11829 + fixed parts SRTMCB8083-BL, SRTWT6203-GM. Template
    "Furniture set, 3 parts" uses Main product, Fixed part 1, Fixed part 2 (or the combo picture,
    as today). Line: two plain part rows; nothing to pick. Price from the combo or typed (R5).
E5. Top-up: SRTKS7061 with upgrade SRTKT71SS, top-up RM 150: "TOP UP RM 150, UPGRADE TO
    SRTKT71SS"; a template may place "Upgrade 1"'s picture. Line: today's "No upgrade" select.

### Edge cases

- A part removed from the combo after a request picked it: the request keeps it (a request is a
  record, AC-S1-5); the picker shows it as "No longer in this combo".
- A template whose needs the combo cannot fill (more picks than the group has, a fixed part it
  lacks) is listed disabled with the reason on the combo's template picker, and never offered
  on the request line.
- Two combos whose groups are in a different order: the template's "choice group 1" is the
  FIRST group on each combo's Combos card; the needs text shows each combo's own name, so a
  wrong order is visible on the picker before any tag is drawn.
- The same tap picked twice: refused by the picker.
- A discontinued tap in a combo's option group (`products.is_discontinued`, `app/models/product.py:354`;
  for example SRTWT5831-BL, CB890SS): the tap picker lists it disabled with a "Discontinued"
  badge (the multi-select's existing option `disabled` + `badgeText`), never offered silently and
  never hidden; a draft that already picked it keeps it and Approve is off with "SRTWT5831-BL is
  discontinued. Pick another tap or escalate it to marketing." The re-seed report lists every
  discontinued product a combo still names.
- Examples and tests use exact system codes only (crew tally 4 Nov: SRTMCB8083-BL, not the
  PDF's SRTMR8083-BL / SRTMCB80803-BL typos; CB1530SS-BL-DIY, not the discontinued CB1530SS-BL).
- A set's printed LP is never derived (crew tally: SRTBF11829 set LP 2,715 matches no sum of its
  component LPs), which is why R5 never sums.
- Cabana combo on an SP line: typed SP only, as for any Cabana product.

### Questions

None open. Q-A and Q-B answered 4 Nov (R4, R5). Mock v4 shows the change inside the existing
request form and template designer (owner Lavish note: no new components).
