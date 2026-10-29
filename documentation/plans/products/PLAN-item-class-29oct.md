# PLAN: Item Class from AutoCount (ITEM-CLASS)

Status: Review done (reviewer READY, security re-review no C/H/M findings, cloud browser
pass 5/5). Hand test and the end-to-end run through the shared service pending (SS branch
claude/item-class-sync-rbac-4sehj5 in foundryx-shared-service). Track: full (migration +
RBAC/access control change). UAC: `item-class-acceptance-criteria.md`.

## 1. Journey

Owner (29 Oct 2026): AutoCount Stock Item carries an Item Class (e.g. SERENE on three
SRTWC8066-SH-* items, brand SORENTO). hapi `itembypage` returns it as `ItemClass`, often "".
Sync it via the shared service like ItemType and ItemBrand; reference-data screen; product list
column (server sort, multi-select filter) and product form field; contact access by class within
brand, applied everywhere brand scoping applies.

## 2. Measured facts (main 6011ba76)

| Fact | Where |
| --- | --- |
| Precedent: AutoCount ItemType already lands as its own table `item_types` (NOT product category), back-created on ingest | `sorento_crm_backend/app/models/product.py:165-187`; plan `documentation/plans/autocount/PLAN-item-type-crm-3oct.md` |
| `products.item_type_id` nullable FK SET NULL | `app/models/product.py:255-256` |
| Brand / category reference tables | `app/models/product.py:33` (`product_categories`), `:99` (`brands`) |
| Canonical push fields `category_code`, `brand_code`, `item_type_code` | `app/schemas/canonical_masters.py:193-198` |
| Ingest mapping: `ensure_reference` back-create, warnings `brand_created` / `item_type_created`; absent or blank = untouched | `app/services/master_ingest_service.py:603-618` |
| Contact brand access stored as `respond_contacts.brand_ids` ARRAY(UUID), NULL/[] = every brand | `app/models/access.py:295` |
| The ONE scope rule: `brand_predicate(scope, brand_col, company_col)`, per company, NULL brand out inside a restricted company | `app/services/contact_brand_scope.py:68-82` |
| Python twin for output guards: `_product_out_of_scope` | `app/services/contact_brand_scope.py:97-101` |
| Session stamp `set_brand_scope` / `get_brand_scope` on `db.info`, applied by `do_orm_execute` on Product | `app/models/base.py:75-91`; `app/services/company_scope.py` |
| Readers of the scope (17 files, 54 call sites): chatbot engine + business lane, order_service, entity_resolver, sales analysis, report_ask, low_stock_report, forecast, export tasks, API-key scope resolver | `grep -rn "brand_predicate\|get_brand_scope\|set_brand_scope" app` |
| Contact brands settings card read/write | `contact_brand_scope.py` `get_contact_brands` / `set_contact_brands` |
| FE reference-data screens to copy | `sorento_crm_frontend/app/(protected)/master-data-management/brands/`, `.../product-categories/` |
| FE product list brand filter | `.../products/hooks/useProductFilters.ts:13,37`; `.../products/components/ProductsList.tsx` |
| Shared service mapping ItemBrand/ItemType | UNVERIFIED: `jayson-odoo/foundryx-shared-service` is not attached to this sandbox yet |
| Does one ItemClass span several brands in real data | UNVERIFIED: needs crew-data-request |

## 3. Proposed design

- **D1 Storage.** New table `item_classes`, a copy of `item_types` (`item_class_code`,
  `item_class_name`, description, is_active, company scoped, unique `(company_id, code)`).
  `products.item_class_id` nullable FK SET NULL + index. Not the category table with a kind:
  ItemType already set the "own table" precedent and categories carry class/brand hints, stock
  limits and searchability that mean nothing for an item class.
- **D2 Ingest.** `CanonicalProduct.item_class_code`, the `item_type_code` rule except for blank:
  absent leaves the link untouched, "" clears it (crew ruling 29 Oct, security M1); unknown
  value back-created, warning `item_class_created`.
- **D3 Shared service.** hapi `ItemClass` -> canonical `item_class_code` next to where
  `ItemType` -> `item_type_code` is mapped (SS PR). Unlike ItemType, a blank ItemClass is
  always sent as `""` (security M1), so the first sync after deploy re-sends every product row
  once: about 12k db1 rows and every db2 row, through the normal `/external/ingest/products`
  path in batches of at most 1000 (`app/api/v1/external/ingest.py` `MAX_BATCH`).
- **D4 UI.** Reference Data > Item Classes (list + modal create/edit + detail, copy of Brands);
  product list column (server sort) + multi-select filter; product form field (View = Edit).
- **D5 Contact access: class nested under brand.** New column
  `respond_contacts.brand_class_ids` JSONB `{brand_id: [item_class_id, ...]}`. A brand absent from
  the map, or mapped to [], means every class of that brand (the brand rule today). A class pick
  only narrows a brand that is already in `brand_ids` (or every brand when `brand_ids` is NULL).
  Rule, folded into `brand_predicate` (no parallel function): a product passes when
  `brand IN scope AND (brand has no class list OR product.item_class_id IN that brand's list)`,
  per company as today. A product with no class inside a class-restricted brand is OUT (the
  NULL-brand rule Q1, mirrored). The scope object stamped on the session grows from
  `frozenset[brand_id]` to a small value carrying both; every caller keeps calling the same
  functions.
- **D6 Empty class.** "" in AutoCount = no class on the product = visible to contacts with no
  class restriction on that brand, hidden from contacts restricted to a class list.

- **D7 Scope encoding.** The scope stays a frozenset of strings: a whole brand is its id, a
  class-narrowed brand is one `<brand_id>/<item_class_id>` token per class. Every carrier (session
  stamp, RQ export args, turn ctx) already passes the set through untouched, so only
  `contact_brand_scope.py` reads tokens (`_split_scope`); the 8 `brand_predicate` call sites pass
  `Product.item_class_id` as a 4th column.
- **D8 Writers.** The contact card writes `brand_class_ids`; access-copy carries it (security
  H1); tag-apply prunes class lists of the brands it drops (review S2), so re-adding a brand later
  never brings an old narrowing back. The setup engine and access-sheet writers touch `brand_ids`
  only; the reader and the delete guard ignore class lists for brands outside `brand_ids`, so no
  writer can widen access.
- **D9 Delete guard.** Deleting a class a contact is limited to is a 409 (it would leave that brand
  narrowed to nothing while the card reads as "every class").

## 4. Answers (owner, 29 Oct)

Q1 (a) own table. Q2 (a) per brand. Q3 a brand with no class list shows its products with no
class; a brand limited to some classes hides them. Q4 (a) inside the Brands card, Lavish mock
first. db2 has no ItemBrand: class limits only take effect where a brand exists (AC-11).

## 5. Tests

SS: `service_backend/tests/test_autocount_item_class.py` (29). CRM: `tests/test_ingest_item_class.py`,
`tests/test_item_class_scope.py`, `tests/test_item_class_api.py`.
