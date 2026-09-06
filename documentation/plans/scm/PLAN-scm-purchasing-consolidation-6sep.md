# PLAN - purchasing consolidation batch (6 Sep 2026)

**Status:** Lane D built, review round 1 applied, awaiting browser test. (Lanes A, B and C
still as markup round 1 left them: Q1-Q5 ruled, R1 and R7 revised, R11 clarified.) UAC:
`scm-purchasing-consolidation-6sep-acceptance-criteria.md`. Lavish page:
`mockups/purchasing-consolidation-6sep-plan.html`.

Feedback given 6 Sep on production (`fe-sorento.foundryx.my`). Twelve asks, four lanes, four
PRs. Every "what exists" line below was measured on `origin/main` `cc0789971` (6 Sep), not on
the stale checkout (`fix/mention-email-and-chat-render` predates the SPO document rewrite).

## 0. The ask, in the captain's words, mapped to sections

| Ask | Section |
| --- | --- |
| Sales Orders to Project Sales Admin; Purchase Orders, Proforma Invoices, Order Inquiries, Loading Plan, Reorder to Procurement under a Supply Chain sub-section | 1 |
| "Upload packing list" CTA on the Packing Lists page, file lands in a default Packing List folder | 2 |
| "Upload SPO" becomes the CTA on SPO Allocations | 3 |
| Loading plan: suggested qty deducts incoming packing list; hide Earliest need-by, Project peak, Retail peak; one column for on hand + SPO + incoming | 4 |
| Supplier request: preview before send, amend, highlight rows with qty to load (not the supplier's formatting), editable remarks | 5 |
| One place to upload proforma invoice AND packing list, separate or combined; read container, seal, consignee, 提单号 so the packing list is pre-filled | 6 |
| Translation memory Chinese <-> English for supplier documents | 7 |
| Costs section not needed: hide on screen and in the exported packing list | 8 |
| SO covered: one tab Project, one tab Retail; Take editable (suggest, user overrides); columns sortable | 9 |
| SPO link opens the SPO allocation view, not the PO; Lines tab shows PO and SO linkage | 10 |
| SPO editable through the planner after creation (links, quantity, locations) | 11 |
| Shipment lines: supplier photos per line, multiple, each in its own column in the exported Excel | 12 |

## 1. Navigation: purchasing under Procurement, sales under Project Sales Admin

### What exists (measured)

- `config/menu.config.tsx` `MENU_SIDEBAR` (the only mounted tree; `MENU_SIDEBAR_COMPACT` carries
  no `/scm/*` path). Supply Chain (`moduleKey: 'scm'`, line 197) holds Dashboard, Planning
  (Reorder Planning, Loading Plan, Simulation, Market Signals, Policies), Project Demand
  (Fulfilment Planning, Stock Debt, Plans, Order Inquiries, Planning changes, Forecast &
  Reports), Orders (Sales Orders, Purchase Orders, Proforma Invoices, Incoming Containers).
  Procurement (`moduleKey: 'procurement'`, line 301): Suppliers, Product-Suppliers, Packing
  Lists, SPO Allocations, GRN, Picking Lines, Stock Inquiries. Project Sales Admin (line 586,
  OPERATIONS heading, `moduleKey: 'procurement'`): Purchase Requests, Sponsorship Forms,
  Sponsorship Report.
- Leaves carry no `moduleKey`; the sidebar filter (`sidebar-menu.tsx:78`) gates by the nearest
  ancestor's key. The route guard gates by URL prefix (`lib/route-module-map.ts:12,17`:
  `/scm` -> `scm`, `/procurement-management` -> `procurement`). `scm` depends on
  `procurement` (`module_manifest.py:103`), never the reverse.
- Every page hardcodes its breadcrumb (`href="/scm">Supply Chain`); only the search palette
  (`lib/universal-search.ts:66`) derives its breadcrumb from the tree.
- `config/menu.config.test.ts` pins: Order Inquiries under Supply Chain > Project Demand with
  Planning changes right after it (204-226); six headings in order (348-359); `OLD_PATHS`
  snapshot (55, every path must survive); Project Sales Admin `moduleKey: 'procurement'`.

### Design

**R1. Routes stay. Menu nodes move. Moved leaves declare `moduleKey: 'scm'` themselves.**
No URL changes (bookmarks, `OLD_PATHS`, the route guard all keep working). Tree after:

```
SALES
  Project Sales, Delivery Orders, Marketing        (unchanged)
SUPPLY CHAIN
  Supply Chain (scm)
    Dashboard
    Planning: Simulation, Market Signals, Policies
    Project Demand: Fulfilment Planning, Stock Debt, Plans, Planning changes, Forecast & Reports
  Procurement (procurement)
    Suppliers, Product-Suppliers, Packing Lists, SPO Allocations, GRN, Picking Lines,
    Stock Inquiries                                  (unchanged leaves, same positions)
    Supply Chain  (sub-group, no path)
      Reorder Planning      /scm/reorder                 moduleKey scm
      Loading Plan          /scm/loading-plan            moduleKey scm
      Order Inquiries       /project-sales/order-inquiries
      Purchase Orders       /scm/purchase-orders         moduleKey scm
      Proforma Invoices     /scm/proforma-invoices       moduleKey scm
  Inventory                                          (unchanged)
OPERATIONS
  Project Sales Admin (procurement)
    Sales Orders          /scm/sales-orders            moduleKey scm
    Purchase Requests, Sponsorship Forms, Sponsorship Report
```

