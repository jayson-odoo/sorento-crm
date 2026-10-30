# PLAN: permission gates on the product write routes

Status: in progress (full track, size S: RBAC change, no migration)
UAC: `product-edit-perm-acceptance-criteria.md`
Lane: PRODUCT-EDIT-PERM

## Problem

Ten write routes in `sorento_crm_backend/app/api/v1/master_data/products.py` depend on
`get_current_user` only (verified at origin/main ff7231e9), so they are gated by login plus the
`master_data` module guard but not by any `master_data.products.*` permission:

| Route | Line | Gate after this lane |
| --- | --- | --- |
| `POST /products/` | 307 | `master_data.products.add` |
| `PUT /products/bulk` | 330 | `master_data.products.edit` |
| `PUT /products/{id}` | 346 | `master_data.products.edit` |
| `POST /products/bulk-import` | 368 | `master_data.products.import` |
| `DELETE /products/bulk` | 429 | `master_data.products.bulk_delete` |
| `DELETE /products/{id}` | 446 | `master_data.products.delete` |
| `PUT /products/{id}/variant-parent` | 467 | `master_data.products.edit` |
| `DELETE /products/{id}/variant-parent` | 489 | `master_data.products.edit` |
| `POST /products/{id}/variant-reset` | 509 | `master_data.products.edit` |
| `POST /products/{id}/attachments/{aid}/field-links` | 595 | `master_data.products.edit` |

Every other product mutation route is already gated: `family-code` / `family-code-reset` in the
same file, and the sibling routers `product_alternatives`, `product_attachments`,
`product_barcode_import`, `product_combos`, `product_companions`, `product_compatibility`,
`product_specifications`, `catalogue_photo_readings`, `product_sets`.

## Decision

Reuse the existing slugs (all registered in `app/rbac/permission_registry.py:203-206`) with the
existing `require_permission` dependency. No new slug, no migration.

## Frontend

Gate New / Edit / Delete / bulk actions / import on product screens with the existing
`useHasPermission` hook (`hooks/usePermissions.ts`).
