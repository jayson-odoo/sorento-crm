# UAC: price tag templates per product

Plan: `PLAN-pricetag-template-per-product-02nov.md`. Card: `CARD-pricetag-template-per-product-02nov.md`.

## Product links

- AC-1 A product can carry zero, one or many tag templates; the same pair is stored once.
- AC-2 `GET /api/v1/dealer-kit/products/{id}/tag-templates` lists the product's linked templates
  (id, name, family, print size, published flag); needs `dealer_kit.tag_templates.view`.
- AC-3 `PUT /api/v1/dealer-kit/products/{id}/tag-templates {template_ids}` replaces the set; needs
  `dealer_kit.tag_templates.manage`; 403 without it; 404 for an unknown product or template.
- AC-4 The product page Overview shows a "Price tag templates" card to anyone holding
  `dealer_kit.tag_templates.view`: SearchableMultiSelect for a manager (an add saves at once, an
  untick parks `product.unlink_tag_templates` with a countdown), chips only for a viewer, heading +
  hint when empty.

## Bulk assignment

- AC-5 `POST /api/v1/dealer-kit/tag-templates/{id}/assign/preview {brand_ids, category_ids,
  item_class_ids, family_codes}` answers `{matched, already_linked}`; an all-empty filter is refused
  (422) so a click can never touch every product.
- AC-6 `POST /api/v1/dealer-kit/tag-templates/{id}/assign {..., action: add|remove}` adds the
  template to every matching product that lacks it / removes it from every matching product that
  has it, and answers `{changed}`. Filters are AND across kinds, OR within a kind. Manage permission.
- AC-7 Tag Templates list has an "Assign to products" icon button per row that opens the dialog
  with the live count and Add / Remove.

## Request lines

- AC-8 Portal lookup `GET /public/portal/lookups/product-tag-templates/{product_id}` lists that
  product's linked PUBLISHED templates, scoped to the request company, gated like the other price
  tag lookups.
- AC-9 A line stores `tag_template_id`. Create / update / revise accept it; the detail returns it
  with the template name.
- AC-10 Submit refuses (422, field `line:<i>`, "Pick a tag template for this line.") a product line
  whose product has two or more published links and no valid pick.
- AC-11 A product with exactly one published link: the line is given that template on save when
  the client sent none.
- AC-12 Any save DROPS a `tag_template_id` that is not one of the product's published links
  (stored as no pick, so Submit asks again; card R4: no own error, so no way to probe whether
  another template id exists), and drops any `tag_template_id` on a set line.
- AC-13 A product with no published link: no field, no refusal, behaviour as today.
- AC-14 The line row shows "Template: <name>" for one, a required SearchableSelect for many,
  nothing for none.

## Live preview

- AC-15 Portal `POST /public/portal/lookups/tag-preview {price_mode, lines[]}` answers, per line
  key, the template to draw (the line's pick, else its single link, else its first link; a product
  with no link gets none, a set line only an exact furniture_set template - #2101; formerly the
  family default among published templates) with that version's doc, the resolved tag data and the
  media maps. No row is written.
- AC-16 The request form shows a "Preview" section (while the request is not yet at a status that
  shows the real design) drawn through DesignViewer; it redraws after lines, price mode, promotion,
  typed price or template change.

## Designer

- AC-17 Marketing's designer starts a line's tag from the line's stored template when it is
  published; else today's family rule. "Use template..." is unchanged.

## Migration

- AC-18 One migration adds `dealer_kit.product_tag_template` and
  `price_tag_request_lines.tag_template_id`; idempotent upgrade, clean downgrade.
