# PLAN - AutoCount ItemType on CRM products (ITEM-TYPE-CRM)

**Status:** Build (small fix track: additive migration only, no auth/RBAC change, no new ingest
surface; one new optional field on the existing products push). Pair lane: ITEM-TYPE-SS.

**UAC:** `item-type-crm-acceptance-criteria.md` (alongside).

## 1. Journey

Owner (3 Oct 2026): AutoCount's ItemType (MISC, PROJECT, WASTE, KITCHEN SINK, OMEX, ...) is kept on
each CRM product as reference data, the same way brands and product categories are: a reference
table, back-created when an incoming value does not exist yet, and the product linked to it.

## 2. Measured facts (origin/main e5441be9)

| Fact | Where |
| --- | --- |
| `Brand` / `ProductCategory` reference tables, company-scoped, unique `(company_id, code)` | `sorento_crm_backend/app/models/product.py:32-149` |
| `products.brand_id` FK `brands.id` SET NULL, nullable | `app/models/product.py:215` |
| Canonical product push shape: `category_code`, `uom_code`, `brand_code` | `app/schemas/canonical_masters.py:183-205` |
| Unknown canonical keys are dropped and logged, never refused | `app/schemas/canonical_masters.py:28-37` |
| Product push maps `brand_code` via `product_rules.ensure_reference` and warns `brand_created` | `app/services/master_ingest_service.py:590-596` |
| `ensure_reference`: match by normalised code, then name; else create `code = name = raw value`, description = auto-created note | `app/services/rules/product_rules.py:152-214` |
| Code / name column maps the matcher reads | `app/services/rules/master_rules.py:32-47` |
| AutoCount pull commits through the same `MasterIngestService` | `app/tasks/autocount_pull_tasks.py:294` |
| Contract diff `fields_added` + warnings vocabulary | `app/api/v1/external/contract.py:81-82, :238-257` |

## 3. Decisions

- **D1 Storage.** New table `item_types` shaped like the smallest reference sibling:
  `id`, `company_id` (CompanyScopedMixin), `item_type_code` String(50), `item_type_name`
  String(150), `description`, `is_active`, `created_at`, `updated_at`; unique
  `(company_id, item_type_code)`. `products.item_type_id` nullable FK SET NULL + index.
- **D2 Ingest field.** `CanonicalProduct.item_type_code` (Optional, max 100, the same as
  `brand_code`), pending the ITEM-TYPE-SS contract. Absent = untouched; blank = untouched (the
  brand rule, `master_ingest_service.py:590`). Unknown value back-created via
  `ensure_reference`, warning `item_type_created`.
- **D3 Matching.** Exactly what brands use (`ensure_reference`: normalised code, then name, which on
  an auto-created row equals the code). Nothing beyond that.
- **D4 Contract.** `item_type_code` added to `fields_added.products`, `item_type_created` to the
  warnings vocabulary. No version bump: unknown keys are already dropped, so an older Sorento
  never refuses a push that carries it (crew-ask on the PR).
- **D5 UI.** Read-only on the product detail only if it is a trivial reuse of how brand is
  shown; otherwise storage only, stated in the PR.

## 4. Tests (red first)

`tests/test_ingest_item_type.py`: back-create on unknown code; reuse on existing code
(case/whitespace-insensitive); absent / blank leave the link untouched; company isolation;
contract lists the field and the warning.
