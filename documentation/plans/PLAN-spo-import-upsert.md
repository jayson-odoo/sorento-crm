# PLAN — SPO import: upsert instead of skip duplicates

**Status:** Implemented + verified 2026-06-22. 7 pytest green (incl mixed-file task aggregation, AC-SPO-1..7).

## Problem

SPO Excel import skips any row whose `(spo_number, product_id, warehouse_id)` already
exists, emitting `"Skipped duplicate: SPO-x / product x / warehouse x"`. Re-uploading a
corrected SPO file does nothing — the existing allocation keeps its stale quantity.
Should **update** the existing allocation instead of skipping.

## Current behaviour

- `app/tasks/import_tasks.py` `process_spo_import()` groups rows by `(product_id, warehouse_id)`,
  sums qty into `allocated_quantity`, calls `SPOAllocationService.create_allocation()` per group.
- `app/services/procurement_service.py` `create_allocation()` raises `handle_conflict(...)` when
  `(spo_number, product_id, warehouse_id)` exists. DB unique constraint
  `uk_spo_allocations_spo_number_product_warehouse` enforces it.
- Import loop catches the conflict → `skipped_groups += 1` + generic "Skipped duplicate" error.

## Decisions (grilled)

1. **Quantity = overwrite with guard.** File is source of truth. Overwrite `allocated_quantity`
   with the new summed file value. **Guard:** if new `allocated_quantity < existing quantity_received`,
   do NOT overwrite — skip that row and report it as a real error (received-below-allocated is a
   data problem, must surface loud). _Not_ accumulate.
2. **Only touch `allocated_quantity`.** Leave `receipt_status`, `quantity_received`,
   `quantity_rejected`, `created_by`, `storage_zone_id`, `allocation_notes` untouched (file
   doesn't carry them reliably). Refresh shipment line statuses after update (same as create).
3. **No-op when unchanged.** If new qty == existing `allocated_quantity`, do nothing; do NOT count
   as updated. Only count rows whose qty actually changed.
4. **Reporting:** add `allocations_updated` counter. `allocations_created` = genuinely-new only.
   Guarded rows (new qty < received) → `errors[]` with explicit message
   (`"Allocation SPO-x / product x / warehouse x: new qty 5 < already received 8, skipped"`) and
   bump `skipped_rows_count`. **Drop** the old generic "Skipped duplicate" message — duplicates now
   update.

## Implementation

- **`procurement_service.py`:** add `upsert_allocation(allocation_data, created_by)` (or
  `update_allocation_quantity`) that:
  - looks up existing by `(spo_number, product_id, warehouse_id)`;
  - none → create (existing path), return `("created", row)`;
  - exists, new qty == current → return `("unchanged", row)`;
  - exists, new qty < `quantity_received` → raise a distinct guarded error (own exception/marker so
    the import loop classifies it, not a generic conflict);
  - exists, otherwise → set `allocated_quantity`, `updated_at`, commit, refresh shipment line
    statuses, return `("updated", row)`.
- **`import_tasks.py` `process_spo_import()`:** call the upsert; branch on the returned action to
  bump `created` / `updated` / `unchanged` / guarded-error counters. Build result with
  `allocations_created`, `allocations_updated`, `skipped_rows_count`, `errors[]`.
- Keep it all in one transaction-per-group as today.

## Tests (pytest)

- New allocation → created counter, row inserted.
- Existing, higher qty → updated counter, `allocated_quantity` overwritten, others untouched.
- Existing, identical qty → unchanged, no counter bump, no write.
- Existing with `quantity_received=8`, file qty `5` → guarded: not overwritten, error in `errors[]`,
  `skipped_rows_count` bumped.
- Mixed file (new + update + unchanged + guarded) → correct counters.
- Shipment line status refreshed after an update.

## Out of scope

- No change to the unique constraint (still `(spo_number, product_id, warehouse_id)`).
- No FE change beyond surfacing the new `allocations_updated` count in the import result toast/panel.