Why the leaf key: a tenant with `procurement` but not `scm` would otherwise see the link and be
bounced to `/` by the guard. The explicit key keeps sidebar, palette and guard in agreement
without touching `route-module-map.ts`. Order Inquiries is gated by `projects.projects.view`
and lives under `/project-sales`, so it keeps its own gating and needs no key.

**R2. Incoming Containers (`/scm/incoming`) is retired from the menu once section 2 ships.**
It lists the same `inbound_shipments` table as Packing Lists and exists mainly to host the
upload dialog (`IncomingContainersView.tsx:15`) plus the consolidated list and allocation
panels, both of which the packing list detail already carries (Download packing list, SPO
planner). Path stays reachable (no deletion this batch; `OLD_PATHS` untouched), menu entry
goes. RULED 6 Sep (Q2).

Breadcrumbs of the five moved pages are rewritten by hand to `Procurement > Supply Chain > X`
(and `Project Sales Admin > Sales Orders`). Test file updated to the new tree with the same
`findGroup / findSubGroup / findLeaf` helpers; the headings assertion is unchanged (no new
heading).

## 2. "Upload packing list" is the Packing Lists CTA

### What exists

- Packing Lists toolbar: primary `Create Packing List` (manual form, `PackingListsList.tsx:382`),
  secondary Import Container Status. No upload.
- TWO ways a packing list file becomes a shipment today: (a) Drive upload with attachment type
  Packing List -> n8n AI extraction -> `POST /api/v1/external/packing-lists/` (header + product
  quantities only, no dimensions, no prices); (b) the in-app deterministic reader on
  `/scm/incoming` (`PackingListUploadDialog.tsx` -> `POST /api/v1/scm/packing-lists/preview|apply`,
  alias-driven, multi-container blocks, Test then Confirm, `apply(attachment_id=...)` already
  accepts a bound attachment).
- No default-folder concept: `AttachmentUploadDialog` takes a `defaultDirectoryId` prop from the
  caller only; `attachment_types` has no directory column; no migration seeds a "Packing List"
  folder or type (both are admin data in production).

### Design

**R3. The CTA is the in-app reader, and it files the document in Drive.** Primary button
`Upload packing list` opens the existing `PackingListUploadDialog` (moved to a shared location
under `procurement-management/packing-lists/components/`), extended by section 6 into the
supplier-documents dialog. On Confirm the backend stores the file as an `attachments` row of
type Packing List in the type's default folder, binds it (`inbound_shipments.attachment_id`,
the column the n8n path already fills) and does NOT fire the n8n webhook for that upload (the
reader already produced the shipment; firing would create a second one through the external
route). `Create Packing List` moves into the gear menu.

**R4. Default folder is a column on the attachment type.** `attachment_types.default_directory_id`
(nullable FK -> `attachment_directories`, SET NULL), editable on the attachment type form as a
folder select. Used by this upload and pre-selected in the generic Create Attachment dialog
when the user picks a type that has one. One preference, one column (no rules table). Seeding:
none; the captain sets it on the Packing List and Proforma Invoice types after deploy (the
types are admin data, not code).

## 3. "Upload SPO" is the SPO Allocations CTA

What exists: `Import SPO` is a secondary action (`SPOAllocationsList.tsx:412`, `SPOImportDialog`);
`Create SPO Allocation` is the primary button. **R5.** Swap them: `Upload SPO` primary (same
dialog, relabelled), Create SPO Allocation into the secondary menu. No backend change.

## 4. Loading plan: suggested qty nets incoming packing lists, three columns go, one column arrives

### What exists

- `container_request_service.build()` line 1284:
  `suggested_qty = max(open_so_need - on_hand - incoming_spo, 0)`; `incoming_pl` (unreceived
  `inbound_shipment_lines`, `_incoming_packing_lists` line 891) and `outstanding_po` are shown
  beside it, never subtracted. The FE tooltip says so (`ContainerRequestSection.tsx:501-510`).
- Columns are a hardcoded `ColumnDef[]` (no visibility config): Rank, Product, Suggested qty,
  Need, Project, Retail, On hand, SPO, Incoming PL, PO, Earliest need-by, Packed, Project peak,
  Retail peak. Eight of them open the standard lightbox (p4 plan section 2).
- `incoming_spo` sums `spo_allocations` on unreceived shipments; `incoming_pl` sums
  `inbound_shipment_lines` on unreceived shipments. A packing list that already has its SPO
  created is in BOTH sums. `inbound_shipment_lines.spo_allocated_quantity` records the overlap.

