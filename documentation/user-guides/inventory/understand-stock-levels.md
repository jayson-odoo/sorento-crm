# Inventory - Understand stock levels

The **Stock** page is the live balance of every product in every warehouse - one row per **(product, warehouse)** pair. This guide explains the columns, the status badge, the filters, and the per-balance detail page. To load balances from a spreadsheet, see [Warehouse - Upload stock balances](../warehouse/upload-stock.md).

## Where

Open [**Inventory Management → Stock**](/inventory-management/stock). The page is titled **Stock**.

Requires the `inventory.stock.view` permission to open.

## The list

| Column | What it shows |
|--------|----------------|
| **Product Code** | The product's code. |
| **Product Name** | The product's name. |
| **Category** | The product's category. |
| **Warehouse** | Which warehouse this balance is held in. |
| **Available** | On-hand minus reserved (`quantity_available`). This is what can actually be committed. |
| **Reserved** | Quantity already allocated to orders (`quantity_reserved`). |
| **Total** | Physical on-hand quantity (`quantity_on_hand`). |
| **Reorder Level** | The product's reorder threshold, used to decide the status. |
| **Status** | A coloured badge - see below. |

**Available** is a derived value computed by the database (`Total − Reserved`); it is never edited directly.

### Status badge

The status is computed from **Available** versus the product's reorder level:

| Status | Meaning |
|--------|----------|
| **Critical** | Available is `0` or below. |
| **Low** | Available is above 0 but below the reorder level. |
| **Normal** | Available is at or above the reorder level (and not overstocked). |
| **Overstock** | Available is more than twice the reorder level. |

## Filtering and searching

* **Search stock...** - searches product code and product name.
* **Warehouse** - a dropdown; default **All warehouses**, then one entry per warehouse.
* **Status** - a dropdown: **All statuses**, **Critical**, **Low**, **Normal**, **Overstock**.
* **Clear filters** - appears when a filter is active.

## Toolbar

* **Import** - bulk-create / update balances from an Excel file. Full steps: [Warehouse - Upload stock balances](../warehouse/upload-stock.md).
* **Export** - downloads the current balances as `stock_balance_export.xlsx` (use it as your import template).
* **Stock List** - generates the Stock List attachment. It is disabled until a stock file has been imported; the disabled tooltip reads *"Import a stock file to create the Stock List attachment"*.
* **Delete** - bulk-delete selected rows (only shown to users with `inventory.stock.delete`; confirmation required).

## The stock-balance detail page

Click a row to open the balance detail page (URL `/inventory-management/stock/{productId}/{warehouseId}`). The heading is **Stock Balance**. If the pair has no record you'll see **Stock record not found** with a **Back to Stock** button.

Sections:

* **Product** - product name and code.
* **Warehouse** - the warehouse name.
* **Quantities** - **On Hand**, **Available**, **Reserved**, and **Damaged** (`quantity_damaged`).
* **Stock Ledger** - every movement against this balance, newest first, with columns **Type**, **Change** (green for positive, red for negative), **Previous**, **New**, **Created By**, **Created At**, **Notes**. See [Inventory - Read the stock ledger](read-the-stock-ledger.md).

## How balances change

There is no manual "edit balance" form - balances move through imports and system adjustments, and every change is recorded as a stock-ledger entry. The unique key `(product, warehouse)` guarantees one balance row per pair.

## Permissions

* `inventory.stock.view` - open the page.
* `inventory.stock.export` - run **Export**.
* `inventory.stock.import` - run **Import**.
* `inventory.stock.delete` - bulk-delete balances.

## See also

* [Warehouse - Upload stock balances](../warehouse/upload-stock.md)
* [Inventory - Read the stock ledger](read-the-stock-ledger.md)
* [Inventory - Stock batches and expiry](stock-batches-and-expiry.md)
