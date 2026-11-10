# PLAN: pick eligible products inside the Tag Template designer (bulk link)

Status: in review (mock v3 approved 10 Nov 23:43; built, reviewer round 1 fixed, security CLEAR, browser
pass done). Track: standard lane (no migration, no permission change, diff over 300 lines; security-reviewer
joined for multi-company scoping of picked ids). Card: Q1 (a) products only, Q3 (a) never change a default,
Q2 open (old list-row Assign dialog kept until the owner says retire).
Lane: PRICETAG-TEMPLATE-PRODUCTS. Requested: owner + management meeting 9 Nov, relayed 10 Nov.
Mock: `pricetag-template-products-mock-v3.html` (same folder; v1, v2 kept).

## Journey

Marketing opens a price tag template in the Tag Template designer and clicks Products. One view
opens: the product grid with the template's current products already ticked. They search by code
("SRTKS" for kitchen sinks), narrow by category / brand, tick many rows (or "all matching"), untick any
that should not print with it, and Save once. Salespeople are unchanged: they pick from what marketing
linked. The template's definition and variation matrix stay marketing-owned.

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

## Design v3 (owner 10 Nov 23:4x: one view, no Linked / Add tabs)

Mock v3: `pricetag-template-products-mock-v3.html` (v1, v2 kept for the record). ONE view: the shared
product grid where a tick means "uses this template", opened with the current products ticked; search
and filters find more to tick, unticking takes one off, one Save applies both. Same model as the
product page link field (`ProductTagTemplatesSection.tsx:119`, value = the linked set) on the same grid
as Copy to other products.

The picker is reused, not new:
`sorento_crm_frontend/app/(protected)/master-data-management/products/[id]/components/ProductTargetPicker.tsx`
(`useProductTargetPicker` :67; used by `CopyAccessoriesDialog.tsx` and `CopyComboDialog.tsx` :84): server
search (contains on code / name / description), Category + Brand filters, shift/drag ticks, "Select all
N matching" capped at 500, paging, discontinued grey hint (owner 7 Nov), footer count.

Other pickers checked and not chosen: `dealer-kit/components/ProductPickerDialog.tsx` (collection pins
+ rule, card grid), `dealer-kit/tag-templates/components/ProductPickDialog.tsx` (one block's product),
`DeliveryScheduleProductPicker.tsx` (single select), `AssignTemplateDialog.tsx` (filter only, no rows).

Backend (no migration):
1. `GET /dealer-kit/tag-templates/{id}/product-ids`: ids of the products linked to it (scoped), seeds
   the ticks.
2. Products list `GET /master-data/products` (`products.py:116`, `product_service._build_list_query`
   :343) gains `tag_template_id` (the "Show: Uses this template" filter), one EXISTS, same scope.
3. `POST /dealer-kit/tag-templates/{id}/assign` (`tag_templates.py:542`) accepts `product_ids` (max
   500). Foreign ids are ignored, never linked. Defaults: today's `bulk_assign` rule (:709).
4. Pending action `tag_template.unassign_products` (`record_actions.py:1822`) accepts `product_ids`.

Frontend:
5. `useProductTargetPicker` takes an options object `{ excludeProductId?, initialSelection?,
   extraParams? }`; the old string argument keeps working for the two copy dialogs.
6. NEW `tag-templates/components/TemplateProductsDialog.tsx`: CopyComboDialog's modal shell (:129), no
   tabs, the picker seeded from (1), a "Show" SearchableSelect in its Filters popover, footer
   "N use this template after Save: +a, -r", Save = assign adds, then `useDeferredAction` countdown for
   removals. Opened by a "Products (N)" toolbar action in the designer (`[id]/page.tsx:592`), manage
   permission only.

## Card questions (v3, in the crew-ask)

Q1 combos: (a) products only here; combos keep their per-combo template field in AddComboModal (rec:
   the reused picker is a product grid; a combo grid would be a second picker, the thing the owner
   asked us not to build) / (b) also list combos, which needs a new combo grid.
Q2 old list-row "Assign to products" dialog: (a) retire it; the row action opens the designer with
   this dialog open (rec, one place) / (b) keep both.
Q3 defaults on bulk link: (a) never change an existing default; a product with no template gets this
   one as default for the price types it fits; one with a single template keeps that as default (rec,
   today's rule) / (b) also fill an empty default on products with 2+ templates.
v1's search and discontinued questions are settled by the reused picker (contains search;
discontinued pickable with a grey hint, owner 7 Nov).

## Tests (red first, after approval)

pytest: product-ids seed + products list tag_template_id (foreign company never listed);
assign by product_ids, foreign ids ignored, over-500 refused, defaults rule (0, 1, 2+ links, existing
default untouched); unassign by product_ids.
vitest: Products action hidden without manage; ticks seeded from product-ids; Save diff (+a, -r); copy dialogs
unchanged with the old argument; Link sends the picked ids; Remove countdown.

## Browser evidence run (cloud sandbox, agent-browser 0.27.0, 10 Nov, head 404a0713)

Stack: uvicorn :8000 on `.env.ci-tests` (sandbox `sorento_ci`, bootstrapped, every module installed),
`npm run dev` :3000. Seed (ZZT names, sandbox only): one published template "ZZT Kitchen sink A6", 30
SRTKS kitchen sinks (one discontinued) + 5 taps; sink 1 linked (default LP + SP), sink 2 linked plus
another template holding its default LP. Navigation by sidebar clicks from `/`.

1. PASS. Dealer Kit > Room Designer > Tag Templates > the template: toolbar "Products (2)" next to
   Versions. It opens one view (no tabs): the shared picker, sinks 1 and 2 ticked, "2 use this
   template", Save off.
2. PASS after a fix. Filters was unreachable while rows were ticked (the shared toolbar swaps it for the
   bulk strip); fixed with `keepFiltersWhileSelected`. Search "SRTKS" + Category "ZZT Kitchen Sink":
   "Filters 1", the Show / Category / Brand controls all in the popover.
3. PASS. Page tick, "Select all 30 records": "30 use this template after Save: 28 added, 0 removed"
   (seeded links kept). Untick sink 2: "29 ... 28 added, 1 removed".
4. PASS. Save: toast "Linked 28 products", the Save button became "Removing in 5s" + Cancel, the
   dialog closed on commit. DB: 29 linked; sink 1 kept its defaults; sink 2 unlinked, its remaining
   template now default LP + SP (AC-8); new sink 3 got this template as default LP + SP (AC-7).
   Toolbar then read "Products (29)".
5. PASS. 375px: Products sits in the toolbar's "More actions" menu; the modal is full width, the grid
   scrolls sideways inside its border, no page-level horizontal scroll.
6. PASS. Master Data > Products > All Products > SRTKS-8014-SS: the "Price tag templates" card lists
   "ZZT Kitchen sink A6" (AC-9, same rows both directions).

Screenshots kept (cap 2): `evidence-pricetag-template-products/1-save-countdown-1280.png`,
`2-dialog-375.png`.

## Assistant coverage (DoD 6 to 8)

6: `scripts/ci_ai_coverage.py` ok, no new paged list route (`/product-ids` is an unpaged seed for the
dialog). 7 and 8: n/a. Linking products to a template is a marketing curation task done visually in
the designer; the repo has no `ActionDef` registry and no `assistant_<module>.jsonl` gold file to extend.
