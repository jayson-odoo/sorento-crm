# PLAN: price tag templates per product (auto-pick or choose, live preview)

Status: building (track: full L lane, migration + security review). Card answers assumed on the
recommendations (Q1 c, Q2 a, Q3 a, Q4 a, Q5 a) until crew answers.

Lane: PRICETAG-TEMPLATE-PER-PRODUCT. Card: `CARD-pricetag-template-per-product-02nov.md`.
UAC: `pricetag-template-per-product-acceptance-criteria.md`. Mock:
`pricetag-template-per-product-mock.html`.

## Data (one migration)

- `dealer_kit.product_tag_template(id, product_id FK products CASCADE, template_id FK
  dealer_kit.tag_template CASCADE, created_by, created_at)`, unique (product_id, template_id),
  index on template_id. Not company-scoped: reachable only through its product and template, both
  scoped (same reasoning as `TagTemplateVersion`).
- `price_tag_request_lines.tag_template_id` UUID FK `dealer_kit.tag_template` SET NULL, nullable.

## Backend

- `app/services/dealer_kit/product_tag_template_service.py` (new): `linked_templates`,
  `set_product_templates`, `published_links_for(product_ids)`, `bulk_match` / `bulk_assign`,
  `resolve_line_template` (the AC-10/11/12 rule, used by the request service on save and submit).
- Routes: `products/{id}/tag-templates` GET/PUT in `api/v1/dealer_kit/tag_data.py`;
  `tag-templates/{id}/assign[/preview]` in `api/v1/dealer_kit/tag_templates.py`; portal lookups
  `product-tag-templates/{product_id}` and `tag-preview` in `api/v1/public/portal_price_tag.py`.
- Preview: build TRANSIENT request / line / tag objects (never added to the session) and call the
  same `tag_sheet_export_service.design_media` the proof uses, so a preview and a proof cannot
  resolve differently.
- Request service: line create/update/revise copy `tag_template_id`; `resolve_line_template`
  fills a single link, refuses an invalid one; submit refuses a missing pick on a many-link line.

## Frontend

- `ProductTagTemplatesSection.tsx` on the product Overview (under Combos).
- `AssignTemplateDialog.tsx` from the Tag Templates list row.
- Line editor: `tag_templates` lookup per product (like combos), `tag_template_id` on DraftLine and
  the payload, Template cell in `PriceTagLinesTable`.
- `PriceTagLivePreview.tsx`: calls the preview lookup (debounced), builds the sheet doc with
  `tagForTag` + `arrangeTagSheets`, renders `DesignViewer`.
- Designer: `defaultTemplateFor` prefers the line's `tag_template_id`.

## Tests (red first)

- pytest: links CRUD + RBAC, bulk preview/assign + empty-filter refusal, line rule
  (single fills, many refuses at submit, invalid refused, set line refused), portal lookup scope,
  preview writes nothing and returns the chosen template, migration up/down.
- vitest: section (manager vs viewer vs empty), line Template cell (one / many / none), preview
  builds one tag per line, designer default prefers the stored template.
