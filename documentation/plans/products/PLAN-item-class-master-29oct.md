# PLAN - ITEM-CLASS-MASTER: AutoCount ItemClass as an ingest master (contract 2.11)

**Status:** Build (small fix track: backend only, no migration, no auth/RBAC change, the ingest
surface gains one entity on the existing door). CRM branch is based on #1972
(`claude/item-class-sync-rbac-4sehj5`, head 7a0c583b) because #1972 is not merged yet; rebase
after it merges.

**UAC:** `item-class-master-acceptance-criteria.md` (alongside).
**Origin:** owner 29 Oct ~23:35 "we should be able to sync the product class also right from
hapi /api/db1/itemclass"; design = #1972 crew-note section B
(https://github.com/jayson-odoo/sorento-crm/pull/1972#issuecomment-6501598039).
**Precedent copied one for one:** `documentation/plans/autocount/PLAN-autocount-brands-ingest.md`
(contract 2.3).

## 1. Journey

The shared service reads each AutoCount company's ItemClass list (`/api/db1/itemclass`,
`/api/db2/itemclass`, read only) and pushes it to the CRM as entity `item_classes` BEFORE brands
and products, on the existing master cadence and on the on-demand run. Every class then exists as
a proper master row with its AutoCount description and an integration reference, instead of only
the code = name placeholder a product push back-creates (#1972). A class retired in AutoCount
goes inactive through `/ingest/item_classes/deletions`. The SS gates on `GET /external/contract`
reporting `2.11` with `item_classes` in `entities`; a 2.10 CRM simply never lists it.

Wire shape (field names of hapi itemclass to be confirmed by crew; the CRM side is canonical):

```json
{"companyCode": "SRT", "records": [
  {"source_ref": "SRT:SERENE", "code": "SERENE", "name": "SERENE",
   "description": "Serene series", "is_active": true}
]}
```

## 2. Measured facts (lane base = #1972 head 7a0c583b merged on main c97eda27)

| Fact | Where |
| --- | --- |
| `item_classes` table: code String(50), name String(150), description Text, is_active NOT NULL, CompanyScopedMixin, unique (company_id, item_class_code) | `sorento_crm_backend/app/models/product.py:189-212` |
| `CanonicalBrand` sizes to the brands columns 50/150 | `app/schemas/canonical_masters.py:79-92` |
| `brands` EntitySpec + `_brand_columns` + NOT NULL default table | `app/services/master_ingest_service.py:382-385, :353, :707` |
| Default adoption = `resolve_master_by_code`: `upper(btrim())` both sides, company-filtered. `ItemClass` is already in the code/name maps | `app/services/rules/master_rules.py:41, :52`; `master_ingest_service.py:1196-1201` |
| Product push back-creates classes via `ensure_reference` (code = name, description "Auto-created by product import") | `master_ingest_service.py:620-633`; `app/services/rules/product_rules.py:152-215` |
| INGEST / READ / DELETE permission maps, `CONTRACT_VERSION = "2.10"` | `app/api/v1/external/ingest.py:113-200, :337` |
| Integration reference allowlist | `app/services/integration_reference_service.py:56-82` |
| Read door columns | `app/services/master_read_service.py:85-101` |
| Deletion: hard delete when the catalogue probe finds no referrer, else deactivate | `app/services/deletion_service.py:128-155, :400-450` |
| `respond_contacts.brand_class_ids` (JSONB, #1972) holds class ids; the FK catalogue probe cannot see it | `app/models/access.py`, `app/services/contact_brand_scope.py` |
| `master_data.item_classes.{view,add,edit,delete}` slugs exist (#1972 migration grants them wherever the brands slug is held) | `alembic/versions/item_class_0001.py` |

## 3. Decisions

- **D1 Canonical shape.** `CanonicalItemClass`: code (1..50), name (1..150), description,
  is_active (absent vs null, D14). Same as `CanonicalBrand`.
- **D2 EntitySpec** `item_classes` next to `brands` (`code_column = item_class_code`), default
  adoption (case and whitespace insensitive by code, company scoped). A row #1972's product push
  created is adopted and claimed, never duplicated.
- **D3 AutoCount is master** for code, name, description and is_active (the brands rule): a sync
  overwrites what the Item Classes screen edited. A blank description clears the placeholder
  "Auto-created by product import".
- **D4 Permissions:** ingest `master_data.item_classes.edit`, read `.view`, deletions `.delete`.
  No new slug, no migration.
- **D5 Deletions always deactivate, never hard delete.** A class can be named in a contact's
  `brand_class_ids` JSONB, which the referrer probe cannot see; a hard delete would leave a
  dangling id there (and the CRM screen refuses that delete with 409 for the same reason).
  `is_active = false`, row and reference kept, re-push reactivates (AutoCount is master).
- **D6 Contract 2.11**: `item_classes` joins `entities`; `fields_added.item_classes` lists the
  record keys. Additive.
- **D7 No per-brand mapping** in the master: AutoCount ItemClass is flat. The Brands card keeps
  offering, per brand, the classes its products carry (#1972, unchanged).
- **D8 Shared service** (`jayson-odoo/foundryx-shared-service`): read `/api/db{1,2}/itemclass`
  read only like ItemBrand, map to the shape above, push `item_classes` before brands/products on
  the master cadence + on-demand run, gate on contract >= 2.11. Not reachable from this sandbox
  (only sorento-crm is in scope); needs a session with that repo.

## 4. Tests (red first)

`tests/test_ingest_item_classes.py`, copy of `test_ingest_brands.py` scoped to the ACs below,
plus the contract test (`entities`, version, `fields_added`).

## 5. Out of scope

Any FE change; per-brand class mapping; a CRM-side schedule.