### Design

**R6. Incoming PL enters the formula as the part not yet turned into an SPO.**
`incoming_pl_unallocated = SUM(GREATEST(quantity_shipped - spo_allocated_quantity - quantity_received, 0))`
over unreceived shipments. Then
`suggested_qty = max(open_so_need - on_hand - incoming_spo - incoming_pl_unallocated, 0)`.
Netting the full `incoming_pl` would subtract every planned container twice. The tooltip and
the FormulaTip footer print the new formula; `engine_qty` keeps carrying the raw engine value.

**R7. On hand, SPO and Incoming PL stay as columns; a `Total supply` column follows them**
(REVISED 6 Sep: the captain wants the three kept). Cell = On hand + SPO + Incoming PL, plain
number, no lightbox of its own; the three existing columns and their lightboxes are untouched.
PO stays its own column after it (shown, not subtracted, unchanged).

**R8. Earliest need-by, Project peak, Retail peak columns are removed.** The peaks remain
reachable: the Project and Retail cells' lightbox already opens the 12-month history tab.
Earliest need-by stays in the row payload and in the Need lightbox's first row. No new
column-config machinery (the grid never had one; adding one for three deletions is a layer).

## 5. Supplier request: preview, highlight our rows, editable remarks

### What exists

- `Send to supplier` -> `SendRequestDialog` (channel, recipients, one free-text note). No
  preview; the document is only inspectable through the gear's Download XLSX / PDF.
- `supplier_document_model.SheetModel` renders three ways (xlsx writes column K
  `需装数量 / Qty to load` INTO the supplier's retained workbook keeping their fills; PDF and the
  public page replay their yellow fills and red zeros). No remarks field anywhere in
  `SupplierNotice` / `SupplierNoticeLine` / the sheet model. Per-line qty edits persist in
  `loading_plan.line_edits` (row_key -> qty).

### Design

**R9. Preview is a page state, not a dialog.** A `Preview request` button beside `Send to
supplier` switches the plan into the document view: the SheetModel rendered by the public
page's renderer (same component, moved to `scm/components/SupplierSheet.tsx`), with an
editable Remarks cell per line and the Send button in its header. Sending from the preview
runs the existing save-then-send path; the dialog for channel and recipients is unchanged.

**R10. Our highlight, not theirs.** The renderer stops replaying source fills and red fonts.
Rows whose qty to load is > 0 get one highlight fill (the design system's warning tint on
screen, `FFF2CC` in the xlsx and PDF); every other row is plain. Merges and widths survive.
In the xlsx this means `_with_qty_to_load` clears data-row fills before writing ours (the
title and header rows keep their style). Set lines keep printing the supplier's own code.

