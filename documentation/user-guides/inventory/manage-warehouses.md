# Inventory — Manage warehouses

Warehouses are the storage locations stock is held against. Every stock balance, batch, and ledger entry is tied to exactly one warehouse. Use this page to create, edit, and deactivate them.

## Where

Open [**Inventory Management → Warehouses**](/inventory-management/warehouses). The page is titled **Warehouses**.

Requires the `inventory.warehouses.view` permission to open.

## The list

The DataGrid shows one row per warehouse with these columns:

| Column | What it shows |
|--------|----------------|
| **System Location** | The warehouse code (the unique system identifier). |
| **System Location Description** | The warehouse's descriptive name. |
| **Warehouse** | The physical location / address. |
| **Zones** | How many storage zones are defined under this warehouse. |
| **Status** | **Active** or **Inactive**. |

Toolbar:

* **Create Warehouse** — opens the new-warehouse page.
* **Import** — bulk-create warehouses from a file.
* **Delete** — bulk-delete the selected rows (appears when rows are checked; confirmation required).

## Create or edit a warehouse

1. Click **Create Warehouse** (or **Edit** on a warehouse detail page).
2. Fill in the form:
   * **System Location \*** — the warehouse code. Placeholder `WH-001`. The form notes *"Must be unique."* Required.
   * **System Location Description** — the descriptive name. Placeholder `e.g. Selangor Main DC`.
   * **Warehouse** — physical location / address. Placeholder `Warehouse name / address`.
   * **Active Status** — a toggle. The form notes *"Inactive warehouses will not appear in dropdowns"*.
3. Click **Create Warehouse** (new) or **Update Warehouse** (edit). **Cancel** discards.

## The detail page

Click a row to open the warehouse detail page. The header shows the warehouse name (or code) with its **Active** / **Inactive** badge and the subtitle **System Location: {code}**.

The **Basic Information** card lists: **System Location**, **System Location Description**, **Warehouse**, **Status**, **Created**, and **Last Updated**. Toolbar actions: **Edit** and **Delete**.

## Active vs. inactive

`is_active` controls whether the warehouse appears in pickers elsewhere in the app. Deactivating is **not** a delete — existing stock, batches, and ledger rows keep their warehouse link; the warehouse simply stops appearing in dropdowns. Use **Delete** (hard delete, with confirmation) only to remove a warehouse entirely.

## What's captured

Per warehouse: `warehouse_code`, `warehouse_name`, `location`, `manager_id` (optional), `is_active`, `created_at`, `updated_at`.

## See also

* [Inventory — Manage storage zones](manage-storage-zones.md) — subdivide a warehouse into zones.
* [Inventory — Understand stock levels](understand-stock-levels.md)
