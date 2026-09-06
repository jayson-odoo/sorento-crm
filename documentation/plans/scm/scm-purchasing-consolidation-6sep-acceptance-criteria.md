# UAC - purchasing consolidation batch (6 Sep 2026)

Plan: `PLAN-scm-purchasing-consolidation-6sep.md`. Status: markup round 1 applied 6 Sep 2026
(Q1-Q5 ruled, AC-A1 / AC-D3 / AC-D4 / AC-E4 / AC-F4 revised), awaiting GO.

## Journey

Actor: purchasing (Ms Tee), desktop, and the supplier receiving the request.

1. She opens the sidebar. Everything about buying sits under Procurement > Supply Chain;
   Sales Orders sits under Project Sales Admin. Nothing she bookmarked is dead.
2. A supplier sends the proforma invoice and the packing list (two files, or one). She goes to
   Packing Lists, presses `Upload supplier documents`, drops both. The preview names each file's
   kind, the container and seal per block, the prices, the cartons, the English beside the
   Chinese. She confirms. A draft packing list per container exists with container, seal,
   consignee, shipper and BL pre-filled; the lines carry prices from the invoice; both files are
   in Drive in the Packing List folder.
3. On the loading plan the suggested quantity already discounts what is on a packing list and
   not yet on an SPO. She presses `Preview request`, sees the exact document the supplier will
   get: rows with a quantity to load highlighted, the rest plain, a remark she types per line.
   She sends it from there.
4. In the SPO planner she opens SO covered: a Project tab and a Retail tab, sortable, and she
   types 30 for the first order and 8 for the next. After creating the SPO she opens it: the SPO
   view, not the PO, with each line's PO and the sales orders it covers. A week later she
   presses `Edit in planner`, moves 10 units to another warehouse, saves.
5. The supplier sends photos of the goods. She adds them to the shipment lines; the exported
   packing list carries one photo column per photo.

## A. Navigation (plan section 1)

- AC-A1. Sidebar from `/`: Procurement keeps Suppliers, Product-Suppliers, Packing Lists, SPO
  Allocations, GRN, Picking Lines, Stock Inquiries in their current positions and gains a
  `Supply Chain` sub-group with, in order, Reorder Planning, Loading Plan, Order Inquiries,
  Purchase Orders, Proforma Invoices. Supply Chain (top level) holds Dashboard, Planning
  (Simulation, Market Signals, Policies), Project Demand (without Order Inquiries); Incoming
  Containers is gone from the menu. Project Sales Admin's first entry is Sales Orders.
- AC-A2. Every path in `OLD_PATHS` still exists in `MENU_SIDEBAR`; no page URL changes.
- AC-A3. A user whose tenant has `procurement` enabled and `scm` disabled does not see the six
  `/scm/*` leaves in the sidebar nor in the search palette; a user with `scm` sees them and can
  open them (no bounce to `/`).
- AC-A4. Breadcrumbs of the five moved pages read `Procurement > Supply Chain > <page>` and
  Sales Orders reads `Project Sales Admin > Sales Orders`; the search palette breadcrumb
  matches the tree.
- AC-A5. `menu.config.test.ts` pins the new positions with the existing helpers; the six
  headings assertion is unchanged.
- AC-A6. Incoming Containers is absent from the menu; `/scm/incoming` still renders.

## B. Upload packing list CTA (section 2)

- AC-B1. Packing Lists toolbar: primary `Upload packing list` (lane A label; lane C relabels to
  `Upload supplier documents`), gear holds Create Packing List and Import Container Status.
- AC-B2. Confirming an upload creates the shipment(s), stores the file as an attachment of type
  Packing List in that type's default folder, binds `attachment_id`, and writes NO
  `integration_log` row for n8n.
- AC-B3. Attachment type form has a clearable `Default folder` select; the Create Attachment
  dialog pre-selects it when that type is chosen and the user can change it.
- AC-B4. A type with no default folder behaves as today.
- AC-B5. New column appears in the attachment type read and list serializers (asserted).

## C. Upload SPO CTA (section 3)

- AC-C1. SPO Allocations toolbar: primary `Upload SPO` opens the existing import dialog;
  Create SPO Allocation sits in the secondary menu.

## D. Loading plan (section 4)