**R11. Remarks live on the plan line, next to the qty edit.** `loading_plan.line_edits` becomes
`row_key -> {qty, remark}` (JSON, no migration; old values `row_key -> number` read as
`{qty: n}`). Editable in the plan table (new `Remarks` column, text input) AND directly in the
preview (the Remarks and Qty to load cells are inputs there; same field, same save; the user
never has to return to the plan table to amend, captain's question 6 Sep). The sheet gains column L `备注 / Remarks`; the notice's frozen
`sheet_json` carries it, so a sent document keeps the remark that went out. The dialog's
whole-send `note` stays (it is the message body, not a line remark).

## 6. One upload for proforma invoice and packing list, separate or combined

### What exists

- Proforma upload: `/scm/proforma-invoices` `ProformaUploadDialog` -> `proforma_invoice_reader`
  (block fields `pi_number, invoice_date, container_no, bl_no, currency`). Packing list upload:
  `packing_list_reader` (block fields `container_no, bl_no`). Both readers share the labelled-cell
  scanner `_labelled` (splits ONE `label: value` per cell) and the `import_field_alias` table.
  PI -> draft shipment conversion exists (`convert-to-draft-shipment`, always a NEW draft;
  `proforma_invoice_shipment_link` records PI line -> shipment line).
- Shipment header already has `shipping_container_number, seal_number, shipper, consignee,
  bill_of_lading_number, forwarder_order_ref` (migration 436). PI header has `container_ref,
  bl_ref` only.
- Measured on the two Jiexia files (`发票 SORENTO-2026.7.26.xls`, `装箱单 SORENTO-2026.7.26.xls`):
  same `INVOICE NO.: 2026JXL0726`, same `日期 : 2026.7.26`; blocks open with ONE cell
  `箱号:WHSU6243088 / 封签号:WHA4528193`; PI columns `ITEM | 洁厦型号 | 客户型号 | 品名 | 数量 |
  单价 | 总金额 | 商标`, sub-total rows `SUB TOTAL 1*40HQ`; PL columns `ITEM | JIEXIA MODEL |
  客户型号 | 品名 | 数量 | CARTONS | UNIT G.W | TOTAL G.W | UNIT N.W | TOTAL N.W | CBM/CTN |
  CBM | 商标 | (remark)`; PL carries accessory lines with no code (`840 水箱空瓷：1个`), a
  `备注：` footer with carton dimensions, and `3*40HQ` in the address block. Consignee is the
  `客户：SORENTO SDN BHD` line. Neither file carries `提单号`. Today `箱号` resolves to nothing
  (only `货柜号` is seeded), so the block would read as one container-less block.

### Design

**R12. One dialog, `Upload supplier documents`, on the Packing Lists page (and the same on
Proforma Invoices).** Multi-file. Each file is classified by its title cell (`发票` / `INVOICE`
/ `PROFORMA` -> proforma; `装箱单` / `PACKING LIST` -> packing list; a sheet holding a price
header AND a cartons/CBM header -> combined). Preview lists per file: kind, supplier (asked
once, one supplier per upload as today), blocks (container, seal, cartons, CBM, amount), line
count, unmatched codes. Confirm applies proforma first, then packing lists, then links.

**R13. Header capture.** New block fields on both readers: `seal_no`, `consignee`, `shipper`,
plus the existing `container_no`, `bl_no`, `pi_number`, `invoice_date`, `currency`.
`_labelled` learns to split a cell on ` / ` and `／` before the label test, so
`箱号:X / 封签号:Y` yields both. Aliases seeded (migration, `seed()` replayed from
`bootstrap_env.py` as 357/375 are): `箱号 -> container_no`, `封签号 -> seal_no`,
`客户 -> consignee`, `INVOICE NO. -> pi_number`, `日期 -> invoice_date`, `客户型号 -> item_code`,
`洁厦型号 / JIEXIA MODEL -> supplier_code`, `品名 -> description`, `数量 -> qty`,
`单价 -> unit_price`, `总金额 -> amount`, `CARTONS -> cartons`, `商标 -> brand`, and the G.W /
N.W / CBM pairs. `SUB TOTAL` and `TOTAL` rows are skipped by the existing totals rule; a
line with a description but no code becomes a `remark`-only line attached to the block (kept
in preview, not written as a shipment line; shown under the block as supplier notes). The
`备注：` footer is captured verbatim into `inbound_shipments.notes`.

**R14. A packing list block becomes a draft shipment with its header pre-filled** - container,
seal, consignee, shipper (the letterhead company), `提单号` into the `SO` field
(`forwarder_order_ref`, RULED 6 Sep Q1; `bill_of_lading_number` untouched), ETD when stated -
one shipment per
container block (a two-container document creates two drafts, both linked to the same
uploaded file). Where a PI with the same supplier + `pi_number` (or the same container) exists,
the PL lines are matched to its lines by item code inside the block and prices copy onto
`unit_cost / currency`, writing `proforma_invoice_shipment_link` rows exactly as the convert
dialog does. Uploaded together, the same matching runs in the same apply. Uploaded PI after
PL: the PI apply looks for a draft shipment with the same container and offers the link in the
preview ("Prices for 2 draft shipments"). No new tables: the link table, the aliases table and
the header columns exist.

Q1 RULED 6 Sep: `提单号` fills the `SO` field (`forwarder_order_ref`). The existing
`bl_no` block field keeps its alias but its value is written to `forwarder_order_ref` by the
packing list apply; `bill_of_lading_number` is left for the manual form.

## 7. Translation memory

### What exists

Two alias mechanisms, both structural: `import_field_alias` (header -> field) and
`scm.supplier_product_code_alias` (supplier code -> product). No free-text translation anywhere.
What arrives in Chinese and reaches a user or the export: `品名` descriptions
(`座厕 S-250出水 对冲`), remarks (`纸箱：2个`, `空瓷`), brand `空白` (= blank), footer notes.
Ruling 5 of the 3 Sep batch: DESCRIPTION on screen and in the export stays the product master
name, so descriptions need translating only where no product matched (preview) and in remarks.

### Design

**R15. `translation_memory` table, one row per phrase.** Columns: `id`, `source_text`
(normalised, unique with `source_lang`), `source_lang` (`zh`), `target_lang` (`en`),
`target_text`, `source` (`manual` / `ai`), `created_by`, `updated_at`, `hit_count`. A
`translation_service.translate(texts) -> dict` reads the memory first; misses go to the AI
Assistant's configured model in one batched call (the existing OpenAI config row, prompt in the
prompt registry as `supplier_translation`), are written back as `source='ai'`, and are
returned. No key configured: misses come back untranslated, flagged. Deterministic memory is
the layer of record; the model only fills gaps (the standing "deterministic post-LLM" rule).
AI fill ships in v1 (RULED 6 Sep, Q4).

**R16. Where it shows.** The upload preview prints the English beside each Chinese description
and remark; a cell is editable in the preview and an edit writes a `manual` row (manual always
wins over `ai`). Shipment line `remarks` stores the English with the Chinese in brackets when
they differ; the packing list export prints the English. A `Translations` page under System
Management lists the memory (DataGrid, edit in place, delete) - the same shape as the
supplier code aliases page.

