# CARD: price tag templates per product (PRICETAG-TEMPLATE-PER-PRODUCT, 2 Nov)

Behaviour card. Read of `origin/main` 46de2f6d. Owner rulings of 2 Nov apply (one or many templates
per product; one = automatic, many = salesperson picks, with preview).

## What exists today (measured)

- `dealer_kit.tag_template` has a `family` (sink_combo, ala_carte, art_basin, wc, urinal, shower,
  mirror, mirror_cabinet, furniture_set) and no link to any product (`app/models/dealer_kit.py:703`).
  Only a template with `published_version_id` set is offered to request design (`:719`).
- The template a request tag starts from is picked in MARKETING's designer, in the browser:
  `defaultTemplateFor` (`lib/dealer-kit/request-tags.ts:84`) maps the product code prefix to a
  family (`lib/dealer-kit/line-family.ts`), then falls back to `ala_carte`, then to any template.
  Marketing can swap it with "Use template..." (`TemplatePickDialog.tsx`). Nothing about the
  choice is stored on the request line (`app/models/price_tag.py:188-262`); it lives only inside
  the saved tag sheet document.
- The salesperson sees the design only from `proof_ready` (`PriceTagRequestForm.tsx:132`,
  `portal_price_tag.py:196`). Before that the form has no picture of the tag at all.
- Products have `brand_id` and `category_id` (`app/models/product.py:277-278`), `item_class_id`
  (`:285`) and `family_code` (the model family from the code, `:309`). There is NO "series"
  column on a product (series exists only in Projects, `app/models/projects.py:857`).

## Rules (proposed)

R1. A product carries zero, one or many allowed price tag templates (a new link table
    `dealer_kit.product_tag_template`, product x template, unique pair). Only PUBLISHED templates
    count anywhere below; an unpublished one stays linked but is ignored until republished.
