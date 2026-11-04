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
| 14 | Combo seeded from flyer | PARTLY | 169 combos on dev, 162 from the 1 Nov flyer import, SRT only, no prices; Cabana hosts never imported; CKS7306+CB1520SS-DIY, KS6645-NL+CB1530SS-BL, SRTWB1419-BL+SRTWT7449 have no combo; SRTKS2432 has a different tap group to the current PDF (crew findings). Flyer reading extracts codes per page, not combos (`app/services/dealer_kit/flyer_reading_service.py`). | |

Canvas, preview and PDF agree today: text breaks once in `textLayerLines` for both surfaces
(`lib/dealer-kit/text-layout.ts:1-14`) and the print page resolves through the same
`layerText` / `resolveSlotText` (`app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer.tsx:33-36`).
Any new layer must keep that single path.

## 2. Behaviour card (v2, after the owner's answers)

### Rules

R1. **One template per tap count.** A sink (or basin) combo template is built for a fixed number
    of taps: "Sink combo, 2 taps", "3 taps", "4 taps", "5 taps". Each tap position on it is made of
    ordinary layers (picture, code, tag description, price) whose subject is **"Picked option k"**
    (k = 1..N), a new subject beside today's fixed `subjectPart` index
    (`lib/dealer-kit/product-block.ts:200-227`). The template's tap count N is read from its own
    layers (the highest k used); no new column. The sink, the combo name, the combo codes line and
    the price are ordinary layers as today.
R2. **Templates are linked to combos** through the existing combo template link
    (`dealer_kit.combo_tag_template`, `app/models/dealer_kit.py:846-875`). A combo can print with
    every N-tap template up to the size of its option group (a combo with 3 taps to choose from
    links the 1, 2 and 3 tap templates).
R3. **Salesperson picks the combo, the template, then exactly N taps**, in the existing line row
    (`components/dealer-kit/PriceTagLinesTable.tsx`): the Package select and the Template select
    are unchanged (the template's option description adds "3 taps"); the tap group's part row
    (PartRow :235-331) swaps its single `SearchableSelect` for the existing
    `SearchableMultiSelect` when N >= 2, with one new prop `max` (hides "Select all", disables
    the rest once N are picked). Pick order = print order. The hint row under it reads "Pick 1
    more tap for this template."; Approve's existing reason line (`approveBlockedReason`,
    `PriceTagRequestForm.tsx:1485`) says the same until N are picked. A smaller template keeps
    the first picks and drops the rest. Stored as resolved line parts sharing the group's role
    (`price_tag_request_line_parts`, `app/models/price_tag.py:299-351`); no new table.
R4. **Each tap slot prints that tap's own picture, full code, tag description and its own LP**
    from the product master (owner Q-B, 4 Nov). A picked tap with no picture shows an empty
    tile, never the sink's picture (today a missing index falls back to the host,
    `product-block.ts:220-226`; the new subject never does).
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
R9. **Re-seed combos from the current flyers, Cabana included.** A script reads each current
    flyer PDF page through the existing AI document read (semantic, 28 Oct ruling), returns
    combos (host, parts, option groups, top-ups, prices), resolves every code through the one
    product resolver and writes a review report (`new`, `matches`, `differs` with what differs,
    `unsure` with why, flyer page). After the owner approves it, `--apply` writes through
    `ProductComboService`: a combo that differs from the flyer is **updated to the flyer** (owner
    Q4), prices included, and linked to the N-tap templates its option group allows (R2). A combo
    the flyer no longer shows is reported, never deleted. **Cabana: no SP, option SP or top-up is
    ever written** (#2104); a flyer price read for one is listed as "not loaded".
R10. **The seeded "Kitchen Sink - Combo" template** (three tap blocks with no subject, which
    print the sink three times, `scripts/tag_template_seed_docs.py:604-609`) is rebuilt as the
    3-tap template on R1's subject. The 2, 4 and 5 tap templates are new seeds on the same
    layout grid (105 x 148).
R11. **One renderer.** The new subject resolves inside `subjectOf`, which the canvas, the
    preview and the PDF print page already share, so the three cannot disagree.

Out of scope (owner): small and DIY tags, tag description and barcode gaps, lead times.

### Examples

E1. SRTKS7061, 3-tap template, salesperson picks SRTKT1862SS, SRTKT1863SS, SRTKT1871SS: sink
    on the left, three tap tiles each with its own picture, code, description and LP, SP RM 849
    NETT (combo SP once the re-seed sets it; typed by the salesperson until then).
E2. Same combo, 2-tap template, picks SRTKT1863SS and SRTKT1871SS (taps 2 and 3): two tiles.
E3. Five-tap sink: 5-tap template, all five picked; tiles in two rows (3 + 2).
E4. Basin + tap: SRTWB1419-BL with SRTWT7449-BL and -RG on the 2-tap basin template; the free
    pop-up waste is a picture asset the designer placed (R6). Today no combo exists: re-seed `new`.
E5. Top-up: SRTKS7061 with SRTKT71SS: "TOP UP RM 150, UPGRADE TO SRTKT71SS" plus its picture.
E6. Bathroom furniture SRTBF11829 + SRTMCB8083-BL + SRTWT6203-GM: unchanged layout (combo-level
    picture and description); SP RM 2,099 from the combo once re-seeded, typed until then.

### Edge cases

- A tap removed from the combo after a request picked it: the request keeps it (a request is a
  record, AC-S1-5); the picker shows it as "No longer in this combo".
- A template whose N is larger than the combo's option group is not offered for that combo.
- The same tap picked twice: refused by the picker.
- Cabana combo on an SP line: typed SP only, as for any Cabana product.

### Questions

None open. Q-A and Q-B answered 4 Nov (R4, R5). Mock v4 shows the change inside the existing
request form and template designer (owner Lavish note: no new components).