- AC-D1. `suggested_qty = max(open_so_need - on_hand - incoming_spo - incoming_pl_unallocated, 0)`
  where `incoming_pl_unallocated` sums `GREATEST(quantity_shipped - spo_allocated_quantity -
  quantity_received, 0)` over unreceived shipments. Pytest: a product with need 100, on hand 10,
  incoming SPO 20 from shipment X, shipment X line qty 50 with `spo_allocated_quantity` 20 ->
  suggested 40 (not 20).
- AC-D2. The row payload carries `incoming_pl_unallocated` beside `incoming_pl`; the tooltip and
  the FormulaTip footer print the four-term formula.
- AC-D3. Grid columns, in order: Rank, Product, Suggested qty, Need, Project, Retail, On hand,
  SPO, Incoming PL, Total supply, PO, Packed. No Earliest need-by, Project peak, Retail peak.
- AC-D4. Total supply = On hand + SPO + Incoming PL for the row (vitest on the cell); the
  three source columns and their lightboxes behave exactly as today.
- AC-D5. Project and Retail lightboxes still expose the 12-month history tab with the peak
  month named.
- AC-D6. Usable at 375 and 1280 (horizontal scroll inside the grid only).

## E. Supplier request preview (section 5)

- AC-E1. `Preview request` beside `Send to supplier` switches the plan page into the document
  view; the header shows supplier, horizon, line count, total qty, and the Send button;
  `Back to plan` returns.
- AC-E2. The preview renders the same `SheetModel` the public page, PDF and xlsx use; the
  three renderers and the preview agree on rows, merges, totals, highlights and remarks
  (pytest on the model; vitest on the renderer).
- AC-E3. Rows with qty to load > 0 carry the highlight fill; no other row carries any fill or
  red font, whatever the supplier's file had. xlsx: title and header rows keep their style,
  data rows have only our fill. PDF and public page: same.
- AC-E4. Remarks: a text cell per line in the plan table (`Remarks` column) and an input on
  the preview itself (Qty to load is an input there too); both write the same
  `line_edits[row_key].remark`; a remark typed on the preview shows in the plan table after
  save and vice versa; Send saves first (existing rule).
- AC-E5. `line_edits` stored as a bare number still reads as `{qty}`; saving upgrades it.
- AC-E6. The sheet's column L is `备注 / Remarks` in xlsx, PDF and the public page; the
  notice's frozen `sheet_json` carries the remarks that went out; a later edit on the plan
  does not change a sent document.
- AC-E7. The public page stays read-only.

## F. Supplier documents upload (section 6)

- AC-F1. `Upload supplier documents` accepts several files; preview classifies each as
  proforma, packing list or combined by title cell; an unclassifiable file is named and blocks
  Confirm.
- AC-F2. Parsing `发票 SORENTO-2026.7.26.xls` (fixture): 2 blocks, containers `WHSU6243088`
  (seal `WHA4528193`, 3 lines, 366 units, 87,710) and `WHSU6356079` (seal `WHA4528173`, 2
  lines, 510 units, 122,182), `pi_number 2026JXL0726`, `invoice_date 2026-07-26`, consignee
  `SORENTO SDN BHD`, shipper the letterhead company, currency RMB. SUB TOTAL and TOTAL rows
  excluded.
- AC-F3. Parsing `装箱单 SORENTO-2026.7.26.xls` (fixture): 2 blocks, same containers and
  seals; block 1 lines with codes: SRTWCX8840-S-RL 266, SRTWCX8840-P-RL 100, SRTWCY8840 366,
  8840 366 (60 cartons); the four code-less accessory rows kept as block notes, not lines;
  `备注：` footer captured into `notes`; cartons 792, CBM 49.41 for block 1.
- AC-F4. Confirm creates one draft shipment per container block with `shipping_container_number`,
  `seal_number`, `consignee`, `shipper`, and `forwarder_order_ref` (the `SO` field, from
  `提单号` when stated) pre-filled; `bill_of_lading_number` is left empty; the Details card
  shows them without editing.
- AC-F5. Uploaded together: every PL line with a matching PI line (same block container, same
  item code) has `unit_cost` and `currency` from the PI and a `proforma_invoice_shipment_link`
  row; the shipment's Proforma invoices tab lists the PI.
- AC-F6. Uploaded separately, PL after PI: same result via `pi_number` or container match.
  PI after PL: preview says which draft shipments will receive prices; confirm links them.
