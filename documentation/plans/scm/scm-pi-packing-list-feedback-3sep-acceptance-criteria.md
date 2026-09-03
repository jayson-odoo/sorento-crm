# UAC - proforma invoice + packing list feedback batch (3 Sep 2026)

Plan: `PLAN-scm-pi-packing-list-feedback-3sep.md`. Status: APPROVED 3 Sep 2026 (plan Status line governs).

## Journey

**Actor:** Ms Tee (purchasing), on the desktop, with the supplier's proforma invoice already
uploaded and a container to fill.

1. She opens **Proforma Invoices** from the sidebar. The list shows every invoice, newest first,
   with no filter pre-applied; the Packing list filter is one click away when she wants only the
   unconverted ones.
2. She opens an invoice and reads its **Lines**. Every line that our catalogue recognises shows
   the product; a line the supplier codes differently reads Not in catalogue with a Match action
   in the row (as built today, kept by captain ruling 3 Sep).
3. She matches in the row, or presses Edit and picks the product in the line's own select. Save
   remembers the pick as the supplier's code for next time; clearing the product and saving
   forgets it. Undo is the same edit in reverse.
4. She steps to the next invoice with the pager and lands on the **same tab**.
5. She presses **Edit** while on Lines and stays on Lines. Every matched product is shown in its
   select; UoM is picked from the master list; Save writes only what she changed and never
   unbinds a product she did not touch.
6. She selects the invoices going into one box and presses **Convert to packing list**. The
   dialog names the container size; the invoices' volume against that size is the only capacity
   check. The invoice itself carries its total volume as a number, nothing more.
7. She opens the packing list. **Edit** is the primary action; Download sits in the gear. The
   Details tab reads top to bottom like the header block of her own container workbook: Loading,
   ETD, ETA, Container, Seal, SO, Consignee, Shipper, China agent, Factory, Free days, Delivery
   warehouse; then the three costs the footer apportions; then the rest of the clearance trail.
   Save either succeeds or names the field that was refused.
8. **Shipment lines** is a DataGrid laid out column-for-column like the workbook: Factory, No,
   Model, Description, Material, Qty, Pcs/ctn, Ctn qty, L, W, H, CBM/ctn, Total CBM, NW, GW,
   Total NW, Total GW, Logo, Remarks, Price, Amount, with a totals footer and the per-company
   split (CBM, clearance, insurance, China freight, amount) beneath it. What she sees on screen
   is what Download writes to the file.

Nothing is asked twice: the factory is the line's supplier, the logo is the product's brand,
carton count and CBM/ctn are derived from pcs/ctn and the carton size, and the per-company split
follows the three costs typed on Details.

## Acceptance criteria

### A. PI detail navigation (S1)

- **AC-A1 [FE]** Given the PI detail, when a tab other than General is selected, then the URL
  carries `?tab=<id>` (`lines`, `revisions`, `packing-lists`) and General carries no `tab`.
- **AC-A2 [FE]** Given `?tab=lines`, when prev/next is pressed, then the next record opens on
  Lines with the rest of the list query intact.
- **AC-A3 [FE]** Given a reload of `?tab=revisions`, then Revisions is active.
- **AC-A4 [FE]** Given the Lines tab, when Edit is pressed, then Lines stays active.
- **AC-A5 [T]** `useUrlTab` has a vitest covering: unknown value falls back to the default,
  default writes no `tab`, other params survive a tab change. Loading plan uses the same hook
  and its existing tab tests still pass.

### B. PI edit fidelity (S2)

- **AC-B1 [BE]** `GET /scm/proforma-invoices/{id}` line payload carries `product_id` and
  `product_set_id` alongside `product_code` / `set_code`.
- **AC-B2 [FE]** Given a matched line, when Edit is pressed, then the Product select shows the
  matched product code as its value.
- **AC-B3 [BE][T]** Given a PUT whose line omits the `product_id` key, then the stored
  `product_id` and `product_set_id` are unchanged. Given `product_id: null` explicitly, then the
  product is unbound. Pytest pins both.
- **AC-B4 [FE]** Given edit mode, then UoM is a clearable `SearchableSelect` fed by the master
  units-of-measure select endpoint; the stored value stays the UoM code (String 20).
- **AC-B5 [FE]** Given a new line, when a product is picked, then UoM defaults to the product's
  base UoM when blank (existing behaviour kept).

### C. PI match memory parity (S3)

Captain ruling (3 Sep markup): the PI's in-row match is the better experience; it stays. The
loading plan's Supplier codes tab is not brought onto the PI.

- **AC-C1 [BE][T]** Given a PUT whose line's `product_id` changed to a product (or `product_set_id`
  to a set), then a `manual` alias `(supplier_id, item_code) -> product` is upserted, and every
  other current line of that supplier carrying the same code is re-bound. Pytest.
- **AC-C2 [BE][T]** Given a PUT whose line's product was cleared (explicit null), then the line is
  unbound and the alias for that code, if manual, is deleted. An `auto` alias is left alone.
  Pytest.
- **AC-C3 [FE]** The Match column keeps Matched / Set / auto / Not in catalogue plus the in-row
  Match, Change and Forget actions exactly as today; a line matched through edit-mode shows
  Matched after Save without a reload.
- **AC-C4 [FE]** Edit-mode Product select is `clearable`; clearing shows the line as Not in
  catalogue in the draft.

### D. PI list + supplier select (S4)