R2. Product page, Overview tab, new section "Price tag templates" under Combos: the linked
    templates as chips, edited with a `SearchableMultiSelect` (clearable). Editing needs
    `dealer_kit.tag_templates.manage` (marketing); seeing the card needs
    `dealer_kit.tag_templates.view` (the route's own gate). An add saves at once; an untick is an
    unlink, so it parks with a countdown and Cancel (`product.unlink_tag_templates`).
    Empty state: heading + hint, no button.
R3. Bulk assignment, Dealer Kit > Tag Templates, row action "Assign to products": pick brands,
    categories, item classes and model families (each a multi-select; any mix, matched as AND
    across kinds, OR within a kind; an all-empty filter is refused), see
    the matching product count, then Add or Remove that template for all of them. Same
    `dealer_kit.tag_templates.manage` permission.
R4. Price tag request line (portal form and the CRM's My Requests copy of it, same component):
    - product with ONE allowed template: used automatically, shown as plain text "Template: X".
    - product with MANY: a "Template" `SearchableSelect` on the line, required at Submit
      ("Pick a tag template for this line."); Save Draft accepts none.
    - product with NONE (and every product-set line): today's family rule, unchanged, no field.
    The choice is stored on the line (`price_tag_request_lines.tag_template_id`, SET NULL).
    A sent template that is not one of the product's published links is dropped (stored as no
    pick, so Submit asks again), never stored and never given its own error: no way to probe
    whether some other template id exists.
R5. Live preview on the request form: a "Preview" section that draws each line's tag with its
    template (picked or single link; a set line: an exact furniture_set template) and the line's
    real data and price. A PRODUCT with no linked template draws NOTHING and is named under the
    preview ("No tag template yet for <code>."): no silent family fallback, since the salesperson
    approves his own tag (#2101 browser pass: CKS821 drew a bathroom furniture layout; crew-ask
    on #2100, building (b)). Marketing seeds the links before go-live (PR body)
    (promotion or typed selling price, list/selling mode), through the same `DesignViewer` /
    `TagSheetRenderer` the proof uses. It redraws as lines, prices or the template change
    (debounced).
    No selling price for a "no selling price" brand (Cabana, lane CABANA-NO-SELLING-PRICE #2104):
    the preview resolves through the SAME `line_pricing` / `resolve_tags_live` the proof and the
    PDF use, so #2104's reader fix (price tags in Selling mode) covers the preview with no rule of
    its own here. A test in this lane asserts it once #2104's brand flag is on main.
R6. (revised for PRICETAG-SELF-APPROVAL #2101: the salesperson approves his own tag, marketing
    leaves the normal flow.) The final tag IS the template, auto-filled: each line's template
    (pick, single link, first link, else the family default) bound to the line's resolved data.
    One builder, `lib/dealer-kit/request-tags.ts` (`tagForTag` + arrange), draws it for this lane's
    live preview and for #2101's "generated tag" the salesperson approves, so what he approves is
    what he previewed. Split proposed to #2101: this lane owns the product links, the line's
    template pick, the preview endpoint and the builder; #2101 owns turning it into the request's
    saved tag sheet at approve and the status flow. Marketing's designer is only for an escalated
    request, and opens each tag on the line's stored template instead of the family guess
    ("Use template..." still lists every template).
R7. Editing an approved request (allowed by the 2 Nov ruling) may change the template too, same
    rules as R4.

## Examples (shapes for now; real masked dev rows requested from crew, crew-data-request on #2100)

E1. A basin `SRT WB...` linked to one template "Basin A5": the line shows "Template: Basin A5", no
    picker; the preview draws Basin A5; marketing's designer opens on Basin A5.
E2. A kitchen sink `SRT KS...` linked to "Sink combo A4" and "Sink combo A5": the line shows a
    Template select with both; Submit without a pick is refused on that line; after picking A5 the
    preview redraws in A5 size.
E3. A mirror with no link: no field; the preview and the designer use the `mirror` family template
    exactly as today.
E4. Marketing bulk-adds "Promo Tag 2026" to brand X + category Basins: 37 products gain it; any of
    them that already had one template now have two, so salespeople start being asked to pick.
E5. A linked template is unpublished: it disappears from E2's select; if it was a product's only
    link, the product falls back to E3 behaviour.

## Edge cases

- A draft saved with a template that has since been unlinked or unpublished: Submit refuses that
  line with the same message as an empty pick, so the salesperson picks again.
- A combo line: the HOST product's templates apply.
- Duplicating a request copies the line's template choice.
- Deleting a template removes its links (CASCADE) and nulls the line choice (SET NULL).
- Overlap with the parallel price tag lane (salesperson approves / escalate): both touch
  `price_tag_request_service.py` and `PriceTagRequestForm.tsx`; this lane only adds line fields
  and a preview section, no status flow changes.

## Answers (crew, 2 Nov, from owner rulings)

Q1 (c) model family AND item class, each a multi-select filter, beside brand and category. Q2 (a).
Q3 (a). Q4 (a), decided from the ruling's wording; the PR body says so, so the owner can bump it.
Q5 (a).

## Questions (as asked)

Q1. "Series" for bulk assignment: products have no series column. (a) model family (`family_code`
    from the code), (b) item class, (c) both. Recommendation: (c), cheap to offer both since both
    are columns already.
Q2. Bulk assignment: (a) Add and Remove, (b) Add only (remove per product page). Recommendation:
    (a), otherwise a wrong bulk add is 37 product page edits to undo.
Q3. A product with many templates: (a) no default, salesperson must pick, (b) the first-linked one
    pre-selected. Recommendation: (a), the ruling says the salesperson chooses; a silent default is
    how the wrong size gets printed.
Q4. Product-set lines: (a) out of scope, family rule as today, (b) link templates to sets too.
    Recommendation: (a), the ruling names products; let a real set case pay for (b).
Q5. Who edits the links: (a) `dealer_kit.tag_templates.manage` (marketing), (b) product edit
    permission. Recommendation: (a), the templates are marketing's and the bulk tool is theirs.
