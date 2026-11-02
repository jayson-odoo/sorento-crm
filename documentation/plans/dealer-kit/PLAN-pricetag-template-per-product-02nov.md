# PLAN: price tag templates per product (auto-pick or choose, live preview)

Status: in review (track: full L lane, migration + security review). Card answered (Q1 c, Q2 a, Q3 a, Q4 a, Q5 a), mock approved; reviewer READY, security blocker fixed, browser pass done.

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
  (single fills, many refuses at submit, invalid dropped, set line dropped), portal lookup scope,
  preview writes nothing and returns the chosen template, migration up/down.
- vitest: section (manager vs viewer vs empty), line Template cell (one / many / none), preview
  builds one tag per line, designer default prefers the stored template.

## Browser evidence run (cloud sandbox, agent-browser 0.27.0, 2 Nov)

Stack: backend uvicorn :8000 on `.env.ci-tests` (sorento_test, bootstrapped), `npm run dev` :3000.
Seed (ZZT names): every module installed; a non-admin staff role with every permission except
`dealer_kit.price_tag_requests.view/.process` (My Requests refuses admins), a workspace, a sales
agent + customer for the contact; product A (one live template), B (two live templates, different
sizes), C (none).

1. PASS. Product B > Overview lists both templates; removing one and adding it back each sent
   `PUT /dealer-kit/products/{id}/tag-templates` 200, toast "Price tag templates saved". Product C
   shows "No price tag templates" + hint, no button.
2. PASS. Sidebar Dealer Kit > Room Designer > Tag Templates > row "Assign to products": empty
   filter disables both buttons and says "Pick at least one brand, category, item class or model
   family."; brand picked: "3 products match, 2 already have this template"; Add sent
   `POST /assign` 200, toast "Added to 1 product"; Remove showed a "Removing in Ns" toast with
   Cancel (no confirm), Cancel kept all links (DB count).
3. PASS. Price Tag Requests > Create: product A line shows "Template: <name>" and the Preview
   appears on the first item (`/my-requests/lookups/tag-preview` 200); product B shows the "Tag
   template" select, Submit without a pick shows "Pick a tag template for this line." on the row
   and sends nothing; picking the large template redraws as Sheet 1 / 2; product C has no field
   and draws on the family default.
4. 375px: product page, dialog and list usable. The form's Template sub-row ran past the card edge
   inside the sideways-scrolling lines table; fixed (sticky, viewport-capped sub-row).

Screenshots kept (cap 2): `evidence-pricetag-template-per-product/2-assign-dialog-brand-picked-1280.png`,
`3-form-product-B-picked-large-1280.png`.
