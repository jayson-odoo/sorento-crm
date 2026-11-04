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

*(drafting; posted as one owner ask once the dev data is in)*
