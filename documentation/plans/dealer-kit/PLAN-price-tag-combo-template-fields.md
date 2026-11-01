# PLAN: price tag combos carry their own picture, description and options, pullable into templates

Status: draft, behaviour card + mock go to the owner first; nothing is built until the owner OKs both. Track: full (size L, migration).
Lane: PRICETAG-COMBO, branch `crew/pricetag-combo`, one PR for the feature, seed data stays outside this repo.
UAC: written after the owner's answers, as `price-tag-combo-template-fields-acceptance-criteria.md` beside this file.
Predecessors: `PLAN-price-tag-combos.md` (#913), `PLAN-price-tag-r10.md` (S4 description, S5 combo image, #1083), `_archive/dealer-kit/PLAN-price-tag-line-promo-combo-subject.md` (#948).

## Journey (owner, 1 Nov 2026)

A dealer submits a combo. The tag should come out with the combo's own photo and the combo's own description, straight
away, on a template marketing designed once. Today marketing can define a combo but cannot design a template that does this.

## Why it fails today (measured on origin/main 670a4c97f6)

Description, no path at all:
- `product_combos` has no description column (`app/models/product_combo.py:53-72`).
- The resolver has no combo branch: description always comes from the host product (`app/services/dealer_kit/tag_data_service.py:351`, `:1068`). One column per host (`app/models/product.py:321`) against many combos per host.
- Nothing to bind: no combo slot (`lib/dealer-kit/tag-template-types.ts:25-40`), no combo merge token (`lib/dealer-kit/merge-fields.ts:42`), no combo fields on the line payload.

Image, a path exists but is conditional and falls back silently:
- `_combo_lead_image` (`tag_data_service.py:1007-1022`) only reorders the host's gallery when the line has a `combo_id` and the combo has a picture; otherwise the host's photo prints with no warning.
- `combo_id` stays empty when a host has more than one combo and the dealer picks none (`hooks/usePriceTagLineEditor.ts:181`); submit still passes.
- A layer with an explicit photo source beats the combo cover (`lib/dealer-kit/product-block.ts:354-356`).

Authoring, why the template cannot be designed:
- The template editor previews a product or a set only (`tag-templates/components/useTagBindings.ts:97-122`); there is no combo input, and in that preview the combo picture ranks LAST (`app/services/dealer_kit/product_images.py:39-42`). The author sees host photo and host text.
- Auto pick looks at line type and code prefix only (`lib/dealer-kit/line-family.ts:28-35`, `lib/dealer-kit/request-tags.ts:84-96`).

Options and price:
- OR choices exist (`product_combo_parts.choice_group`). Free items and top-ups have no column anywhere.
- A combo has no price (owner ruling 14 Sep, `PLAN-price-tag-combos.md`): the tag sums host + parts through the promotion engine (`tag_data_service.py:846-866`). The flyer prints a combo price.

Measured on the 28 Oct prod copy, extracted by crew (figures stay private; counts only here):
- 7 combos, none with a picture; 13 parts; 11 of 208 request lines carry a combo. The picture path has never fired on this copy.
- 9 templates: 8 `ala_carte`, 1 `shower`. No `sink_combo` or `furniture_set` template exists, so a combo line falls to the first `ala_carte` (`lib/dealer-kit/request-tags.ts:84-96`). One template binds the product description.
- With the flyer promotion applied through the real offer rule, the tag's summed price matches the flyer's printed price on 0 of 75 bathroom combos and 3 of 155 sink + tap pairs. Printed list price matches the sum of part list prices on 0 of 75. Caveat: list prices are today's, not those at flyer time.
- The flyer promotion ended 31 May 2026. Of 18 bathroom hosts with an active end-user offer today, 16 differ from the flyer's figure; 37 have no active offer. Flyer prices are not current.
- Promotions store a package price on whichever code marketing chose: host, tap, basin or waste, and parts at RM 0. `_offer_worth_showing` (`app/services/dealer_kit/pricing.py:633-636`) drops a 0 or at-or-above-list offer and `_offer_or_list` (`tag_data_service.py:501-510`) then charges the list price, so a free part in a combo promotion adds its list price to the tag.
- 257 of 273 flyer codes exist as products. 5 hosts and 29 further combos reference a missing code. 264 of 314 free item mentions have no printed code.
- 23 of 135 flyer hosts carry more than one combo, and one offer per host cannot price them apart.

## Proposal (to be confirmed by the card)

Additive only. Existing templates and approved tags print exactly as before.

| Element | Change | Reuses |
| --- | --- | --- |
| Combo picture | no schema change, direct binding | `product_combos.image_attachment_id`, `ComboImageControl`, `product_combo_service.upload_image` |
| Combo description | `product_combos.description` TEXT | `PriceTagDescriptionBlock` editor, `renderPriceTagDescription` |
| Combo title | none, `name` holds the printed title | existing `name` column and `AddComboModal` |
| OR choices | none | `choice_group`, Split / Pick one on the tag |
| Free items | `product_combos.free_items` TEXT, copied to the line | `price_tag_request_lines.included_accessories` and its slot |
| Top-ups | `product_combo_parts.topup_amount` NUMERIC | part rows, Sold with card |
| Combo price | decided by the owner, see the card | `manual_sell_price` precedent, tag override stays last |
| Template fields | new Combo group in the Field select and Insert field dialog | `SlotBinding`, `merge-fields.ts`, `InsertFieldDialog` |
| Designer preview | Preview combo picker | `useTagBindings`, `product_tag_data` |
| Later data changes | combo fields join the tag data diff | `apply_auto_data_updates`, red dot, roll back |
| Seed | `scripts/import_product_combos.py`, dry run by default | `scripts/import_price_tag_descriptions.py` shape, `product_combo_service` |

Not built, with the trigger that would justify it:
- Per-combo template pointer: when one family needs two layouts that a Field cannot express.
- Screen for importing combos: next season's flyer.
- Combo code column: when something other than a tag needs to look a combo up by code.

## Seed

Real business data. `combos-seed.json` and the photo crops stay in the crew's private state folder, never in this public repo. This PR ships only the import script and a synthetic test fixture.

## Open

Owner answers on the card, then UAC, tickets, red tests, build.