- **AC-D1 [FE]** Given a fresh sidebar visit to Proforma Invoices, then no filter is applied
  and the chip row is empty. `placement` still works from the filter popover and the URL.
- **AC-D2 [BE]** `GET /procurement/suppliers/select` orders by `supplier_name, supplier_code`,
  accepts `page` + `limit` (default 50, max 100) and returns `{items, has_more}`.
- **AC-D3 [FE]** Supplier options are labelled `<code> - <name>` so two rows sharing a name are
  distinguishable; the PI upload dialog, loading plan container dialog and PI list filter all
  read through `getFulfilmentSuppliers` and inherit it.
- **AC-D4 [FE]** The select is `paginated` (Load more after 50) and the list scrolls with the
  wheel inside a Dialog at 1280 and 375.
- **AC-D5 [T]** Pytest on the select endpoint: ordering, paging, `has_more`.

### E. Volume belongs to the container (S5)

- **AC-E1 [FE]** PI General tab shows **Total volume** as a number (`69.36 cbm`, plus `N
  unmeasured lines`); no capacity, percentage, bar or "over by".
- **AC-E2 [FE]** The Container size field is removed from the PI General tab and edit form.
- **AC-E3 [BE]** Migration adds `inbound_shipments.container_size_id` (FK `scm.container_size`,
  SET NULL). `scm.proforma_invoice.container_size_id` is dropped in the same migration after
  its values are copied onto any draft shipment the invoice was converted into (one PI per
  shipment case only; mixed cases leave the shipment NULL).
- **AC-E4 [FE]** Convert dialog carries a Container size select (default = tenant default);
  the over-capacity check compares the selected invoices' summed volume with that size, and the
  size is written onto the draft shipment.
- **AC-E5 [FE]** Packing list Details tab shows the fill gauge (total CBM of lines vs the
  shipment's container size, "over by") in the Container card; the size is editable there.
- **AC-E6 [BE][T]** Pytest: convert writes `container_size_id`; over-capacity uses the dialog
  size; `_fit` moves from the PI serializer to the shipment payload.

### F. Packing list header + save (S6)

- **AC-F1 [FE]** Primary action is **Edit**; the gear holds Download packing list, Import
  Container Status workbook, Delete.
- **AC-F2 [FE]** `packingListService` create / update / delete / bulk-delete use
  `extractApiError`; a 422 toasts the pydantic message naming the field.
- **AC-F3 [FE]** Empty date inputs send `null`; blank numeric inputs send `null` (never NaN,
  never a silent default of 1 for cartons).
- **AC-F4 [BE][T]** `InboundShipmentUpdate` accepts `shipment_number`; the update schemas are
  `extra='forbid'` so an unknown key 422s. Pytest pins both.
- **AC-F5 [FE]** Details tab card order and field order, view and edit identical:
  1. **Container** - Loading date, ETD, ETA, Container no, Seal no, SO (forwarder order ref),
     Consignee, Shipper, China agent, Factory (derived, read-only), Free days, Delivery
     warehouse, Container size (S5).
  2. **Costs** - Clearance, China freight, Insurance rate.
  3. **Clearance** - the remaining checkpoints and attributes (ETC, ETA delay, Inspection,
     Approval, Gatepass, Warehouse arrival, Informed collection, Collection, Liner, China
     forwarder, Malaysia forwarder, Location, Stacked, COA permit no), Source sheet.
  4. **Document** - Shipment number, Supplier, Shipment date, Actual arrival, Bill of lading,
     Invoice number, Total items (derived), Notes.
- **AC-F6 [E2E]** Fill Seal no, Shipper, Container no, Save: toast success, values persist after
  reload, Download writes them into rows 4, 5, 8 of the RMB sheet.

### G. Shipment lines grid (S7)

- **AC-G1 [FE]** Shipment lines is a `DataGrid` (`tableLayout fixed`, resizable, sticky header,
  `listingKey` = `procurement.packing_lists.view::lines`) with columns in workbook order:
  Factory, No, Model, Description, Material, Qty, Pcs/ctn, Ctn qty, L, W, H, CBM/ctn, Total
  CBM, NW, GW, Total NW, Total GW, Logo, Remarks, Price, Amount, then From PI, SPO allocated,
  Received, Status.
- **AC-G2 [FE]** Derived cells (Ctn qty, CBM/ctn, Total CBM, Total NW, Total GW, Amount)
  use the same rule as the workbook: `ctn = qty / pcs_per_ctn` when pcs stated else the stored
  cartons; `cbm/ctn = L*W*H / 10^6`; totals multiply by ctn; amount = price * qty.
- **AC-G3 [FE]** Rows sort by Factory then No; a totals footer sums Qty, Ctn qty, Total CBM,
  Total NW, Total GW, Amount with an `(N unmeasured)` caveat.
- **AC-G4 [FE]** Beneath the grid a **Split** card shows, per company (SORENTO, MOCHA): CBM,
  Clearance, Insurance, China freight, Amount, and a total row, computed by the same JSON
  `build()` the export uses (`GET /inbound-shipments/{id}/packing-list`).
- **AC-G5 [FE]** Edit mode keeps the same columns; inputs sit in the same cells; Add line /
  Remove keep working; the search box and column preferences persist.
- **AC-G6 [E2E]** Values on screen for a real container (FSCU8103365 fixture) equal the cells
  Download writes: spot-check three lines and the split card against the workbook.
- **AC-G7 [FE]** Usable at 375 (horizontal scroll inside the grid, page never scrolls
  sideways) and 1280.
