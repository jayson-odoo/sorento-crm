# Domain modules (incremental layout)

**Catalog (source of truth for the App Store UI and install resolver):** PostgreSQL table
`app_modules_catalog` - `module_key`, `display_name`, `description`, `dependencies` (JSON array of
keys), `sort_order`, `is_core`. Change those columns to update names, copy, dependency edges, and
ordering without a deploy.

**Bootstrap:** `app/modules/runtime/module_manifest.py` seeds **missing** catalog rows. **Bundles**
live in PostgreSQL table `app_module_bundles` (`bundle_key`, `display_name`, `module_keys` JSON
array, `sort_order`). Migration `099_module_bundles` seeds the former `MODULE_BUNDLES` defaults;
`MODULE_BUNDLES` in code is only a **fallback** if the table is empty or a key has no row.

`app/modules/<name>/bootstrap.py` files are **compatibility placeholders** for a future move of
`api`, `services`, and `schemas` into module-oriented folders. Existing imports and URL paths stay
unchanged until that migration is done feature-by-feature.