- AC-F7. A second upload of the same file is refused by the existing duplicate rule.
- AC-F8. Alias seed migration is idempotent and replayed by `bootstrap_env.py`; a test proves
  `seed()` resolves every header in both fixtures.
- AC-F9. `_labelled` splits `箱号:X / 封签号:Y` into two fields; `货柜号：X` alone still works.

## G. Translation memory (section 7)

- AC-G1. `translation_memory` table; `translate(["座厕"])` returns the manual row when present,
  the `ai` row when present, else (with AI configured) one batched model call writes `ai` rows
  and returns them; with no key configured returns misses flagged `untranslated`.
- AC-G2. Preview shows English beside Chinese for descriptions and remarks; editing a cell
  writes a `manual` row; the same phrase in the next upload shows the edited text.
- AC-G3. Shipment line `remarks` stores `English (中文)` when the two differ; the export prints
  the English.
- AC-G4. System Management > Translations: DataGrid (source, target, source kind, hits,
  updated), inline edit, hard delete with confirmation.

## H. Costs hidden (section 8)

- AC-H1. Packing list Details has no Container costs card in view or edit mode.
- AC-H2. The exported xlsx has no clearance / freight / insurance footer rows; line columns
  unchanged (RMB, TOTAL RM stay). Existing cost values in the DB are untouched.

## I. SO covered dialog (section 9)

- AC-I1. Tabs `Project (n)` and `Retail (n)`; each lists only its class; the footer
  `taken of SPO qty · Unassigned N` is shared.
- AC-I2. `Take` is a numeric input per ticked row, seeded by the waterfall; editing a row
  re-flows only the rows after it; a take above the row's outstanding or a total above the SPO
  qty marks the cell destructive and disables Confirm.
- AC-I3. Example: SPO qty 38, rows outstanding 38 and 58; user types 30 on the first; the
  second seeds 8. Confirm sends `so_takes: [{key, qty: 30}, {key, qty: 8}]`.
- AC-I4. Columns sortable (click header, indicator shown), default Delivery date ascending per
  tab.
- AC-I5. Create writes `order_inquiry_links` with the typed qty for project rows and
  `order_link_claim(source='planner', qty)` for retail rows; reopening the SPO shows both.

## J. SPO link and linkage (section 10)

- AC-J1. Created SPOs `S-SPO-2026/09-0003` opens `/procurement-management/spo-allocations/S-SPO-2026%2F09-0003`.
- AC-J2. Lines tab columns gain `PO` (link to the PO) and `SO covered` (`n SOs · qty`, opens the
  lightbox listing document, customer, class, qty).
- AC-J3. The header tab shows the linkage strip: PO, SPO lines, SO covered, Packing list, GRN,
  each a link when present. Response fields asserted in pytest (`response_model` rule).

## K. Edit SPO in planner (section 11)

- AC-K1. Created SPOs row action `Edit in planner` loads the planner with that SPO's lines,
  qty, PO takes, SO takes and location splits pre-filled; the toolbar reads `Editing S-SPO-...`
  with Save and Cancel.
- AC-K2. Save updates rows in place: changed qty, moved warehouse split, added / removed SO
  take, changed PO take; `spo_allocated_quantity` on the shipment line and the PO header totals
  recompute; the SPO number is unchanged.
- AC-K3. A row with `quantity_received > 0` refuses a qty below the received figure, naming the
  row; nothing is written.
- AC-K4. Removing a line entirely from an edited SPO unwinds only that line.
- AC-K5. The SPO document Lines tab offers `Edit in planner` linking to the same screen.

## L. Line photos (section 12)

- AC-L1. Lines tab has a `Photos` cell: thumbnails, `+` opens the shared dropzone
  (multi-file, image types), delete with confirmation.
- AC-L2. `inbound_shipment_line_photos(line_id, attachment_id, sort_order)`; attachment type
  Shipment Line Photo.
- AC-L3. Export: `PHOTO 1 .. PHOTO n` after REMARKS, `n` = max photos on any line; images
  embedded and sized to the row; a line with fewer photos leaves cells empty; a shipment with
  no photos exports with no photo column.
- AC-L4. Photos are served through `storage_router` (s3 / r2 rows both work).

## DoD gate (every lane)

Phase 1 mock swapped to real; pytest + vitest for every AC above; agent-browser evidence run via
sidebar clicks at 375 and 1280; `alembic heads` single before PR; new columns in every manual
dict builder they touch; no em-dashes anywhere.
