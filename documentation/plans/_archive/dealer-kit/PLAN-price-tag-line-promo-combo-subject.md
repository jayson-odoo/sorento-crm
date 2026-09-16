# PLAN - Price tag: line-level promotion, combo subject picker, auto-split, photo tiebreak, tag size

Status: merged 2026-09-16 as PR #948 and deployed. Follow-up lane fix/price-tag-line-price-columns turns the per-line price fields into real table columns on desktop.
UAC: `documentation/plans/dealer-kit/price-tag-line-promo-combo-subject-acceptance-criteria.md`
Predecessor: `PLAN-price-tag-ai-extract-resolver.md` (merged #929, 15 Sep 12:08Z), `PLAN-price-tag-combos.md` (#913), `PLAN-price-tag-r9-review-loop.md` (#907).
Lane: one lane, one PR. Branch `feat/price-tag-line-promo`, worktree `.claude/worktrees/price-tag-line-promo`, stack slot :3080/:8080, private DB `sorento_ptlp_ci`.

Owner walked the merged #929 on prod on 15 Sep 2026 and sent five findings with
screenshots. The journey and grill happened in chat the same evening; the rulings are
in the UAC's Journey section and restated per decision below.

All line refs are `origin/main` at 3009b374c.

**Seam found during Phase 3 (not in the original design):** the app session is `autoflush=False`; `_add_line_parts` must attach parts to `line.parts`, or the tag builder lazy-loads an empty list and mints one tag (8ca1980b1). AC-S7-4 reworded: a saved line's basis never inherits the lookup's auto pick.

## What exists (measured, two Sonnet explorers 15 Sep)

- **Promotion is per request.** `PriceTagRequest.promotion_id` (`app/models/price_tag.py:100-104`),
  `price_mode` (`:110`), line `show_promo_price` derived on every save as
  `request.price_mode == "selling"` (`price_tag_request_service.py:266`). Portal form loads
  every active promotion once on mount (`PriceTagRequestForm.tsx:644`, select at `:2301-2313`)
  from `lookup_promotions` (`price_tag_request_service.py:1829-1880`): active window in MYT,
  contact audience, text search. **No product filter.** CRM detail only displays
  `promotion_name` (`PriceTagRequestDetail.tsx:776-782`); no CRM route writes price mode or
  promotion.
- **Pricing engine** `resolve_prices` (`app/services/dealer_kit/pricing.py:181-224`): per product
  `PriceView(list_price, offer_price, ...)`, offer from `PromotionProduct` rows of the given
  promotion, audience-gated, lowest wins, discarded when `<= 0` or `>= list`
  (`_offer_worth_showing :265-292`). No `Product.selling_price` column.
- **Tag price** `resolve_tags_live` (`tag_data_service.py:627-736`): host + resolved parts summed;
  host with no offer falls back to `data["list_price"]` (`:692-698`), parts through
  `_offer_or_list` (`:471-480`). So a combo is never `sell_price is None` and prints "SP" even
  with no promotion; a plain product line stays LP (`:674-675`). Confirmed by
  `tests/test_price_tag_tag_render_data.py:309-324` ("1299 offer + 199 list + 249 offer").
  Unresolved open group contributes nothing (`_resolved_part_products :541-566`).
- **Open slot** = `PriceTagRequestLinePart` with `product_id NULL` + `candidates`
  (`ck_ptag_line_parts_resolved_or_open`). One default tag per line, built at
  `price_tag_request_service.py:315-336`. Designer rail `TagRailRow`
  (`RequestTagDesigner.tsx:1768-1924`) shows Split (`POST /tags/{id}/split`, `split_tag :1245-1296`)
  or Pick one (`PATCH /tags/{id}` with `choices`, `validate_choices :1213-1243`). Portal part row
  offers "Not sure, any of N" (`PriceTagRequestForm.tsx:2490-2565`).
- **Rail layout** `TagCanvasEditor.tsx:3384-3462`: vertical `ResizablePanelGroup`, top panel =
  `leftRail` (LinesRail + TagSizeControl, `RequestTagDesigner.tsx:1261-1314`), handle, bottom =
  LayersPanel. LinesRail wrapper is `max-h-[45%] shrink-0` (`:1630`), TagSizeControl `shrink-0`
  (`TagSizeControl.tsx:167`), so dead space sits between TAG SIZE and the handle.
- **Tag binding is the LINE = parent product.** `boundData = {kind:'line', line: row}`
  (`RequestTagDesigner.tsx:573-578`). `_line_product_data` (`tag_data_service.py:739-760`)
  resolves code/name/specs/images/barcode once per line from the host. Parts reach the canvas
  only as `TagPartData {product_id, code, name, dimensions}` (`tag-template-types.ts:565-572`)
  joined into `set_members` text (`_package_text :582-605`). Token vocabulary
  (`merge-fields.ts:73-99`, `SlotBinding` `tag-template-types.ts:25-39`): `product.*`, `set.*`,
  `line.quantity`, `spec.<key>`, slots `product_image|code|name|dimensions|spec_lines|
  included_accessories|list_price|sell_price|badges|alternatives|accessories|set_members|barcode`.
  No member namespace.
- **Photo pick** `gallery_images` (`app/services/dealer_kit/product_images.py:122-165`):
  image mime, not deleted, `_may_see`; order `is_primary DESC, sort_order NULLS LAST, created_at`.
  No attachment type or folder filter. Frontend `primaryImageOf` (`product-block.ts:161-205`)
  = `find(is_primary) ?? images[0]`, same call on canvas and print
  (`TagSheetRenderer.tsx:275-291`). SRTKS8547 in the 0907 copy: both rows `is_primary=false`,
  Technical Specifications (`attachment_types.type_name`) linked 2026-05-20 06:53, Product
  Photos 07:20, so the drawing wins. `attachment_types` has no code for either; match on
  `type_name`.
- Pins: `pin_tags` (`tag_data_service.py:1131-1156`) freezes `resolve_tags_live` output per tag on
  first design open; `resolve_request_line_data :785-874` prefers the pin and reports
  `data_changes`. Export guard `_check_promotion_expired`
  (`tag_sheet_export_service.py:42-88`) checks only the header promotion, with `date.today()`.
- Alembic head on `origin/main`: `ptag_0010_badge_textcolor`. Run `scripts/alembic-reparent.sh`
  before PR.

## Decisions

**D1 Promotion moves to the line; the header keeps only List / Selling.** Owner ruling: a
request-level promotion breaks the moment two lines sit on two promotions, and an
auto-only pick is too rigid when the promo is missing or wrong. So: `price_mode` stays on
the request; `promotion_id` and `manual_sell_price` live on the line. The header column is
dropped in the same migration (backfilled into lines first). One source of the price basis,
no dead column.

**D2 Auto-fill, override, manual.** In Selling mode each line's promotion is pre-filled with
the covering promotion that gives the lowest tag total; the salesperson overrides from a
list scoped to promotions covering that line (`PromotionProduct` join on parent, resolved
parts and candidates); with no covering promotion a numeric input takes an agreed price.
Zero extra entry when auto is right, one select when wrong, one number when there is no
promo. Manual and promotion are exclusive on a line (picking a promotion clears manual).

**D3 One promotion per line, uncovered parts print list, SP only when it means something.**
Owner ruling: combo parts sit on the same promotion. `sell_price` = manual, else sum of
(offer under the line promotion if worth showing, else list) over parent + resolved parts.
New `sell_price_basis` (`manual` | `promotion` | `list`). `show_promo_price` (existing line
column, still derived on save) becomes `price_mode == 'selling' and basis != 'list'`, so a
combo with no offer prints LP exactly like a plain product. This retires the "SP that is a
list sum" defect without adding a flag the designer has to read.

**D4 Pricing is one service, two thin routes.** `line_pricing(db, lines, viewer_codes)` in
`app/services/dealer_kit/pricing.py` (next to `resolve_prices`, which it calls) returns per
line list total, promotion options with totals, auto pick, sell total, parts at list, and
per-candidate prices. Portal route under `/public/portal/lookups/line-pricing` (contact
audience), CRM route under `/dealer-kit/price-tag-requests/line-pricing` (viewer). The form
calls it on line add, combo apply, part resolve, promotion change and mode switch; the
response is the only place prices come from on the form (no client-side arithmetic).
`lookup_promotions` and `GET /lookups/promotions` are removed with the header select.

**D5 CRM staff can change a line's price basis.** Owner ruling for flexibility. New
`PATCH /dealer-kit/price-tag-requests/{id}/lines/{line_id}` under
`price_tag_requests.process`, same validation as the portal, clears the line's tags' pin
fields so the existing data-change banner carries the change into a pinned design. Terminal
request: 409. The detail page's lines table gets the same two cells as the portal form,
saving on change.

**D6 Open groups split where tags are built, so the designer never sees one.** Owner ruling:
straight split, no Split / Pick one. The tag row builder at
`price_tag_request_service.py:315-336` is the one seam every path passes through (create,
update, revise, design-first). It emits one tag per candidate combination (cartesian over
open groups) with `choices` filled, keeping existing split tags untouched when parts are
unchanged (compare the set of `choices` maps). `split_tag`, the split route, `choices` on
the tag PATCH, `validate_choices`, and the rail's Split / Pick one UI are deleted.
`open_groups` stays in the response shape (always empty) so `TagRailRow` and the print
renderer need no type churn beyond dropping the branch. A data migration step splits any
existing open tag with the same builder.

**D7 Combo tags carry every product; a layer picks its subject.** Owner ruling: a member must
have the same capability as the parent, chosen per layer, and single products never ask.
`TagPartData` grows to full product data (`images, spec_lines, specs, barcode, list_price,
sell_price`), resolved through the same `_line_product_data` per part product (one master
data read per distinct product per line, cached in the resolve pass). Any layer that reads
product data gains an optional `subjectPart?: number` (index into `line.parts`; absent =
parent). `product-block.ts` gets one function `subjectOf(data, layer): ProductTagData |
LineTagData` that every existing resolver (`resolveSlotText`, `slotImageAttachmentId`,
`resolveBarcodeValue`, `priceBadgeInput`, merge-field rendering) calls first. The print
renderer already goes through those functions, so the PDF follows for free. A price badge's
subject list has one extra entry, **Tag total** (`subjectPart` absent), the roll-up of parent
+ parts that today's badge prints, and it is the default; the parent alone (`subjectPart: -1`)
and each part alone (`subjectPart: n`) print that product's own list and offer. Owner ruling
15 Sep: a combo tag prints the roll-up in the big box and each product's own price beside
its code. Other layer kinds default to the parent. An existing design renders unchanged. The properties panel shows a **Product**
SearchableSelect only when `line.parts.length > 0`. "Apply to all" onto a line with fewer
parts drops the subject and toasts the layer name. Layer rows suffix the part code.

**D8 Photo tiebreak by attachment type, no filter.** Owner ruling. `gallery_images` joins
`attachment_types` and orders `is_primary DESC`, then a CASE on `type_name`
(`Product Photos` 0, else 1, `Technical Specifications` 2), then the existing keys. A
product whose only image is a drawing still gets it. The brochure picker (`is_primary`)
still wins outright. One resolver, so canvas, portal preview and PDF agree.

**D9 TAG SIZE at the foot of the top panel.** Owner ruling. `LinesRail` wrapper becomes
`flex min-h-0 flex-1 flex-col`, `TagSizeControl` stays `shrink-0` after it, the panel's
inner column is `flex h-full flex-col` with no `overflow-y-auto` on the outer (the list
scrolls itself). No new splitter.

**D10 Export guard per line.** `_check_promotion_expired` walks the distinct line promotions
in use, uses `business_today()` (MYT) like the engine, and names the first offending line
in the 409.

**D11 No new motion.** Two selects and a number input from the existing primitives; the rail
relayout is static.

**Not doing, and why**
- Per-part promotion: owner ruled parts share the line's promotion. If a real request needs
  a part on a second promotion, that is the trigger for a per-part column.
- Keeping `PriceTagRequest.promotion_id` as a deprecated column: one dead column becomes two
  sources of truth by the next lane. Dropped with backfill.
- A `{{part.n.*}}` token family: the subject-per-layer ruling means the existing `product.*`
  tokens simply follow the layer's subject. No new vocabulary to teach.

## Data model

```
price_tag_request_lines
  + promotion_id        UUID NULL FK promotions(id) ON DELETE SET NULL, indexed
  + manual_sell_price   NUMERIC(12,2) NULL
    show_promo_price    (unchanged column; now derived = selling AND basis != list)
price_tag_requests
  - promotion_id        (dropped after backfill)
tag layer props (JSONB doc)
  + subjectPart?: number   on text | product_slot | price_badge | barcode layers
                           (absent = parent; price_badge: absent = tag total, -1 = parent, n = part n)
```

Migration `ptag_0011_line_promotion`: add columns, `UPDATE lines SET promotion_id =
requests.promotion_id`, drop header column, then split existing open tags via the D6
builder. Downgrade: re-add header column from `min(line.promotion_id)` per request, drop
line columns; split tags are left as they are (they are valid data either way).

## API contract (Phase 1 documents this at the top of the service file)

- `POST /api/v1/public/portal/lookups/line-pricing` and
  `POST /api/v1/dealer-kit/price-tag-requests/line-pricing`
  body `{ price_mode, lines: [{ key, product_id, part_product_ids[], candidate_product_ids[],
  promotion_id? }] }` →
  `[{ key, list_price, promotion_options: [{ id, description, sell_price }], auto_promotion_id,
  sell_price, sell_price_basis, parts_at_list: [product_id], candidates: [{ product_id,
  list_price, sell_price }] }]`
- Line on create / update / response: `+ promotion_id, promotion_name, manual_sell_price,
  list_price, sell_price, sell_price_basis`; request: `- promotion_id, promotion_name`.
- `PATCH /api/v1/dealer-kit/price-tag-requests/{id}/lines/{line_id}`
  `{ promotion_id?: string | null, manual_sell_price?: number | null }` → request response.
- Removed: `GET /public/portal/lookups/promotions`, `POST .../tags/{tag_id}/split`, `choices`
  on `PATCH .../tags/{tag_id}`.
- `resolve-prices` / export tag row: `parts[]` grows per D7; `sell_price_basis` added.

## Slices (tracer bullets, in order)

| Slice | Scope | UAC |
| --- | --- | --- |
| S1 | Portal form: per-line List price / Promotion / Selling price cells against a mocked line-pricing service; header promotion select removed | S1 |
| S2 | Part row candidate prices | S2 |
| S3 | Designer rail: remove Split / Pick one; TAG SIZE at the foot | S3 |
| S4 | Subject picker: `subjectPart` on layers, `subjectOf`, properties panel select, layer row suffix, Apply-to-all fallback, print renderer | S4 |
| S5 | CRM detail lines table: Promotion + Selling price cells (mocked) | S5 |
| S6 | Migration + models + schemas | S6 |
| S7 | `line_pricing` service + both routes; `show_promo_price` derivation | S7 |
| S8 | Auto-split in the tag builder; delete split/choices paths; data migration step | S8 |
| S9 | Tag render data: full parts, basis, pin diff per part, export guard per line | S9 |
| S10 | `gallery_images` tiebreak | S10 |
| S11 | CRM line PATCH route | S11 |
| S12 | Swap mocks for real calls; vitest + pytest per UAC S12 | S12 |

Phase 1 = S1 to S5 (coder, worktree, mocks only). Phase 2 = S6 to S12, tester writes the red
tests first per slice from the UAC and the captain's test list. Phase 3 once: reviewer,
security-reviewer (portal ingest + permission gating on the new PATCH), browser
verification (AC-E2E-1, E2E-2), then guide-writer.

## Files

Backend: `app/models/price_tag.py`, `app/schemas/price_tag.py`,
`app/services/price_tag_request_service.py` (tag builder `:315-336`, `_add_lines`, remove
`split_tag`/`validate_choices`/`lookup_promotions`), `app/services/dealer_kit/pricing.py`
(`line_pricing`), `app/services/dealer_kit/tag_data_service.py` (`resolve_tags_live`,
`_line_product_data` per part, `pin_payload`, diff), `app/services/dealer_kit/product_images.py`
(`gallery_images`), `app/services/dealer_kit/tag_sheet_export_service.py` (guard),
`app/api/v1/dealer_kit/price_tag_requests.py` (line PATCH, line-pricing, remove split),
`app/api/v1/public/portal_price_tag.py` (line-pricing, remove promotions lookup),
`alembic/versions/ptag_0011_line_promotion.py`.

Frontend: `app/(auth)/portal/components/PriceTagRequestForm.tsx` (Price section, lines
table, part row), `app/(auth)/portal/lib/price-tag-request-service.ts`,
`app/(protected)/dealer-kit/price-tag-requests/components/PriceTagRequestDetail.tsx`,
`app/(protected)/dealer-kit/price-tag-requests/[id]/design/components/RequestTagDesigner.tsx`
(rail, `TagRailRow`, `LinesRail`), `app/(protected)/dealer-kit/tag-templates/components/
TagCanvasEditor.tsx` (properties panel Product select, layer row suffix),
`lib/dealer-kit/tag-template-types.ts`, `lib/dealer-kit/product-block.ts` (`subjectOf`),
`lib/dealer-kit/merge-fields.ts`, `app/(public)/c/print/tag-sheet/[downloadId]/components/
TagSheetRenderer.tsx`, `services/priceTagRequestService.ts`.

Tests: `tests/test_price_tag_line_pricing.py`, `tests/test_migration_ptag_0011_line_promotion.py`,
`tests/test_price_tag_auto_split.py`, `tests/test_price_tag_tag_render_data.py` (parts,
basis; the 1299+199+249 case now asserts basis and `show_promo_price`),
`tests/test_dealer_kit_tag_data.py` (photo tiebreak), `tests/test_price_tag_request_crm_routes.py`
(line PATCH); vitest per UAC S12.

## Captain's test list (one line per AC id, handed to the tester with the UAC)

Written at Phase 2 start per slice; the shape is `test_<ac_id>_<name>: <assertion in words>`.

## Risks

- `PriceTagRequest.promotion_id` / `promotion_name`: grep on 15 Sep found no reader in
  `sorento_crm_mcp/` or the Respond context builders, so the drop touches only the schemas,
  the form, the detail header and the export guard.
- Cartesian split: the 0907 copy already has two lines with TWO open groups each (2 x N tags).
  Acceptable per the ruling; the rail label order (`1a, 1b, ...`) follows candidate order of
  the first group, then the second.
- Existing designs with `subjectPart` absent must render byte-identical; S4's vitest snapshots
  guard it.

## Backlog (documentation/backlogs/backlog.md)

- Per-part promotion when a real request needs it (trigger named in D3).
- Portal read view of a submitted request could show `parts_at_list` per line.