## 8. Costs are hidden

What exists: `Container costs` card (`PackingListDetailsTab.tsx:202-226`,
`CONTAINER_COST_FIELDS`), and the xlsx footer apportions `clearance_cost / china_freight_cost /
insurance_rate` by share (`consolidated_packing_list.py:598-638`). **R17.** The card goes; the
export's cost footer rows go; the three columns stay in the DB (no migration, data untouched,
the AutoCount ingest contract may still read them). `RMB` and `TOTAL RM` line columns stay
(prices, not costs). RULED 6 Sep (Q3): they stay.

## 9. SO covered: Project tab, Retail tab, editable Take, sortable

### What exists

`SoCoveragePicker` (`scm/components/PlanRowDialog.tsx:1582-1869`): one plain table, project
rows then retail rows, checkbox only; `Take` is read-only, computed by `coverageTakes()`
(`SpoPlannerTable.tsx:202-216`) as a waterfall over ticked rows in server order; no
`getSortedRowModel`. Payload `so_line_ids: string[]`. Backend writes `order_inquiry_links`
(qty from the waterfall) for project rows; retail coverage is computed live and never persisted
(`_retail_coverage`, `spo_conversion_service.py:1263`).

### Design

**R18. Two tabs, one selection.** The dialog gets a `Project | Retail` tab strip (counts in
the tab labels); the footer (`taken of SPO qty · Unassigned N`) is shared across tabs so a
take on one tab visibly reduces what the other can draw.

**R19. Take is an input.** Default = the waterfall suggestion. Ticking a row seeds its take;
editing the number re-runs the remainder for the rows AFTER it only (the user's number is
never overwritten by the cascade); a take above the row's outstanding, or a total above the
SPO qty, marks the cell destructive and disables Confirm. Payload becomes
`so_takes: [{key, qty}]`; `so_line_ids` is removed.

**R20. Retail takes persist.** Project rows keep writing `order_inquiry_links` with the user's
qty. Retail rows write `scm.order_link_claim` (`so_line_id`, `spo_allocation_id`, `qty`,
`source='planner'`) - the table that already pairs an SO line with an SPO allocation for the
upload matcher, given a new source value rather than a new table. Without persistence, section
11's edit could never show what was taken for retail.

**R21. Columns sort.** The picker becomes a `DataGrid` with `getSortedRowModel` and
`DataGridColumnHeader` on Sales order, Customer, Delivery date, Outstanding, Taken, Take,
Location; default sort Delivery date ascending inside each tab.

## 10. SPO link and SPO linkage

**R22.** `createdSpoColumns` (`SpoPlannerTable.tsx:626-639`) links to
`spoDetailHref(spo_number)` (`lib/spo-detail.ts`), never `/scm/purchase-orders/{id}`.

**R23. Lines tab shows both sides of every line.** `SPODocumentLine` gains `po` (`{po_number,
po_id, line_no}` from `po_line_id`) and `so_covered` (`[{document, customer, class, qty}]` from
`order_inquiry_links` + `order_link_claim` where `spo_allocation_id` matches). Two new columns
on the Lines grid: `PO` (link) and `SO covered` (`3 SOs · 120` opening the standard lightbox
listing them, the `so_coverage` kind in read-only mode). The header tab gets a linkage strip:
`PO n · SPO lines n · SO covered n · Packing list · GRN n`, each a link. Query change in
`SPOAllocationService.get_document` (`procurement_service.py:2211`) and the Pydantic schema
(the `response_model` rule: assert the new fields in a test).

## 11. SPO editable through the planner after creation

### What exists

`Created SPOs` rows offer Delete only. `spo_conversion_service.create` always writes a NEW
`purchase_orders` header per supplier and converts each line's `remaining_qty`; a converted
line reads `Done` in PO covers and SO covered. Changing an SPO after creation means Delete and
recreate, or the plain field editor on the SPO document page (no links, no splits).

### Design

**R24. `Edit in planner` on a created SPO.** The planner loads that SPO's lines in edit mode:
qty, PO takes, SO takes, location splits, all pre-filled from the persisted rows
(`spo_allocations` per warehouse, `po_line_id`, `order_inquiry_links`, `order_link_claim`).
Save calls `PUT /api/v1/scm/inbound-shipments/{id}/spo/{purchase_order_id}` ->
`spo_conversion_service.revise`: rows keyed by `(shipment_line_id, warehouse_id)` are
updated / inserted / deleted, links re-dealt to the new takes, quantities on the shipment line
(`spo_allocated_quantity`) and the PO header recomputed. A row with `quantity_received > 0`
cannot drop below what was received (refused with the row named); a line removed entirely is
the existing `unwind` for that line only. Delete stays for the whole SPO. The Lines tab of the
SPO document links back (`Edit in planner`) so both entry points meet at one screen.

