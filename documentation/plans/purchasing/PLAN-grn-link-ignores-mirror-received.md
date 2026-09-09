# PLAN: GRN import links its lines even when the AutoCount mirror already stated the receipt

Status: Tests green, review round 2 pending (lane `fix/grn-link-ignores-mirror-received`, issue #780)
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
  `stated_received` is written by more than the AutoCount mirror push (`app/models/procurement.py`
  around line 521): the supersede/dedupe carry and the retire freeze write it too, and the pool
  widening covers all of them, not the mirror push alone.
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
stated = int(allocation.stated_received or 0)
external_received = max(0, int(allocation.quantity_received or 0) - stated - linked_all)
```

Rewrote the docstring paragraph that used to say an integration's write "must still consume
capacity": the mirror statement is a statement recorded on the allocation (AutoCount mirror
push, supersede carry, retire freeze - `app/models/procurement.py` around line 521), the same
GRN the pool is trying to place, and is explained by the picking lines once they link; only a
stored receipt that is neither stated nor linked still consumes (an n8n / external write with
no line behind it, AC-FM-28 as it stands).

### B2. Import upsert adopts the orphan row in place (review round 2, B1 blocker)

`PickingHeaderService.upsert_grn_line_for_import` (`procurement_service.py`) used to match a
draw's row on the exact tuple `(header, product, source_warehouse, spo_allocation_id)`. Once
B1 lets the pool hand a re-import's draw a REAL allocation id, that tuple can never match the
ORPHAN row already sitting on the header - unlinked, `spo_allocation_id IS NULL` - that a
previous import left because the pool could not place it at the time (the exact prod shape:
mirror-stated, unlinked). The exact-match miss inserted a SIBLING instead of linking the
orphan in place: a re-imported 100-unit GRN read two lines, picked 200, and the container
reported 200 received.

Fix: when the draw carries an allocation id and no exact match exists, adopt an unlinked row
for the same `(header, product, warehouse)` - set its `spo_allocation_id` and let the
fall-through below write its quantity - the same "link in place, don't duplicate" outcome
forward matching produces. A later draw of a genuine split then finds no more unlinked rows
to adopt and correctly creates a new one.

Guard (review round 2, B3 blocker): the adoption candidate is ALSO confined to what the draw's
OWN SPO number claims. A multi-SPO GRN groups its rows by `(doc_no, product, effective_spo)`
(`import_tasks.py`), so one header/product/warehouse can carry an unlinked row stating SPO-A
next to a linked draw for SPO-B in the SAME import; without the guard the SPO-B draw adopted
SPO-A's orphan and overwrote its quantity, destroying it. The candidate query adds
`or_(PickingLine.spo_number_raw.is_(None), _spo_match_key_sql(PickingLine.spo_number_raw) ==
_spo_match_key(spo_number_raw))` (`_spo_match_key_sql` imported from `grn_spo_matching` INSIDE
the function - module-level would be circular, since `grn_spo_matching` imports from
`procurement_service`), plus `.order_by(created_at.asc(), id.asc())` for a deterministic pick
among several eligible orphans.

### A1. Import refreshes containers by SPO number, once per distinct SPO

`app/tasks/import_tasks.py`, the post-import loop (`for header in headers_by_number.values():`
around line 2566): `proc.sync_grn_received_to_spo(header.id)` still runs per header, in its own
try/except with `db.rollback()` on failure. `sync_grn_received_to_spo` walks the header's OWN
linked lines only, so a GRN whose line could not link at all (no allocation for that product)
refreshes nothing through it; `sync_received_for_spo_number` finds the allocations by SPO
NUMBER instead - the same call the forward matcher makes when `linked_lines or created_lines`
(`grn_spo_matching.py`), unconditional here since this loop has no such count to gate on.

`spo_allocations` is ~80k rows and this call materialises every allocation under one SPO
number, so it is NOT called inside the per-header loop: the loop collects
`{_spo_match_key(header.spo_number): (header.spo_number, company_id)}` (read BEFORE the header's
own sync call, not after - a failed sync rolls the session back and expires the header
instance) and, after the loop, `sync_received_for_spo_number` runs once per distinct key, each
in its own try/except with `db.rollback()` on failure.

### A2. `sync_received_for_spo_number` gains a `company_id` kwarg (review round 2, S1)

`sync_received_for_spo_number(spo_number, *, released_allocation_ids=None, company_id=None)`.
When given, `company_id` narrows the query with an explicit
`SPOAllocation.company_id == str(company_id)` filter, the same shape as
`build_allocation_pool`'s - IN ADDITION to the ambient `CompanyScopedMixin` auto-filter
(`do_orm_execute`), not instead of it; it only replaces the redundant explicit
`build_company_predicate(SPOAllocation, get_company_scope(self.db))` call this method already
made. A1's caller states the import job's own company (a job with no company snapshot runs
system-scoped - "all companies" - where the ambient auto-filter constrains nothing) rather than
let this sweep touch another company's allocations under the same SPO number.

### Tests (Phase 2, test-first, `tests/test_grn_spo_forward_matching.py`)

Use the existing `world` fixture. The `world.allocation(...)` helper gained `stated=` (sets
`stated_received`) and `source_system=` kwargs (both default `None`, every existing call
unchanged).

1. `test_a_mirror_stated_receipt_does_not_consume_capacity` - allocation quantity 100,
   `received=100`, `stated=100`, no picking lines. Pool available == [100].
2. `test_a_mirror_stated_receipt_is_explained_once_the_line_links` - same allocation, a linked
   approved line of 100 on GRN A. Pool for GRN B (no exclusion) is empty. Pool for GRN A
   (`exclude_header_ids={A}`) is [100].
3. `test_only_the_unexplained_part_of_a_stored_receipt_consumes` - quantity 100, `received=130`,
   `stated=100`, no lines. Available == [70]. (Keeps AC-FM-28 for a write that is neither
   stated nor linked.)
4. `test_a_grn_imported_after_the_mirror_statement_links_end_to_end` - allocation quantity 329,
   `received=329`, `stated=329`, `source_system="autocount"` (the D28c floor only applies on
   that branch), then run the import-side draw (`build_allocation_pool` + `draw_fifo` for 329 at
   the allocation's warehouse) and assert one linked draw of 329 and no trailing unlinked draw.
   Then `sync_grn_received_to_spo` leaves `quantity_received == 329` (floor holds, no
   regression).
5. `test_the_import_refreshes_the_container_by_spo_number_when_nothing_links` (AC-MR-5) - drives
   the REAL import task (`_import_grn_lines`/`process_grn_lines_import`), not a model of its
   calls. An allocation's whole 50 units are already spoken for by an unexplained external
   receipt (AC-FM-28, `received` with no picking line and no mirror statement) before the
   import runs, so the pool has zero capacity left and this GRN's own line draws unlinked - the
   "could not link at all" case A1 exists for. Asserts the shipment line reads `received` and
   the header `fully_received` after the real import; disabling the `sync_received_for_spo_number`
   call makes it fail (proven in review round 2).
6. `test_re_importing_an_orphan_grn_links_in_place_instead_of_doubling` (AC-MR-9, B1/B2 blocker,
   review round 2) - one approved header with an orphan line (`spo_allocation_id IS NULL`,
   `spo_number_raw` set), a mirror-stated allocation (`stated=100, received=100,
   source_system="autocount"`), re-import the SAME sheet through `_import_grn_lines`. Asserts
   exactly one line, picked 100, linked to the allocation, and the container's received-by-product
   totals 100 (not 200).
7. `test_adoption_never_steals_an_orphan_that_states_another_spo` (AC-MR-10, B3 blocker, review
   round 2) - one header/product/warehouse, two sheet rows naming DIFFERENT SPOs (a multi-SPO
   GRN), only the second SPO has an allocation. Asserts two lines, total picked 100, and the
   unlinked line still carries the FIRST SPO's `spo_number_raw` (not overwritten by the second
   SPO's draw).
8. Existing `test_a_receipt_no_picking_line_explains_still_consumes` and
   `test_a_stored_receipt_its_own_lines_explain_is_not_counted_twice` stay green untouched.

Run: `venv/bin/pytest tests/test_grn_spo_forward_matching.py tests/test_grn*.py
tests/test_spo_xlsx_supersede.py tests/test_spo_import_upsert.py -q` (Postgres, `_pg_fixture`).
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
