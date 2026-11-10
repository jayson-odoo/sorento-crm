# PLAN: pick eligible products inside the Tag Template designer (bulk link)

Status: Plan, waiting on owner (mock + card Q1-Q5 filed as crew-ask). Track: standard lane (no
migration, no permission change, expected diff over 300 lines; security-reviewer joins because the
client now sends product/combo ids that must be company-scoped).
Lane: PRICETAG-TEMPLATE-PRODUCTS. Requested: owner + management meeting 9 Nov, relayed 10 Nov.
Mock: `pricetag-template-products-mock.html` (same folder).

## Journey

Marketing opens a price tag template in the Tag Template designer, clicks Products, searches by code
("SRTKS" for kitchen sinks), narrows by type / brand / category, ticks many rows (or "all matching")
and links them in one click. The Linked tab shows what prints with the template today, with each
row's Default LP / SP, and removes with the standard countdown. Salespeople are unchanged: they pick
from what marketing linked. The template's definition and variation matrix stay marketing-owned.

## What exists today (measured, 10 Nov, main 03be747b)

Data, no change needed:
- `dealer_kit.tag_template` - `sorento_crm_backend/app/models/dealer_kit.py:705`.
- `dealer_kit.product_tag_template` (product_id, template_id, default_list, default_selling; unique
  pair; partial unique index = one default per type per product) - `dealer_kit.py:812`.
- `dealer_kit.combo_tag_template`, same shape keyed on `product_combos.id` - `dealer_kit.py:866`.

Service `sorento_crm_backend/app/services/dealer_kit/product_tag_template_service.py`:
- default rules: `_defaults_for` :129, `_replace_links` :392 (per-owner PUT, keeps a lone link the
  default), `_lone_link_is_default` :550.
- per-owner writes: `set_product_templates` :457, `set_combo_templates` :520 (+ `_require_fit` :502,
  combo shape check `template_needs.fit_reason` in `template_needs.py:130`).
- bulk by filter: `_bulk_products_query` :638 (brand / category / item class / family code, AND across,
  OR within, empty refused 422), `bulk_preview` :693, `bulk_assign` :709 (products only; add keeps
  the existing lone link as default, a first link becomes the default).
- count: `tag_template_service.usage` (`tag_template_service.py:145`).

Routes:
- `api/v1/dealer_kit/tag_templates.py`: `/family-codes` :180, `/{id}/usage` :295,
  `/{id}/assign/preview` :526, `/{id}/assign` :542. View = `dealer_kit.tag_templates.view` :50,
  write = `dealer_kit.tag_templates.manage` :51.
- `api/v1/dealer_kit/tag_data.py`: product links GET/PUT :171/:191, combo links GET/PUT :220/:240.
- deferred unlinks: `app/services/record_actions.py` `tag_template.unassign_products` :1822,
  `product.unlink_tag_templates` :1843, `combo.unlink_tag_templates` :1864.

Frontend:
- Designer `sorento_crm_frontend/app/(protected)/dealer-kit/tag-templates/[id]/page.tsx`: toolbar
  trailing actions :592 (Versions, Save, Settings, Full screen), Versions side sheet :737.
- List row "Assign to products" `tag-templates/components/TagTemplatesList.tsx:515`, dialog
  `AssignTemplateDialog.tsx` (filter only, blind count, no rows shown, no code search, no combos).
- Product page card `master-data-management/products/[id]/components/ProductTagTemplatesSection.tsx`;
  combo field `ComboTemplatesField.tsx` (AddComboModal).
- Service/hooks `dealer-kit/services/productTagTemplateService.ts`, `dealer-kit/hooks/useProductTagTemplates.ts`.

So the gap is not storage or defaults; it is that the template direction has no visible list, no code
search, no per-row pick, no combos, and it sits on the list row instead of in the designer.

## Design (pending card answers)

Backend (no migration):
1. `GET /dealer-kit/tag-templates/{id}/candidates?q=&kind=product|combo|all&brand_ids=&category_ids=
   &linked=any|linked|unlinked&include_discontinued=&page=&limit=` -> rows `{kind, id, code, name,
   brand, category, linked, default_list, default_selling, fit_reason}` + `total`, `linked_total`.
   `q`: code starts-with (case-insensitive) OR name contains. Combos match on host product code/brand/
   category and their own name. All rows `_scoped` (company) via product / combo host.
2. `POST /{id}/assign` extended: `product_ids`, `combo_ids` (explicit picks) or `all_matching: true`
   + the same filter as (1). Ids outside scope are ignored (count reported), never linked. Combos that
   fail `fit_reason` are skipped and reported. Answers `{products_added, combos_added, skipped}`.
   Defaults: reuse `bulk_assign`'s existing rule, extended to combos.
3. `tag_template.unassign_products` payload accepts `product_ids` / `combo_ids` (Linked tab Remove).

Frontend:
4. NEW `tag-templates/components/TemplateProductsSheet.tsx`, opened by a "Products (N)" trailing
   toolbar action in the designer (manage permission only). Line tabs Linked / Add. Reuses
   `components/ui/sheet`, `SearchableSelect`/`SearchableMultiSelect` (clearable), the brand and
   category select hooks, `usePendingAction` countdown for Remove, toast + query invalidation of the
   product-page and combo link queries.

## Card questions (in the crew-ask)

Q1 combos in scope: (a) products and combos in one list with a Type filter (rec) / (b) products only.
Q2 old list-row "Assign to products" dialog: (a) retire it, the row action opens the designer on the
   Products panel (rec, one place) / (b) keep both.
Q3 search: (a) one box, code starts-with OR name contains (rec) / (b) contains on both.
Q4 discontinued products: (a) hidden unless "Show discontinued" is on (rec) / (b) always listed.
Q5 defaults on bulk link: (a) never change an existing default; a product with no links gets this as
   default for the types it fits; one with a link keeps that as default (rec, today's `bulk_assign`)
   / (b) also fill an empty default slot on products that already have 2+ links.

## Tests (red first, after approval)

pytest: candidates scope (foreign company rows never listed), q prefix vs name, kind filter, linked
flag + defaults, discontinued toggle; assign by ids / all_matching, foreign ids ignored, combo misfit
skipped, defaults rule (0 links, 1 link, 2+ links, existing default untouched); unassign by ids.
vitest: sheet hidden without manage, tabs, select page / all matching, disabled linked and misfit
rows, Link CTA counts, Remove countdown.
