# Inventory — Read the stock ledger

The stock ledger is the immutable audit trail of every quantity change: what moved, by how much, the before/after, when, and who. It's append-only — you read it, you don't edit it.

## Where

Open [**Inventory Management → Stock Ledger**](/inventory-management/stock-ledger). The page is titled **Stock Ledger**.

Requires the `inventory.stock_ledger.view` permission to open. (The same movements for a single balance also appear in the **Stock Ledger** section of a [stock-balance detail page](understand-stock-levels.md).)

## The list

Newest entries first.

| Column | What it shows |
|--------|----------------|
| **Product** | Product code (with the product name beneath it). |
| **Warehouse** | The warehouse the movement hit. |
| **Type** | The transaction type — see below. |
| **Change** | The signed quantity change. Green `+N` for an increase, red `N` for a decrease. |
| **Previous** | On-hand quantity *before* the movement. |
| **New** | On-hand quantity *after* the movement. |
| **Created At** | When it happened (Malaysia time). |
| **Created By** | Who / what recorded it. |

## Transaction types

The values you'll see in **Type** today:

| Type | Meaning |
|------|----------|
| **BULK_IMPORT** | A balance was created or updated by a stock import (Excel / file). |
| **SYSTEM_ADJUSTMENT** | The system set a balance to `0` because the product was absent from a full-snapshot stock import. |

> These are the only two types the current code writes. If you see another value it came from a path added after this guide — treat the **Type** column as the source of truth, and flag unfamiliar values to your admin.

Each entry also carries (visible on the balance detail page / export) a `reference_type` and `reference_id` linking back to what caused the change (e.g. `bulk_import`, `stock_snapshot_import`) and a free-text **Notes** field.

## Filtering and searching

The ledger filters are exact-match text inputs (not dropdowns):

* **Product ID** — placeholder `Product ID`.
* **Warehouse ID** — placeholder `Warehouse ID`.
* **Transaction type** — placeholder `Transaction type` (e.g. `BULK_IMPORT`).
* **Clear filters** — appears when any filter is set.

## Toolbar

* **Export** — downloads the ledger as `stock_ledger_export.xlsx`.
* A **Refresh** control reloads the list.

## What's captured

Per entry: `product_id`, `warehouse_id`, `transaction_type`, `quantity_change`, `previous_quantity`, `new_quantity`, `reference_type`, `reference_id`, `notes`, `created_by`, `created_at`.

## See also

* [Inventory — Understand stock levels](understand-stock-levels.md)
* [Warehouse — Upload stock balances](../warehouse/upload-stock.md) — the flow that writes `BULK_IMPORT` entries.
