# Price tag: line-level promotion, combo subject picker, auto-split, photo tiebreak, tag size - acceptance criteria

Status: owner-reviewed 2026-09-15. Plan: `PLAN-price-tag-line-promo-combo-subject.md`.
Owner rulings recorded in chat on 15 Sep 2026 (five findings from the post-#929 prod walk-through).

## Journey

**Actor 1: salesperson on the portal, raising a price tag request.**

Arrives from the portal landing, opens the price tag form. Adds lines by
product code, as today. The system already knows each product's list price,
every active promotion the salesperson's audience may see, and each catalogue
combo's fixed parts and choice groups.

1. Picks **List price** or **Selling price** at the top of the Price section.
   One decision. The lines table gains a **List price** column at once, filled
   from the product, read only. Combo = parent + fixed parts, summed.
2. In **Selling** mode the lines table gains two more columns. **Promotion** is
   pre-filled per line with the best active promotion covering that line's
   products (lowest tag total wins); the salesperson changes it only when the
   pre-fill is wrong, from a list scoped to promotions covering that line.
   **Selling price** is computed from the chosen promotion and shown read
   only. A line with no covering promotion shows the promotion blank, the
   selling price blank, and a **Type a price** input, so the salesperson can
   key the agreed figure by hand. A line with neither prints at list price.
   No promotion is chosen for the request as a whole.
3. Applies a combo to a line. A choice group (say "Kitchen Tap", any of two)
   shows its candidates with each candidate's price beside its code, under
   the line's promotion when one applies. The salesperson may pick one or
   leave it as "Not sure, any of N". No further decision.
4. Submits. Nothing else changes for the salesperson.

At the end the salesperson holds a submitted request whose every line carries
its own price basis. Marketing is notified as today.

**Actor 2: marketing designer in the CRM.**

Opens the request from the sidebar list. The system already turned every
unresolved choice group into one tag per candidate at submit, so the LINES
rail never shows "Open" and never asks Split or Pick one. Each tag row reads
`1a SRTKT1871SS` with its LP or SP.

5. Picks a tag. The LINES rail fills the top of the left panel; TAG SIZE sits
   at its foot, directly above the splitter and the LAYERS panel.
6. On a combo tag, every product-bound layer (product image slot, code, name,
   specs, price badge, barcode, a text layer with `{{product.*}}` tokens)
   offers a **Product** picker listing the tag's products: the parent first,
   then each part in package order. Default is the parent, so an existing
   design opens unchanged. A single-product tag shows no picker.
7. Needs a line's price basis changed (wrong promotion, agreed price). Opens
   the request detail, changes the line's Promotion or manual selling price in
   the lines table. The tags re-resolve; a pinned tag shows the usual
   data-change banner.
8. Exports. The PDF resolves the product photo and the subject product exactly
   as the canvas did.

**Stakeholders told automatically:** nothing new. Existing submit and status
notifications stand.

## Phase 1 - frontend against mocks

### S1 Price section: line-level promotion and selling price [FE]

- **AC-S1-1** Given the form in List mode, When a product line is added, Then
  the lines table shows a List price column with that product's list price,
  read only, and no Promotion or Selling price column.
- **AC-S1-2** Given a combo applied to a line in List mode, Then the List
  price cell reads parent + every fixed part, summed; an unresolved choice
  group adds nothing and the cell carries a "+ option" hint.
- **AC-S1-3** Given the form switches to Selling mode, Then each line gains a
  Promotion select (searchable, clearable) and a Selling price cell, and the
  request-level Promotion select no longer exists on the page.
- **AC-S1-4** Given Selling mode and a line whose product is covered by at
  least one active promotion, Then Promotion is pre-filled with the one that
  yields the lowest tag total, and Selling price shows that total.
- **AC-S1-5** Given a line's Promotion select is opened, Then its options are
  only active promotions covering at least one product on that line, each
  labelled with the promotion description and the resulting tag total.
- **AC-S1-6** Given Selling mode and a line with no covering promotion, Then
  Promotion is blank, Selling price is blank, and a numeric "Type a price"
  input appears in the Selling price cell; a value typed there is the line's
  selling price.
- **AC-S1-7** Given a line has a manual selling price and the salesperson then
  picks a promotion, Then the manual value is cleared and the computed total
  shows; clearing the promotion restores the manual input, empty.
- **AC-S1-8** Given a combo line under a promotion that covers the parent but
  not a part, Then Selling price = parent offer + that part's list price, and
  the cell's title reads which parts are at list.
- **AC-S1-9** Given the form switches back to List mode, Then Promotion and
  Selling price columns disappear and their values are kept in state, so
  switching back restores them.
- **AC-S1-10** Given the read-only view of a submitted request, Then each line
  shows List price, and in Selling mode its Promotion and Selling price.
- **AC-S1-11** The lines table stays usable at 375px: List price and Selling
  price cells wrap under the item on narrow width, no horizontal scroll of the
  page.

### S2 Choice-group candidates with prices [FE]

- **AC-S2-1** Given a combo with a choice group is applied to a line, Then each
  candidate option in the part row reads `CODE  RM x` where x is that
  candidate's list price in List mode, or its price under the line's
  promotion (offer, else list) in Selling mode.
- **AC-S2-2** Given the line's promotion changes, Then the candidate prices
  re-render without a page reload.
- **AC-S2-3** The "Marketing will prepare one tag per option" copy stays, once
  per line, under the last unresolved row.

### S3 Designer rail: no Split / Pick one; TAG SIZE at the foot [FE]

- **AC-S3-1** Given a request whose line had an unresolved choice group at
  submit, When the designer opens, Then the LINES rail shows one tag row per
  candidate (`1a CODE`, `1b CODE`), each with its own LP or SP, and no "Open"
  badge, no Split button, no Pick one select anywhere in the rail.
- **AC-S3-2** Given the designer, Then the top left panel holds LINES filling
  all available height (its list scrolls internally) and TAG SIZE pinned at
  the panel's foot, directly above the resize handle; the LAYERS panel is
  unchanged below the handle.
- **AC-S3-3** Given the panel is resized by the handle, Then TAG SIZE stays at
  the foot and LINES grows or shrinks; no dead space between them.
- **AC-S3-4** Given the previous 45% cap is gone, Then a request with 12 lines
  shows at least 8 rows without scrolling at 1280x800 with the default split.

### S4 Combo subject picker on the canvas [FE]

- **AC-S4-1** Given a combo tag is selected and a product-bound layer is
  selected (product_slot, price_badge, barcode, or a text layer containing a
  `{{product.*}}` or `{{spec.*}}` token), Then the properties panel shows a
  **Product** select listing the parent first (default) then each part in
  package order, labelled by product code. A price badge's select has one
  extra first entry, **Tag total** (default), the roll-up of parent + parts.
- **AC-S4-2** Given a single-product tag, Then no Product select is shown on
  any layer.
- **AC-S4-3** Given a layer's Product is set to a part, Then the product image
  slot shows that part's photo, `{{product.code}}` / name / dimensions /
  spec_lines / `{{spec.*}}` resolve to that part, the barcode is that part's,
  and a price badge set to that part shows that part's own list price and
  offer under the line's promotion.
- **AC-S4-4** Given a layer's Product is unset, Then every token resolves
  exactly as before this change: parent product data, and for a price badge
  the whole-tag total (Tag total). A price badge set to the parent shows the
  parent's own list price and offer, not the roll-up.
- **AC-S4-5** Given a part has no photo, Then the product image slot shows its
  empty placeholder, not the parent's photo.
- **AC-S4-6** Given a tag document with a part subject is copied via "Apply to
  all" onto a tag whose line has fewer parts, Then that layer falls back to the
  parent and a toast names the layer.
- **AC-S4-7** Given a layer with a part subject, Then the LAYERS panel row
  suffixes the layer name with the part's code, so a scan of the list tells
  which product each layer draws.

### S5 CRM detail: change a line's price basis [FE]

- **AC-S5-1** Given the CRM request detail in Selling mode and the request is
  not terminal, Then the lines table shows per line a Promotion select and a
  Selling price cell with the same rules as S1 (AC-S1-4 to S1-8).
- **AC-S5-2** Given a change is made, Then it saves on change (no form submit),
  toasts, and the per-tag price rows under the line refresh.
- **AC-S5-3** Given the request is terminal (collected, cancelled), Then the
  cells are read only.
- **AC-S5-4** Given the viewer lacks `price_tag_requests.process`, Then the
  cells are read only.

## Phase 2 - backend wiring, test first

### S6 Model, migration, schema [BE]

- **AC-S6-1** `price_tag_request_lines` gains `promotion_id` (FK promotions,
  ON DELETE SET NULL, nullable) and `manual_sell_price` (Numeric(12,2),
  nullable). `price_tag_requests.promotion_id` is dropped. Migration backfills
  every line's `promotion_id` from its request's before the drop; downgrade
  restores the header column from the first line that carries one.
- **AC-S6-2** A migration test on a seeded chain proves the backfill and that
  no line loses its promotion.
- **AC-S6-3** Create and Update schemas (portal and CRM) accept per line
  `promotion_id` and `manual_sell_price`; the request-level `promotion_id` is
  rejected with 422 (extra field), and the response model carries per line
  `promotion_id`, `promotion_name`, `manual_sell_price`, `list_price`,
  `sell_price`, `sell_price_basis` (`promotion` | `manual` | `list`).
- **AC-S6-4** `manual_sell_price` is accepted only when `promotion_id` is
  null and the request is in Selling mode; otherwise 422 with a named error.
- **AC-S6-5** `promotion_id` on a line is accepted only if that promotion is
  active today (MYT), visible to the submitting audience, and covers at least
  one product on the line (parent or resolved part or any candidate);
  otherwise 422 naming the line.

### S7 Auto promotion + line pricing service [BE]

- **AC-S7-1** `POST /public/portal/lookups/line-pricing` (portal) and
  `POST /dealer-kit/price-tag-requests/line-pricing` (CRM) take
  `[{product_id, part_product_ids[], candidate_product_ids[], promotion_id?}]`
  and return per line `list_price`, `promotion_options[{id, description,
  sell_price}]` ordered lowest total first, `auto_promotion_id`, `sell_price`
  under the given or auto promotion, `parts_at_list[]`, and per candidate
  `{product_id, list_price, sell_price}`.
- **AC-S7-2** `promotion_options` contains only promotions that are active
  today in MYT, visible to the caller's audience (portal: contact access
  codes; CRM: the viewer's), and have a `PromotionProduct` row for at least
  one product on the line.
- **AC-S7-3** `sell_price` for a line = manual if set, else sum over parent +
  resolved parts of (offer under the line's promotion if worth showing, else
  list). An unresolved choice group contributes nothing.
- **AC-S7-4** `sell_price_basis` = `manual` when manual set; `promotion` when
  the line's SAVED promotion yields an offer below list on a resolved
  product; the lookup's auto pick never feeds a saved line's basis; `list`
  otherwise.
- **AC-S7-5** Each line's `show_promo_price` (existing column) is now written
  as `price_mode == 'selling' and sell_price_basis != 'list'` on every save,
  so a combo with no offer prints LP, matching a plain product.

### S8 Auto-split at submit [BE]

- **AC-S8-1** Given a line with one unresolved choice group of N candidates,
  When tags are built for that line (create, update, revise, or first design
  open), Then N tags are created, each with `choices[role] = candidate`, in
  candidate order, `open_groups` empty on every one.
- **AC-S8-2** Given two unresolved groups (N and M candidates), Then N x M
  tags, one per combination, labelled `1a`.. in order.
- **AC-S8-3** Given a line already split (tags carry choices), When the line
  is re-saved without a change to its parts, Then existing tags and their
  quantities and placements are kept, not rebuilt.
- **AC-S8-4** `POST /{request_id}/tags/{tag_id}/split` is removed;
  `PATCH .../tags/{tag_id}` rejects a `choices` key with 422. `open_groups`
  stays on the response and is always empty.
- **AC-S8-5** Existing requests with open groups at migration time are split
  by a data migration step using the same builder, so no "Open" tag survives.

### S9 Tag render data with subject parts [BE]

- **AC-S9-1** `resolve-prices` and the export payload carry on each tag
  `parts[]` with full product data per part: `product_id, code, name,
  dimensions, spec_lines, specs[], images[], barcode, list_price, sell_price`
  (offer under the line's promotion, else null), in package order.
- **AC-S9-2** A part's `images` follow the same resolver as the parent
  (`gallery_images`), with the S10 tiebreak.
- **AC-S9-3** The tag's own `list_price` / `sell_price` / `show_promo_price`
  follow S7 (line promotion, manual, basis) plus the existing marketing
  override precedence.
- **AC-S9-4** The pinned payload includes `parts[]`; the data-change diff
  reports a part's price or photo change under that part's code.
- **AC-S9-5** Export's promotion guard checks every line promotion in use on
  the request (not a header one) using MYT today, and names the line in the
  409.

### S10 Product photo tiebreak [BE]

- **AC-S10-1** `gallery_images` orders by `is_primary DESC`, then attachment
  type rank (`Product Photos` = 0, any other = 1, `Technical Specifications`
  = 2), then `sort_order NULLS LAST`, then `created_at`.
- **AC-S10-2** A product with a Technical Specifications image linked before a
  Product Photos image, neither primary, resolves the Product Photos image
  first on `resolve-prices` and on the export payload.
- **AC-S10-3** A product whose only image is a technical drawing still
  resolves it (no filter, only ordering).

### S11 CRM line price edit route [BE]

- **AC-S11-1** `PATCH /dealer-kit/price-tag-requests/{id}/lines/{line_id}`
  accepts `{promotion_id?, manual_sell_price?}` under
  `price_tag_requests.process`, validates per AC-S6-4/5, clears the line's
  tags' pin fields, and returns the refreshed request.
- **AC-S11-2** 409 on a terminal request; 403 without the permission; 404 for
  a line on another request.

### S12 Frontend tests [T]

- **AC-S12-1** vitest: `PriceTagRequestForm.linePricing.test.tsx` covers
  AC-S1-1..9 and AC-S2-1..2 against a mocked line-pricing service.
- **AC-S12-2** vitest: `RequestTagDesigner` rail test asserts no Split / Pick
  one control and TAG SIZE rendered after LINES inside the top panel.
- **AC-S12-3** vitest: `product-block.test.ts` covers subject resolution
  (parent default, part index, out-of-range fallback) for slot, text token,
  price badge and barcode.
- **AC-S12-4** vitest: `TagSheetRenderer` test proves a part subject renders
  that part's image id and code on the print path.
- **AC-S12-5** pytest files per S6 to S11, Postgres only, own seed chain.

## Phase 3 - verification

- **AC-E2E-1** [E2E] agent-browser, via sidebar from `/`: portal form in
  Selling mode with a sink combo (open tap group) shows auto promotion,
  candidate prices; submit; CRM designer shows `1a` and `1b`, no Open; TAG
  SIZE at the foot; set the image slot's Product to the tap on `1a` and see
  the tap's photo; export PDF shows the same. Screenshots at 1280 and 375.
- **AC-E2E-2** [E2E] CRM detail: change `1a`'s line promotion, see the tag SP
  change and the pin banner appear.
- **AC-UX-1** [UX] No new motion. The Product select and the manual price
  input use existing primitives; the rail relayout has no transition.
