# Listing Column Preferences

This feature lets each user personalize every listing table by:

- Hiding/showing columns (where the column is hideable)
- Reordering columns
- Pinning/movability/sizing behavior depends on the specific `DataGrid` table setup

Preferences are persisted server-side per user and per `listing_key`.

## `listing_key` (stable personalization key)

### Frontend default

`DataGrid` derives the `listing_key` as:

1. `listingKey` prop (if provided)
2. Otherwise `usePathname()` (the current route pathname)

So if a listing component does not pass `listingKey`, personalization is scoped to the exact route.

### Backend authorization + supported formats

The backend authorizes the column-config endpoints using the `listing_key` itself.
The repository expects `listing_key` to be either:

1. An RBAC view permission slug, for example: `order_management.orders.view`
2. A composite key using `::`:
 - `<permission_slug>::<stable_listing_id>`
 - Example: `order_management.orders.view::orders-list`

If the `<permission_slug>` portion does not exist in the RBAC catalog, the backend treats the key as "module-auth only" and does not perform fine-grained permission checks.

## What gets stored

For each user + `listing_key`, the backend stores:

- `config.version` (currently written as `1`)
- `config.columnOrder`: ordered list of visible/movable column ids (or `null`)
- `config.columnVisibility`: map of hideable column ids to booleans

The payload is stored in `user_list_column_configs.config` (JSONB).

## API endpoints

These endpoints are implemented under:

- `GET    /api/v1/list-query/column-config/{listing_key}`
- `PUT    /api/v1/list-query/column-config/{listing_key}`
- `DELETE /api/v1/list-query/column-config/{listing_key}`

All endpoints require the user to be authenticated; authorization is based on the `listing_key` rules above.

