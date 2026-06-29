# Inventory — Manage storage zones

Storage zones subdivide a warehouse into named areas (shelves, racks, bins, pallets) with a capacity. They give you a finer location than "the whole warehouse" when you want it.

## Where

Open [**Inventory Management → Storage Zones**](/inventory-management/storage-zones). The page is titled **Storage Zones**.

Requires the `inventory.storage_zones.view` permission to open.

## The view

Unlike the other inventory pages this is a **tree**, not a flat DataGrid. Zones are grouped under their warehouse; each warehouse row carries a **{count} zones** badge and expands to show its zones. While the tree loads you'll see **Loading zones...**.

Each zone row shows:

* A **zone type** badge — one of **Shelf**, **Rack**, **Bin**, or **Pallet**.
* The zone name (or zone code if no name is set).
* **Capacity: {capacity} | Utilization: {utilization}%**.
* On hover: **Edit** and **Delete**.

## Create or edit a zone

1. Click **Create Zone**.
2. Fill in the dialog:
   * **Warehouse \*** — a dropdown (placeholder *"Select warehouse"*); options are listed as *{warehouse name} ({warehouse code})*. Required.
   * **Zone Code \*** — placeholder `ZONE-001`. Required. Must be unique within the warehouse.
   * **Zone Name** — placeholder `Enter zone name`. Optional.
   * **Zone Type \*** — a dropdown: **Shelf**, **Rack**, **Bin**, **Pallet**. Required.
   * **Capacity \*** — a number. Required.
3. Click **Create** (new) or **Update** (edit). **Cancel** discards.

A zone code only has to be unique **within its warehouse** — two warehouses can both have `ZONE-001`.

## What's captured

Per zone: `warehouse_id` (the parent warehouse), `zone_code`, `zone_name`, `zone_type`, `capacity`, `created_at`.

> Note: the backend stores `zone_type` as free text, so legacy or imported zones may show a value other than the four the form offers (Shelf / Rack / Bin / Pallet). New zones created through this form are limited to those four.

## See also

* [Inventory — Manage warehouses](manage-warehouses.md)
* [Inventory — Understand stock levels](understand-stock-levels.md)
