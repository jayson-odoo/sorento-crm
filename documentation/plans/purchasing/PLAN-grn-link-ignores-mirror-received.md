# PLAN: GRN import links its lines even when the AutoCount mirror already stated the receipt

Status: In progress (lane `fix/grn-link-ignores-mirror-received`, issue #780)
UAC: `grn-link-ignores-mirror-received-acceptance-criteria.md`

## Journey

Purchasing imports a GRN sheet (AutoCount export) against an SPO. The AutoCount shipping-order
mirror has, minutes or days earlier, already pushed that SPO with its received quantities
(`stated_received`, `quantity_received`, `receipt_status = fully_received` on the
container-stamped allocations). The GRN's lines must still link to those allocations, the SPO
document must show the GRN behind each line, and the container must read Fully Received right
after the import - not the next time someone opens it.

## Measured facts (9 Sep 2026 03:00 UTC prod backup)

- GR-2026/09-0027 (SPO-2026/08-0126, imported 8 Sep 03:22 UTC): 17 picking lines, ALL
  `spo_allocation_id NULL`, `spo_number_raw` set. All 34 allocations on that SPO carried
  `stated_received = quantity_received = allocated_quantity` (container CMAU4932912).
  Container `inbound_shipments.updated_at` 8 Sep 01:19 (never touched by the import), lines
  `allocated / quantity_received 0`, header `in_transit`. Opening the detail page at 9 Sep 09:19
  UTC persisted `fully_received`.
- GR-2026/09-0024 (SPO-2026/08-0069): same, 12 allocations all stated received (UETU7480156).
- GRN on SPO-2026/08-0074 (imported 9 Sep 03:39 UTC): lines matched ONLY the allocations with
  `stated_received NULL` (no container, `receipt_status pending`); every container-stamped
  allocation (GCXU6137164) blocked its lines. Quantities tallied (325 + 4 = 329) so this is not
  a tally defect.

## Cause

1. `app/services/grn_spo_matching.py::build_allocation_pool` computes
   `external_received = max(0, quantity_received - linked_all)` and subtracts it from capacity.
   The mirror's `quantity_received` IS the GRN being imported, seen from AutoCount, so the
   receipt is counted twice. Link outcome depends on arrival order.
2. `app/services/procurement_service.py::PickingHeaderService.sync_grn_received_to_spo` walks
   linked lines only. Zero linked lines means zero containers refreshed. The listing and
   `crm_incoming_stock_list` read the stored `line_status` / `shipment_status`; only the detail
   GET (`packing_lists.py` get_packing_list) recomputes, via `refresh_shipment_line_statuses`,
   whose `get_received_quantities_by_product` DOES count orphan lines by SPO number.

## Ruling (owner, 9 Sep)

- A mirror statement (`stated_received`) is a reconciliation figure. It never consumes pool
  capacity. Capacity = allocated minus OTHER linked picking lines (excluding this GRN's own)
  minus only the part of the stored receipt that neither linked lines nor the statement explain.
- Received / Balance on the SPO document keep the mirror figure as a floor. D28c (`max` rule in
  `_sync_received_for_allocations`) already does this; do not touch it.
- The GRN import refreshes the containers under the header's SPO number as well, so a genuinely
  unlinked line (no allocation for that product) still updates the container.
- Existing orphans in prod are repaired with `scripts/backfill_grn_spo_allocation_links.py`
  (its pool is approved-linked-lines only and already ignores the stored column) after deploy,
  on the owner's go. No new script.

## Changes (backend only, no migration, no FE)

### B1. Pool ignores the mirror statement

`build_allocation_pool`, the `for allocation in matched:` loop:

```python
stated = int(getattr(allocation, "stated_received", 0) or 0)
external_received = max(0, int(allocation.quantity_received or 0) - stated - linked_all)
```

Rewrite the docstring paragraph that currently says an integration's write "must still consume
capacity": the mirror statement is the same GRN seen from AutoCount and is explained by the
picking lines once they link; only a stored receipt that is neither stated nor linked still
consumes (an n8n / external write with no line behind it, AC-FM-28 as it stands).

### A1. Import refreshes containers by SPO number

`app/tasks/import_tasks.py`, the post-import loop (`for header in headers_by_number.values():`
around line 2565): after `proc.sync_grn_received_to_spo(header.id)`, when `header.spo_number`
is set, also call `proc.sync_received_for_spo_number(header.spo_number)` inside the same
try/except. That is the call the forward matcher already makes at `grn_spo_matching.py:385`.
`sync_received_for_spo_number` keeps the stored value on allocations with no picking line
(D28), so it is safe for the mirror rows, and it refreshes every container under the SPO.

### Tests (Phase 2, test-first, `tests/test_grn_spo_forward_matching.py`)

Use the existing `world` fixture. The `world.allocation(...)` helper needs a `stated=` kwarg that
sets `stated_received` (add it; default None so every existing call is unchanged).

1. `test_a_mirror_stated_receipt_does_not_consume_capacity` - allocation quantity 100,
   `received=100`, `stated=100`, no picking lines. Pool available == [100].
2. `test_a_mirror_stated_receipt_is_explained_once_the_line_links` - same allocation, a linked
   approved line of 100 on GRN A. Pool for GRN B (no exclusion) is empty. Pool for GRN A
   (`exclude_header_ids={A}`) is [100].
3. `test_only_the_unexplained_part_of_a_stored_receipt_consumes` - quantity 100, `received=130`,
   `stated=100`, no lines. Available == [70]. (Keeps AC-FM-28 for a write that is neither
   stated nor linked.)
4. `test_a_grn_imported_after_the_mirror_statement_links_end_to_end` - allocation quantity 329,
   `received=329`, `stated=329`, then run the import-side draw (`build_allocation_pool` +
   `draw_fifo` for 329 at the allocation's warehouse) and assert one linked draw of 329 and no
   trailing unlinked draw. Then `_sync_received_for_allocations` / `sync_grn_received_to_spo`
   leaves `quantity_received == 329` (floor holds, no regression).
5. `test_the_import_refreshes_the_container_by_spo_number_when_nothing_links` - an inbound
   shipment with one line (product P, shipped 50), an allocation on it for product Q (so P has
   no allocation), a GRN header stating the SPO with an unlinked line for P of 50, approved.
   After the two sync calls A1 makes, the shipment line for P reads `received` and the header
   `fully_received`. Model the call the import task makes rather than running the whole task.
6. Existing `test_a_receipt_no_picking_line_explains_still_consumes` and
   `test_a_stored_receipt_its_own_lines_explain_is_not_counted_twice` stay green untouched.

Run: `venv/bin/pytest tests/test_grn_spo_forward_matching.py -q` (Postgres, `_pg_fixture`).
Never the full scm suite on the shared DB.

## Out of scope

- Any change to `_sync_received_for_allocations`, D28 rules, or the mirror ingest.
- A mismatch surface on the SPO line (stated != linked) - filed as a follow-up once this lands.
- Frontend. The "Unmatched" badge disappears because the FK is set.

## Prod repair after deploy (owner go required)

```
cd /opt/sorento-crm2/... && python scripts/backfill_grn_spo_allocation_links.py --dry-run --grn GR-2026/09-0027 --grn GR-2026/09-0024
```

then without `--dry-run`, then the same for the SPO-2026/08-0074 GRN and any other GRN whose
lines are all unlinked with an SPO stated (the script's default scope finds them).