## 12. Supplier photos on shipment lines

### What exists

`inbound_shipment_lines` has no image column; the lines tab is a plain table with no
attachment cell; the export never embeds images. `project_quotation_excel_service.py:240-247`
already embeds product photos with `openpyxl.drawing.image` (the pattern to copy).

### Design

**R25. Photos are attachments linked to the line.** `inbound_shipment_line_photos`
(`line_id`, `attachment_id`, `sort_order`), attachment type Shipment Line Photo
(image extensions, admin data), uploaded from a `Photos` cell on the lines tab (thumbnail strip,
`+` opens the shared `FileDropzone`, multi-file, delete with confirmation). Follows the
attachment linkage template used by the other linked-attachment features.

**R26. Export: one column per photo index.** `PHOTO 1 .. PHOTO n` after REMARKS, `n` = the
most photos any line carries (no cap per line, RULED 6 Sep Q5); each cell embeds the image resized to the row (row height raised
to fit, 3 cm cap); lines with fewer photos leave the cell empty. Photos are fetched from storage
at export time through `storage_router`, never inlined into the JSON build.

## 13. Lanes, order, slots

| Lane | Sections | Migration | Size |
| --- | --- | --- | --- |
| **A. Navigation + CTAs + hides** | 1, 2 (R3 only, dialog reused as is), 3, 8, 10 (R22) | `attachment_types.default_directory_id` (R4) | small, first |
| **B. Loading plan + supplier request** | 4, 5 | none (`line_edits` JSON) | medium |
| **C. Supplier documents** | 6, 7, 12 | aliases seed; `translation_memory`; `inbound_shipment_line_photos` | large |
| **D. SPO planner** | 9, 10 (R23), 11 | none (`order_link_claim.source='planner'` is a value) | large |

Each lane branches off `origin/main` after A merges (A moves the upload dialog C extends and
renames the CTA D's screenshots show). B, C, D run in parallel on their own slots
(`feedback_two_stack_slots_only`: two at a time, C and D first since B is independent of both).
Coder on Sonnet per slice; D's revise service on Opus (interdependent state: splits, links,
received guards). Reviewer on Opus at the end of each lane.

## 14. Rejected alternatives

- URL renames to `/procurement-management/...` for the moved pages: breaks bookmarks, the
  `OLD_PATHS` test and every hardcoded `href="/scm"`, for no user-visible gain.
- Column-visibility config on the loading plan grid: three deletions do not need a preference
  layer. Trigger for building it: the captain asks to hide a fourth column ad hoc.
- Netting the FULL incoming PL: double-subtracts every container that already has its SPO.
- A separate `spo_so_coverage` table for retail takes: `order_link_claim` already pairs an SO
  line with an SPO allocation and carries `source`.
- Remarks editable on the public page by the supplier: the public page is read-only by design
  (opens tracked, nothing written); the remark is OUR instruction to them.
- LLM translation without a memory: non-deterministic output on every export; the memory is
  the deterministic layer and the model only fills its gaps.
- Keeping `/scm/incoming` as a second listing of the same table with its own upload.

## 15. Captain's rulings, markup round 1 (6 Sep 2026)

| # | Ruling |
| --- | --- |
| Q1 | `提单号` fills the `SO` field (`forwarder_order_ref`). |
| Q2 | Incoming Containers menu entry retired; path stays reachable. |
| Q3 | `RMB` / `TOTAL RM` export columns stay. |
| Q4 | Translation memory + AI fill for misses in v1. |
| Q5 | No photo cap per line. |
| Nav | Packing Lists and SPO Allocations stay where they are (direct Procurement leaves), not in the Supply Chain sub-group. |
| Loading plan | On hand, SPO, Incoming PL stay as columns; one added Total supply column sums them (R7 revised). |
| Preview | Remarks are edited on the preview itself, no trip back to the plan table (R11 clarified). |

No open questions remain. Waiting for GO.

## Deviations (lane D)

Measured while implementing sections 9-11 (D1/D2 only; D3 "Edit in planner" untouched by
this lane).

- **`scm.order_link_claim` had no `qty` column at all** (R20 assumed it might need one only
  "if a NOT NULL column forces it"; it forces one regardless, since a planner claim is the
  first source that states a quantity at write time). Migration `482_scm_claim_qty_planner`
  adds `qty NUMERIC(15,4)`, nullable (every other source leaves it null), plus `planner` to
  the `source` CHECK constraint.
- **`SPODocumentLine.po.line_no` is always null** - `purchase_order_lines` carries no
  per-line ordinal to name (measured against the model, not assumed). The FE type keeps the
  field (`number | null`) so a future column can fill it without a contract change; today's
  reader renders the PO number as the link label either way.
