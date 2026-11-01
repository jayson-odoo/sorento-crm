# UAC: price tag combos carry their own picture, description and options, pullable into templates

Plan: `PLAN-price-tag-combo-template-fields.md`. Journey: a dealer submits a combo; the tag comes out with the combo's own photo and description, on a template designed once.

Owner rulings, 1 Nov 2026: "1a 2a 3a 4a 5b"; "reuse as much thing as we have with combo now as much as possible, just extend from there". Mock approved.

All figures below are synthetic. Real flyer data never enters this repo.

## Extend, never replace

- AC-0.1 No new combo table. `product_combos` and `product_combo_parts` gain columns only, all nullable or defaulted. Migration id is at most 32 characters and `alembic heads` shows one head.
- AC-0.2 A combo with no new field set behaves exactly as today in every read, and every existing combo and tag test stays green, except the tests that pin the one-tag-per-option rule on a line with a combo (AC-3.1), which are flipped.
- AC-0.3 Every existing slot and merge token resolves as today. An existing template doc renders unchanged.
- AC-0.4 A combo stays invisible to the chatbot and is never a product set, a code or a quote line.

## 1. Combo fields

- AC-1.1 `product_combos` gains `description` TEXT, `free_items` TEXT, `list_price` NUMERIC(12,2), `sell_price` NUMERIC(12,2). `product_combo_parts` gains `sell_price` NUMERIC(12,2), `topup_amount` NUMERIC(12,2), `is_upgrade` BOOLEAN NOT NULL DEFAULT false.
- AC-1.2 The existing combo PATCH accepts `description`, `free_items`, `list_price`, `sell_price`. The existing part PATCH accepts `sell_price`, `topup_amount`, `is_upgrade`. Omitted = left alone, explicit null = cleared (the `model_fields_set` rule the part PATCH already has). The combo list response returns all of them.
- AC-1.3 A negative price or top-up answers 422. RM 0 is allowed on a top-up.
- AC-1.4 Both writes keep today's guards: `master_data.products.edit`, host resolved under the caller's company scope, 404 for a host in another company.
- AC-1.5 Edits are recorded on the product's Audit Trail, as combo edits are today.

## 2. Tag data and price

- AC-2.1 A line with a combo resolves a `combo` object on its tag data: `{id, name, description, free_items, choices: [{role, options: [{product_id, code, description, list_price, sell_price, picked}]}], upgrades: [{product_id, code, description, topup_amount, picked}]}`. A line with no combo resolves `combo: null`. `description` on an option is the product's description text, falling back to its product name (on real data `product_name` equals the code).
- AC-2.2 `list_price` on an option is that product's list price from the existing price engine; `sell_price` is the part row's own `sell_price`, null when blank. `picked` is true when the dealer's line part or the tag's `choices` names that product.
- AC-2.3 `included_accessories` on tag data: the line's own text wins; when blank it is the combo's `free_items`.
- AC-2.4 Price precedence on a tag, highest first: tag override, line manual price, then combo price, then today's sum.
  - Combo list price: `combo.list_price` when set, else today's sum.
  - Combo sell price: the picked option's `sell_price` when set; else `combo.sell_price` when set; else today's sum.
  - A picked upgrade with `topup_amount`, on a combo price: that price plus the top-up. A picked upgrade with a blank top-up: the price alone.
  - A picked upgrade on a combo with no sell price: today's sum, counting the upgrade like any resolved part.
- AC-2.5 Nothing picked, some option has its own `sell_price`, and `combo.sell_price` is blank: tag `sell_price` is null, because each option prints its own price.
- AC-2.6 The figure agrees everywhere: tag data, `line_pricing`, and the CRM and portal product lookups answer the same combo price for the same line.
- AC-2.7 On a combo line a part whose row in the line's promotion is RM 0 adds RM 0 to today's sum, instead of its list price. A part with no row adds its list price as today. A positive offer behaves as today. A host listed at RM 0 is not free: as today.
- AC-2.8 Later edits follow the existing rules: a tag in `designing` or `changes_requested` picks up a changed combo description, free items or price through `apply_auto_data_updates`, with its change note; an approved (pinned) tag keeps its figures and text; the cover picture stays live as today. A payload pinned before this lane has no `combo` key and renders as `combo: null`.
- AC-2.9 The export payload for the PDF carries `combo`, so the PDF prints what the designer shows.

## 3. One tag per combo line

- AC-3.1 A line with a `combo_id` and open choice groups mints ONE tag with empty `choices` at submit, whatever the number of groups or options.
- AC-3.2 A dealer pick on the line resolves that part as today; the tag then shows only that option (AC-4.5).
- AC-3.5 Upgrades reach the portal line as one open `Upgrade` row of candidates, even with a single candidate, never as a fixed part. Left open they add nothing to the price and print under Combo Top-ups. They are never named in a `Missing:` warning. The dealer picks one in that row.
- AC-3.3 A line with open groups and NO `combo_id` keeps today's one tag per combination.
- AC-3.4 A surviving line whose carried tags already match today's one-per-combination set keeps them untouched on save, so requests in flight do not collapse. (Split and Pick one left the product before this lane, D6, so marketing cannot narrow a one-tag line after submit; the dealer's pick is the only narrowing. Reported to the owner.)

