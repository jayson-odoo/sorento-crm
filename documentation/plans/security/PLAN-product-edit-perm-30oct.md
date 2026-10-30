# PLAN: permission gates on the product write routes

Status: built, in review (full track, size S: RBAC change, no migration)
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

One more route writes a product outside this file: `PUT /marketing/promotions/{id}/products/{line_id}`
(`app/api/v1/marketing/promotions.py`) sets `products.list_price` when its body carries
`list_price` (`marketing_service.py` `update_promotion_product`). It now requires
`master_data.products.edit` when that value CHANGES; the promotions price editor always sends the
current list price back, so a promo-price-only edit keeps working without it (same rule as
`guard_chatbot_limits_edit`). Gating the route itself on a `marketing.promotion_products.*` slug
would change marketing access and is left as a follow-up.

Every other product mutation route is already gated: `family-code` / `family-code-reset` in the
same file, and the sibling routers `product_alternatives`, `product_attachments`,
`product_barcode_import`, `product_combos`, `product_companions`, `product_compatibility`,
`product_specifications`, `catalogue_photo_readings`, `product_sets`.

## Decision

Reuse the existing slugs (all registered in `app/rbac/permission_registry.py:203-206`) with the
existing `require_permission` dependency. No new slug, no migration.

Integrations are unaffected: these routes already required a staff session
(`get_current_user`), and `require_permission` resolves the same way, so an X-API-Key never
reached them before and still does not.

## Frontend

Gate the write actions on product screens with the existing `useHasPermission` hook
(`hooks/usePermissions.ts`): list Create product (`.add`), Import + Download template
(`.import`), bulk Chat search (`.edit`), bulk Delete (`.delete`, already enforced server-side by
the `product.delete` record action); record Edit button and Variants tab write buttons (`.edit`).
Row Delete in the record menu was already gated on `.delete` (`products/actions.tsx`).

## Who loses what

Roles are data, not code. The last measured snapshot of the dev copy of production is recorded in
`alembic/versions/414_product_set_grant_sweep.py`: `products.view` is held by 10 roles, and
`.add` / `.edit` / `.delete` by the same set minus `warehouse_executive`. So
`warehouse_executive` is the one provisioned role that can open the product screens but holds
no product write slug: it loses create / edit / delete / variant-link / field-link writes it
could make before. `admin` and `superadmin` bypass. Holders of `.import` and `.bulk_delete`
were not in that snapshot and need measuring on the live DB. `.bulk_delete` only guards the
direct `DELETE /products/bulk` route; the list's bulk Delete runs one `product.delete` record
action per row, which checks `.delete`.

## Tests

Backend `tests/test_product_write_gates.py` (24 tests: the 10 per-route 403 tests, the structural test and the
promotion list-price 403 test are red on main ff7231e9 and green after). Fixtures of six existing product test files now grant the slug their
writes need.
