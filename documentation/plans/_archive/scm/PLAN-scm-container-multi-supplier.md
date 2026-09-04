# PLAN: multi-supplier container and the consolidated Sorento packing list

**Status:** implemented, PR #208 open (2026-08-17); browser evidence run not recorded (no agent stack slot in this lane; vitest-only, stated in PR)
**Origin:** `scm-fulfilment-gap` report, section 3 step 4 and gap G4; captain decision
`decision-container-identity-multi-supplier.md` (combine, never replace; identity model left to
engineering).
**Out of scope here:** proforma invoice as a document and prices on lines (`scm-proforma-first-class`),
PI-vs-PO validation (`scm-proforma-po-validation`), loading-plan scoring (another lane).

## Journey (Phase 0)

Actor: Sorento purchasing (Ms Tee), at `/scm/incoming`.

1. She picks supplier Kailu, uploads Kailu's packing list for container FSCU8103365. The container
   appears in "Containers read" with Kailu's lines.
2. She picks supplier Caizhou, uploads Caizhou's packing list for the SAME container. The container
   now holds Kailu's lines AND Caizhou's lines. Nothing was lost. (Today Kailu's lines vanish.)
3. Kailu sends a corrected list. She re-uploads it as Kailu. Kailu's lines are replaced by the new
   ones; Caizhou's are untouched.
4. She clicks the container and sees the **Sorento packing list**: one table, grouped by factory
   (supplier) with a subtotal per factory, a grand total, the SORENTO / MOCHA split, and a remarks
   column that already says where the shipment differs from the loading plan we sent that supplier
   ("Loading plan asked 500, packed 420 (short 80)", "Not on the loading plan") plus whatever remark
   the supplier wrote on the line. She can download it as `.xlsx` in the shape of the file she used
   to build by hand.

What she never types: the factory (it is the supplier she uploaded as), the discrepancies (derived
from the supplier notice), the company split (derived from the product's brand).

## Identity model (the engineering call)

**Additive per-supplier lines under ONE `inbound_shipments` row per container.** Not a parent
container entity.

Why: everything downstream keys on "the shipment for container X" - container status import
(`container_status_service._shipments_by_container_key`, oldest wins), external SPO allocations
("Packing list not found for shipping_container_number"), clearance fields, `spo_number =
shipment_number`, GRN receiving. A parent entity would either duplicate the clearance columns per
child or move them to a new table; both are far larger than the data-loss fix and would collide
with `scm-proforma-first-class`. Per-supplier lines keep the container as the one row and add the
missing fact - whose lines these are - where it belongs.

Concretely:

- `inbound_shipment_lines.supplier_id` (nullable FK suppliers, SET NULL). Backfilled from the header
  on migration so every existing line is owned by the supplier its shipment already names.
- Line identity becomes `(shipment_id, product_id, supplier_id)` with NULL supplier a key of its
  own (`NULLS NOT DISTINCT`, PG 15+; local 17, CI pg16, prod 15). Replaces
  `uk_inbound_shipment_lines_shipment_product`.
- **Replace rule in `InboundShipmentService.create_shipment` (update-in-place branch):**
 - the effective supplier of an incoming line is `line.supplier_id or payload.supplier_id`;
 - if the payload states a supplier anywhere (header or any line), an existing line is deleted
    before insert when EITHER its `supplier_id` is in the set of incoming effective suppliers, OR
    it has no supplier at all and its `product_id` is among the incoming lines' products. The
    second arm is what stops n8n's unattributed read of a container and the factory's later Excel
    upload of the same goods standing as two rows and doubling the quantity. An unattributed line
    for a product the upload says nothing about is a different item nobody has claimed, and stays;
 - if the payload states NO supplier at all (n8n PDF path, legacy callers) the behaviour is
    unchanged: every line is replaced. An upload that does not say whose it is speaks for the whole
    container, as it always did.
 - Merge-by-product within one payload becomes merge-by-(product, supplier).
- Header `supplier_id`: TOTAL, and re-derived after every write that touches the lines
  (`create_shipment` both branches, `update_shipment` when it replaces lines). No lines at all ->
  whatever the payload stated (which may be nothing); exactly one distinct non-null supplier across
  the lines -> that supplier; anything else (two or more, or every line unattributed) -> NULL.
  Derived, never lies - in particular an n8n resend that names no supplier empties a header that
  used to name one, instead of leaving a claim no line supports.
- **`packing_list_service.apply` requires `supplier_id`,** and `POST /packing-lists/apply` returns
  422 without it on the writing path (`validate_only=true` writes nothing and may omit it). A
  packing list arrives from one factory; an upload that will not say which one is indistinguishable
  from a statement about the whole container and would delete the other factories' lines.
- Header `total_items_shipped` / `total_cartons`: unchanged (display already sums lines).
- Known limit, stated in the PR: SPO allocation and GRN quantities are per `(shipment, product)`,
  so if two suppliers ship the SAME product code in one container, `refresh_shipment_line_statuses`
  stamps the product's WHOLE allocated / received total onto EVERY line of that product - both
  lines display the full allocation, and both can flip to `received` when only one shipped against
  the order. (Where a single line has to be picked instead - the incoming-cost capture and the
  external GRN lookup - the pick is now ordered by `created_at, id` so it is at least the same line
  every time.) Not observed in any real file; not fixed here.

Also on the line: `cbm` Numeric(12,4) nullable (reader already parses `cbm_total` / `cbm_per_unit`
and threw it away; the consolidated list needs volume for the split) and `remarks` Text nullable
(the supplier's own `备注`).

## Part 1 - stop destroying data (land first)

Backend only.

1. Migration `374_shipment_line_supplier` (id 26 chars, <= 32). `down_revision` = BOTH current
   heads (`373_merge_372_flyer_specs`, `373_merge_media_into_main`) so the graph has one head
   again. Ops: add `supplier_id`, `cbm`, `remarks`; index on `supplier_id`; backfill
   `UPDATE inbound_shipment_lines l SET supplier_id = s.supplier_id FROM inbound_shipments s WHERE
   l.shipment_id = s.id AND s.supplier_id IS NOT NULL AND l.supplier_id IS DISTINCT FROM
   s.supplier_id` (set-where-mismatch, not set-where-NULL, so a re-run corrects a bad one); drop constraint
   `uk_inbound_shipment_lines_shipment_product`; `CREATE UNIQUE INDEX
   uk_inbound_shipment_lines_ship_prod_sup ON inbound_shipment_lines (shipment_id, product_id,
   supplier_id) NULLS NOT DISTINCT`. Downgrade reverses (merge dupes by product first, as 055 did)
 - minus 055's allocation-reassignment step: `spo_allocations.inbound_shipment_lines_id` was
   dropped by migration 126, so a merged-away line orphans nothing.
2. `app/models/procurement.py::InboundShipmentLine`: the three columns, `supplier` relationship,
   `__table_args__` swaps the UniqueConstraint for
   `Index("uk_inbound_shipment_lines_ship_prod_sup", "shipment_id", "product_id", "supplier_id",
   unique=True, postgresql_nulls_not_distinct=True)`.
3. `app/schemas/procurement.py`: `InboundShipmentLineBase` gains `supplier_id`, `cbm`, `remarks`
   (all Optional). Response exposes them.
4. `app/services/procurement_service.py::create_shipment`: replace rule above, in BOTH the
   update-in-place branch and the create branch's merge (merge key `(product_id, supplier_id)`;
   effective supplier defaulted onto each line dict before insert). Header supplier derivation
   after write. Keep `_already_existed`.
5. `app/services/scm/packing_list_service.py::apply`: every line carries
   `supplier_id=supplier_id`, `cbm=ln.cbm_total or (ln.cbm_per_unit * qty)`, `remarks=ln.remark`.
   `results[]` unchanged.
6. `app/services/scm/allocation_suggestion_service.py`: candidates per line use
   `line.supplier_id or shipment.supplier_id` (group lines by supplier and call `_candidates` per
   group, or pass per-line supplier). Response `supplier_id` per line if the FE needs it; header
   `supplier_id` stays.
7. `GET /inbound-shipments` (`fulfilment.py`): `supplier_id` filter = header match OR any line with
   that supplier; each row gains `suppliers: [{supplier_id, supplier_code, supplier_name}]`. That
   OR is ONE shared helper, `procurement_service.shipment_supplier_predicate(supplier_id_or_ids)`,
   used by every supplier filter over shipments - the packing-list list / neighbours query, both
   `incoming_stock_service` listings and this route - because a filter that reads the header alone
   hides a mixed container (header NULL) from both of the suppliers actually on it. Where a
   shipment's supplier is SELECTED rather than filtered (`coverage_service`'s factory label,
   `summary_order_service`'s last incoming cost) it reads
   `coalesce(line.supplier_id, header.supplier_id)` for the same reason.
8. Tests (pytest, `blank_session`, seed everything, marker prefixes):
 - **`tests/test_packing_list_multi_supplier.py`** - THE test: two `create_shipment` calls for one
     container, supplier A then supplier B, each with its own product; assert both suppliers' lines
     survive, header supplier NULL (mixed). Then re-upload A with a changed qty; assert A's line
     updated, B's untouched. Then a payload with no supplier at all replaces everything (legacy).
     Plus one test through `packing_list_service.apply` with two in-memory workbooks (openpyxl,
     using the migration-311 aliases `产品型号`/`数量`/`箱数`/`货柜号`) for the same container as two
     suppliers.
 - existing `test_packing_list_container_match.py`, `test_packing_list_duplicate_detection.py`,
     `test_packing_list_neighbours.py` still pass.
 - `tests/test_alembic_revision_ids.py`; `alembic heads` prints exactly one head; migration
     upgrade+downgrade against an empty scratch DB.

## Part 2 - the consolidated Sorento packing list

### Contract

`GET /api/v1/scm/inbound-shipments/{shipment_id}/packing-list` (`_READ` = `scm.dashboard.view`)

```json
{
  "shipment_id": "...", "shipment_number": "FSCU8103365", "container_no": "FSCU8103365",
  "bl_no": null, "status": "in_transit",
  "factories": [
    {
      "supplier_id": "...|null", "supplier_code": "400-K029|null", "supplier_name": "KAILU HARDWARE FACTORY|Unassigned",
      "loading_plan_id": "...|null", "notice_id": "...|null", "has_pack_plan": true,
      "notice_created_at": "2026-08-01T09:00:00|null", "notice_sent_at": "2026-08-01T09:30:00|null",
      "lines": [
        { "line_id": "...", "product_id": "...", "product_code": "SRTWT7443", "product_name": "...",
          "brand": "SORENTO|null", "company": "SORENTO|MOCHA",
          "qty": 490, "cartons": 86, "cbm": 2.10528, "remarks": "supplier's own text|null",
          "discrepancies": ["Loading plan asked 500, packed 490 (short 10)"] }
      ],
      "not_packed": [ { "product_id": "...", "product_code": "...", "product_name": "...", "planned_qty": 100 } ],
      "subtotal": { "lines": 21, "qty": 3519, "cartons": 261, "cbm": 8.6033, "cbm_known_lines": 19 }
    }
  ],
  "total": { "lines": 54, "qty": 7365, "cartons": 685, "cbm": 63.2029, "cbm_known_lines": 50 },
  "split": [
    { "company": "SORENTO", "lines": 48, "qty": 6465, "cartons": 630, "cbm": 55.8959, "cbm_known_lines": 45 },
    { "company": "MOCHA",   "lines": 6,  "qty": 900,  "cartons": 55,  "cbm": 7.3070, "cbm_known_lines": 5 }
  ]
}
```

Rules:
- Factory = the line's `supplier_id` (NULL -> one "Unassigned" group, last). Ordered by supplier
  name. Lines within a factory ordered by product code.
- `company` = `"MOCHA"` when the product's brand code is `MOCHA`, else `"SORENTO"` (the captain's
  file counts SANDEL / CABANA / blank under SORENTO). Both split rows are ALWAYS present, zeros
  when empty.
- `cbm` per line = `line.cbm` if set, else catalogue `dimensions_l*w*h/1e9 * qty` (same mm^3 basis
  as `loading_plan_service._catalogue_cbm`; do NOT import from there, copy the two-line formula and
  say why), else null. Subtotal / total / split cbm sum the non-null ones; `cbm_known_lines` count
  alongside so a partial figure is not read as a full one.
- Discrepancies (derived, never asked): the `supplier_notices` row for that supplier this
  container could have been packed to - notices are sent per SUPPLIER, not per container, so the
  date is the only link: the latest with `created_at <= shipment_date + 1 day`, and only when there
  is no such notice does the latest overall stand in. Any channel; its lines with `kind='pack'`,
  summed by `product_id`. `notice_created_at` / `notice_sent_at` are reported so a comparison that
  looks wrong can be traced to the document it was made against. A notice whose lines are ALL
  `produce` has no pack plan in it: `notice_id` is still reported with `has_pack_plan: false`,
  and nothing is compared (`has_pack_plan` is true only when the chosen notice carries `pack`
  lines, so an empty `discrepancies` on every line can be told apart from a container that
  matched its plan). For each
  shipped line: no plan line -> `"Not on the loading plan"`; planned != qty ->
  `"Loading plan asked {planned}, packed {qty} ({short|over} {abs diff})"`. Plan lines with no
  shipped line for that supplier -> `not_packed[]`. No notice for the supplier -> `notice_id: null`,
  no discrepancies, `not_packed: []`. Unassigned group -> no comparison.
- Empty container (no lines): `factories: []`, totals zero, split both zero. 200, never 404 for
  "no lines"; 404 only when the shipment id is unknown.

`GET /api/v1/scm/inbound-shipments/{shipment_id}/packing-list/export` (`_READ`) -> `.xlsx`
(`Content-Disposition: attachment; filename="<container_or_number>-packing-list.xlsx"`). One
sheet `PACKING LIST`: header block (CONTAINER, BL, STATUS, FACTORY: comma list), a header row
`FACTORY | NO | MODEL | DESCRIPTION | QTY | CTN QTY | CBM | LOGO | REMARKS`, then per factory its
lines, a subtotal row, then the not-packed rows (QTY blank, REMARKS "Not packed - loading plan asked
N"), grand total, then the SORENTO / MOCHA split rows (QTY, CTN, CBM). openpyxl, in-memory bytes.
Number cells as numbers.

### Backend

- `app/services/scm/consolidated_packing_list.py`: `build(db, shipment_id) -> dict` (the JSON
  above), `to_xlsx(payload: dict) -> bytes`. Pure over ORM reads; no writes.
- Routes in `app/api/v1/scm/fulfilment.py` next to the other inbound-shipment routes.
- Tests `tests/test_consolidated_packing_list.py`: two suppliers, one MOCHA-brand product, one
  supplier notice with a differing qty and one un-packed line, one line with `cbm` and one relying
  on catalogue dims; assert grouping, subtotals, total, split, discrepancy strings, not_packed;
  route 200 + 403; export returns a workbook openpyxl can read back with the subtotal rows present.

### Frontend

- `fulfilmentService.ts`: `getConsolidatedPackingList(shipmentId)`, `getPackingListExportUrl(shipmentId)`
  (download via `apiFetch` blob, same pattern as `getNoticeDocumentUrl`). Types
  `ConsolidatedPackingList`, `PackingListFactory`, `PackingListLine`, `PackingListTotals`.
- Hook in `hooks/useFulfilment.ts`: `useConsolidatedPackingList(shipmentId)`.
- `incoming/components/ConsolidatedPackingListPanel.tsx`: rendered under the container list when
  one is selected, ABOVE `AllocationPanel`. Card titled "Sorento packing list" with a "Download
  .xlsx" button. Body: per factory a section header (supplier name, subtotal chips qty / ctn /
  cbm), a `DataGrid` (`tableLayout: { width: 'fixed', columnsResizable: true }`, explicit `size`,
  `truncate` + `title`) with columns Model, Description, Logo/brand, Qty, Ctn, CBM, Remarks
  (supplier remark + derived discrepancies as amber text); not-packed rows listed under the grid
  as muted rows; a footer with grand total and the SORENTO / MOCHA split. States: loading
  skeleton, error, empty ("No lines on this container yet."). No UUIDs shown. No explanatory
  prose.
- `IncomingContainersView.tsx`: row shows `suppliers` names joined by ", " under the container
  number (replaces the "No container number yet" line when suppliers are known; keep that copy
  when there are none). Mount the new panel.
- Vitest: `ConsolidatedPackingListPanel.test.tsx` covering loading / error / empty / data (two
  factories, subtotal, split, discrepancy text rendered), with
  `useListingColumnPreferences` mocked per CLAUDE.md.

## Verification

- pytest targeted files only (never the full suite).
- `alembic heads` = one; upgrade + downgrade on a scratch DB.
- FE: `npx vitest run app/\(protected\)/scm/incoming`; `npm run dev` + agent-browser
  `--session scm-container-multi-supplier` only if genuinely needed; close the session after.

## Delivery

Direct PR, one independent review on Opus (Codex out of quota until 20 Aug; captain approved the
substitution). PR body states the identity model and why, the known limit, and the substitution.