## 4. Template fields

- AC-4.1 `SlotBinding` gains `combo_image`, `combo_name`, `combo_description`, `combo_choices`, `combo_topups`. The Inspector field list shows them in a Combo group above the existing options, which keep their labels and order. The backend slot list in `schemas/price_tag.py` gains them too.
- AC-4.2 Merge tokens `combo.name`, `combo.description`, `combo.free_items` appear in a Combo group in Insert field and resolve in text layers.
- AC-4.3 Combo Photo prints the combo's cover picture and ignores a layer's pinned photo source. No cover, or no combo: the product's primary photo.
- AC-4.4 Combo Name prints the combo's name, else the product code. Combo Description prints the combo's description, else the product's price tag description, else nothing.
- AC-4.5 Combo Choices prints plain text, one group after another: a header `ROLE: PICK ONE` (just `ROLE` when the group has one option or a pick was made), then one line per option `CODE  Description  RM 999`, the price only when that option has its own. With a pick, only the picked line prints. On a one-group combo a picked upgrade prints as the group's only line, with `+RM 100` in place of a price when it has a top-up; on a combo with more groups the groups print as usual and the picked upgrade follows in its own `UPGRADE` section.
- AC-4.6 Combo Top-ups prints a header `UPGRADE`, then one line per upgrade `CODE  Description  +RM 100`, the amount only when set. It prints nothing when the combo has no upgrades or an upgrade was picked.
- AC-4.7 On a line with no combo, Combo Choices and Combo Top-ups print nothing, and the layer shows no placeholder on the printed tag.
- AC-4.8 The canvas, the preview and the PDF print the same text for each field: they share `resolveSlotText` and its neighbours in `lib/dealer-kit/product-block.ts`.

## 5. Designer preview

- AC-5.1 The template editor shows a Preview combo `SearchableSelect`, clearable, searching combos by name or host code. Picking one previews that combo's real photo, name, description and options on the canvas.
- AC-5.2 New endpoint: `GET /api/v1/dealer-kit/tag-data/combos?query=&limit=` answers `{data: [{combo_id, name, host_product_id, host_code}]}`, bounded by `limit`, joined to the host so the company scope applies, same permission as the other tag data routes.
- AC-5.3 The existing product tag data route takes an optional `combo_id`, and the preview payload carries the same `combo` object as AC-2.1, with the list and sell price the combo would print with nothing picked. A `combo_id` that does not belong to that product answers 404. Omitted: today's response plus `combo: null`.

## 6. Combos card on the product page

- AC-6.1 The Combos card shows and edits List price, Sell price, Description, Free items per combo; each part row shows and edits Sell price if picked, Top-up and an Upgrade toggle. Same layout read-only and editing; no new page, no new modal beyond what the card has.
- AC-6.2 Upgrade rows are drawn in their own Upgrade block, after the choice groups.
- AC-6.3 Usable and not clipped at 375px and 1280px. Save and error go through the existing combo hooks with toast and `extractApiError`.
- AC-6.4 No UUIDs and no feature explanations in the UI.

## 7. Warning

- AC-7.1 Submitting a line whose combo has no picture or no description still succeeds, and `package_warning` names what is missing. Marketing sees it where package warnings show today. A line with both set adds no warning.

## 8. Import

- AC-8.1 `scripts/import_product_combos.py --file seed.json --photos DIR [--company SRT] [--apply] [--report out.csv] [--templates]`. Dry run is the default and writes nothing, photos and templates included.
- AC-8.2 Apply loads through the existing service: combo, parts, cover picture via `product_combo_service`, description and free items. Fixed components become fixed parts, `choice_groups` become parts sharing `choice_group`, `topups` become parts with `is_upgrade = true`.
- AC-8.3 No price is loaded: `lp`, `sp`, option `sp` and `topup` in the seed are ignored, so every loaded price column is NULL.
- AC-8.4 A host code with no product: that combo is not loaded and the report says `not_loaded_host_missing`. A part code with no product, or a component with no code: the part is dropped, the combo still loads, and the report lists it.
- AC-8.5 Every seed entry with a `guess` is listed in the report with that text. The report has one row per seed entry: id, status, dropped parts, guess.
- AC-8.6 Re-running changes nothing already there: no duplicate combo (host + name), a description, free items or picture already set stays, prices marketing filled stay, parts missing are added, parts present are not removed. Combos under other names are not touched.
- AC-8.7 A missing photo file is listed in the report; the combo still loads.
- AC-8.8 Host lookup is under the chosen company's scope only.
- AC-8.9 `--templates` creates and publishes two templates, `Bathroom furniture combo` (family `furniture_set`) and `Kitchen sink combo` (family `sink_combo`), layered as in the approved mock with the Combo fields. Re-running does not duplicate or overwrite them.
- AC-8.10 With those templates present, a combo line and a line with no combo on a `bf` or `ks` product both auto pick their family's template on a NEW design; a tag already designed keeps its template.
- AC-8.11 The repo holds the script and a synthetic test fixture only.

## 9. Guide

- AC-9.1 `documentation/user-guides/marketing/price-tag-packages.md` covers the new combo fields, the Combo template fields, the one tag rule and the price order, following `documentation/user-guides/SYNC.md`, with no real customer data.