- **The retail claim's `item_code`** is the shipment line's own PRODUCT's `product_code`
  (`products.product_code`), not `inbound_shipment_lines.item_code` - that column does not
  exist on the model (the plan's phrasing implied it did). Consistent with every other
  claim source, which keys `item_code` on the product identity.
- **Header linkage strip (AC-J3):** "PO n" and "SPO lines n" are plain text (no PO-list
  filter-by-SPO-number route exists, per the plan's own "else no link" allowance). "GRN n"
  links only when exactly one GRN is linked (the header's own "Goods receipts" field already
  lists every GRN with its own link when there are several, so the strip does not duplicate
  that control). "Packing list" names the FIRST shipment among the document's lines (a
  document is routinely one container; a rare split picks whichever line the query meets
  first, the same "first if several" reasoning `get_document`'s own GRN fallback already
  uses).
- **SO covered tabs partition by `kind`** (`project` vs `retail`, the family a coverage row
  came from), not `demand_class` (what the SO itself is classified as, which can disagree
  with `kind` - see `SoCoverageRow`'s own doc comment). This reads the UAC's "one tab
  Project, one tab Retail" as a family split, matching how `_so_coverage`'s own server-side
  merge already groups the two.

Measured while implementing section 11 (D3, "Edit in planner").

- **`spo_qty` is the SPO line's own `purchase_order_lines.qty_ordered`, not the sum of its
  allocated quantities.** A line whose splits were left empty writes no `spo_allocations`
  row at all (`create`'s own "absent/empty means no allocation is written"), so a summed
  figure would read 0 for an SPO line that plainly carries a quantity. Wherever splits
  exist the two agree, because `create` refuses a split that does not add up to the line.
- **The RETAIL half of `so_takes` is read from the SPO line's own `source_ref.so_coverage`,
  not from `scm.order_link_claim(source='planner')`.** `_retail_coverage` nets a coverage
  row against `source_ref` (through `_spo_cover_by_so_line`), and the claim write is
  best-effort - a claim refused at create time would then be missing from the state while
  the row it covers still read as spent. The PROJECT half IS read from
  `projects.order_inquiry_links`, for the mirror-image reason: that is the record
  `_project_coverage` nets against. Each half is read from the row its own reader trusts.
- **"PO header totals recomputed" has nothing to recompute.** `purchase_orders` carries no
  stored total; `_existing_spos` sums `qty_ordered` over the header's lines on read, so the
  header total follows its lines with no second write.
- **`planner_state` hands THIS SPO's own claims back out of every "already claimed"
  figure** (not in R24 as written, and necessary): `create` advanced the source PO line and
  netted the demand it was pointed at, so a plain `suggest` reads the SPO being edited as
  taken by somebody else and its own state cannot be re-ticked. `remaining_qty` gains its
  `qty_ordered`, a source line's `open_qty` gains its pull (`_match_takes_for_line`'s new
  `restore`), a coverage row's `qty` gains its take while `taken_qty` / `taken_by` lose it,
  and `_validate_so_takes` takes an `own_taken` map for the same reason. Any OTHER SPO's
  claim is untouched.
- **Deleting an `order_inquiry_links` row obliges a `refresh_link_state` call.** The
  inquiry row's `state` is DERIVED from its links, and `_assert_linkable` refuses anything
  but `raised` / `partly_linked` - so re-saving the SAME project tick was refused (409,
  `order_inquiry_not_raised`) until `revise` re-derived the state between the delete and
  the re-link. `unwind` does not hit this because it never links anything afterwards, so
  this is a `revise`-only addition, not a change to `unwind`.
- **Two refusals R24 does not name.** An SPO cannot be emptied by a revision (422) - Delete
  is the action for that, and a header with no lines is a document that says nothing; and a
  shipment line that is NOT on this SPO cannot be added by editing it (422) - growing a
  container's conversion is what a second Create SPO run is for, and it mints its own
  number.
- **"Nothing written" on the received guard is achieved by validating first, not by one
  database transaction.** `SPOAllocationService.create_allocation` commits (as `create`
  already relies on), so `revise` runs every guard - split sums, PO take caps,
  `_validate_so_takes`, and the received check per `(shipment line, warehouse)` - over
  every line in the body BEFORE the first write. AC-K3's observable promise holds: a
  refusal leaves a valid change on another line of the same body unapplied.
- **AC-K5 is a page-header action, not a Lines-tab control.** `SPODocumentDetail`'s header
  renders on both tabs, so one button serves the Lines tab and the Header tab; a second
  control inside the Lines grid would be the same action twice. It is HIDDEN unless the
  document's lines agree on exactly one packing list AND one purchase order - which is what
  a CRM SPO always is (one `create` run, one header per supplier, one container). An
  imported or split document has no single SPO for the planner to load, so it gets no
  action rather than a link pointing at whichever half the query met first.

### Review round 1 (captain's rulings + what changed, 6 Sep 2026)

Two rulings, then the findings they settle:

- **R20 amended.** The authoritative record of a RETAIL take is the SPO line's own
  `purchase_order_lines.source_ref.so_coverage` - written by `create` and `revise`, read by
  `_retail_coverage`, `coverage_for_so_lines` and `planner_state`. `scm.order_link_claim
  (source='planner')` stays as an AUDIT ECHO beside it: it is still written, still cleaned up
  by `revise` and (now) by `unwind`, and nothing reads it for quantities. R20's original
  "retail rows write `order_link_claim`" stands as a write; what it is NOT is the record.
- **S3.** `revise` writes its new allocation rows in ONE batch: `forward_match=False`, no
  `create_allocation` commit inside the loop, one commit at the end, no savepoint.

Applied:

- **B1/B2.** `SPOAllocationService.get_document` reads the retail half of `so_covered` from
  `spo_conversion_service._spo_so_coverage_rows(db, po_line_ids=...)`, joined
  `po_line_id -> spo_allocations.po_line_id`, and `linkage.so_count` / `so_qty` follow it.
  Reading the claim made the document disagree with the planner twice over: a claim refused at
  write time (that write cannot fail the confirm) showed nothing covered, and the claim's own
  identity is one row per sales-order line, so two shipment lines of one product taking the
  same sales order kept only the later write. `source_ref` hangs off the SPO LINE, one level
  above the allocation, so a line split across warehouses shows its coverage on the FIRST of
  its allocation rows - the same "first if several" `coverage_for_so_lines` already applies to
  the mirror image of this join, and the only reading that lets `so_qty` foot.
- **B3.** `unwind` deletes this SPO's `OrderLinkClaim(source='planner')` rows beside the
  `OrderInquiryLink` delete, before the allocations they name go.
- **B4.** `create` and `revise` refuse (422) a line that carries `so_takes` with no location
  split, naming the product: "<code> needs a location before it can cover sales orders". Every
  link a confirm writes hangs off an allocation, and a line with no split writes none, so the
  takes were dropped in silence. The planner mirrors it: Create SPO / Save changes disabled
  with the same sentence, naming the row.
- **S1.** The SO-covered picker's footer totals are read through refs, so the frozen columns
  memo prints the live `totalQty` / `totalTaken`.
- **S2.** `_validate_so_takes` takes a `claimed` accumulator spanning every line of ONE request
  and subtracts it from each row's outstanding, in both `create` and `revise`. Two lines of one
  product can now SHARE a row's outstanding but cannot each be given all of it. On the `revise`
  path the guard is present but not reachable end to end: one SPO header is one supplier, and
  `uk_inbound_shipment_lines_ship_prod_sup` forbids one container carrying one product from one
  factory twice, so a revision body never holds two lines of the same product. The `create`
  path (several suppliers, one confirm) is where it bites, and where the test lives.
- **S3.** Per the ruling. `SPOAllocationService.create_allocation` gains `commit=False`
  (flush, no shipment-line refresh, cost capture flushed with it); `_write_allocations` gains
  `commit=False` (no per-row commit, no forward-match sweep, `company_id` returned so the
  caller can fire the sweep after its own commit); `revise` commits once, through
  `refresh_shipment_line_statuses`, and then forward-matches once for the document.
- **S4.** No code change. `refresh_shipment_line_statuses` carries a caveat comment, and
  BL-060 in `documentation/backlogs/backlog.md` records the defect:
  `spo_allocated_quantity` is summed per PRODUCT, not per shipment line.
- **S5.** Save changes is disabled when no line is left included, with "An SPO has to keep at
  least one line - delete it instead" - the sentence the server already refuses with.
- **S6/S7.** The picker's tabs open sorted by Delivery date ascending and re-sort on a header
  click (AC-I4, now under test), and it reports the order it is SHOWING (project tab then
  retail, each in its own sort) through `onOrderChange`. The planner's Take cascade walks that
  order, so "the rows after the one she edited" means the rows after it ON SCREEN. A row a
  filter has hidden keeps the server's own place, at the end of the walk.
- **S8.** The SPO document's "Edit in planner" links to
  `/procurement-management/packing-lists/{shipment}/spo?edit={po}` - the planner's own route,
  which `?tab=spo` was not.
- **Nits.** The `useSearchParams` consumer on that page sits under a `Suspense` boundary;
  `SPODocumentLineSOCovered` is a named FE interface with `document: string | null` (the dash
  fallback the picker already renders); `planner_state` hands back only THIS line's own take
  when it strips `taken_by` (one occurrence, so a SIBLING line of the same SPO covering the
  same row is still named); `_write_allocations` reports the ROUNDED integer that was actually
  written, the same figure `revise`'s update branch reports.

Two more deviations this round makes explicit, neither a change of behaviour:

- **The `Class` column of the SO-covered picker is not sortable** (AC-I4 names the other seven
  columns). It paints `demand_class`, which the tab strip has already partitioned by `kind`, so
  sorting it inside a tab would order a column that reads almost the same value all the way
  down.
- **`so_line_ids` is gone from the confirm payload**, replaced by `so_takes: [{key, qty}]`
  (R19). Nothing else sent it: the planner is its only caller, and the service's own validation
  is what turns a key into a quantity.
