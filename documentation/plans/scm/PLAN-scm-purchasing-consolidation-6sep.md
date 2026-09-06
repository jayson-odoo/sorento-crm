# PLAN - purchasing consolidation batch (6 Sep 2026)

**Status:** Markup round 1 applied (captain, 6 Sep 2026): Q1-Q5 ruled, R1 and R7 revised,
R11 clarified. UAC:
`scm-purchasing-consolidation-6sep-acceptance-criteria.md`. Lavish page:
`mockups/purchasing-consolidation-6sep-plan.html`. **Lane A (section 13: 1, 2 (R3 only), 3, 8,
10 (R22)) built, browser-verified, review round 1 applied.** B/C/D awaiting GO.

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

## Deviations (lane A)

- **Section 1 breadcrumbs are NOT hardcoded per page.** The plan's "What exists" measurement
  (`href="/scm">Supply Chain`) predates a wayfinding standardisation
  (`components/common/PageHeader.tsx` + `hooks/use-menu.ts`'s `getBreadcrumb`, enforced by
  `PageHeader.inventory.test.ts` S5-02: "no page builds its own breadcrumb"). Every page in this
  batch (`scm/reorder`, `scm/loading-plan`, `scm/purchase-orders`, `scm/proforma-invoices`,
  `project-sales/order-inquiries`, `scm/sales-orders`, and their `[id]` children) renders
  `<PageHeader title=... />` with no `crumbs` override, so the trail is derived live from
  `MENU_SIDEBAR`. Moving the menu leaves (this lane's `config/menu.config.tsx` edit) is the whole
  fix; no page file needed touching. Verified: `PageHeader.inventory.test.ts` and
  `PageHeader.test.tsx` both green after the menu move, and `grep -rn "crumbs="` across the six
  route trees returns nothing.
- **`PackingListUploadDialog` gained a self-serve supplier picker.** R3 moves the dialog to the
  Packing Lists page, which (unlike `/scm/incoming`) carries no persistent supplier filter to
  source `supplierId` from. Rather than build a second, page-level picker, the dialog itself now
  manages an internal `internalSupplierId` when its `supplierId` prop is left `undefined`; every
  other caller (`IncomingContainersView.tsx`) still passes an explicit `supplierId`/`supplierName`
  and is unchanged. Documented in the dialog's own JSDoc.
- **Step 10's "packing_list_service.apply() ... and the route" needed a THIRD change the brief
  didn't ask for: an opt-in `file_in_drive` flag, default `False`.** Filing unconditionally broke
  every OTHER `pg_session`-based test of `apply()` (`tests/scm/test_packing_list_import.py`, three
  tests) - the shared dev DB already carries a real "Packing List" attachment type (admin data),
  so an unconditional file-and-bind step made those tests perform a LIVE upload against the
  configured staging storage bucket the moment they called `apply()`, which is not something any
  test should ever do silently. Only `POST /packing-lists/apply` passes `file_in_drive=True`;
  every other existing caller (all of them tests) is unaffected. See the docstring on
  `test_packing_list_apply_files_attachment.py` for the full story.
- **Attachment-type lookup for step 10:** `code = 'packing_list' OR lower(type_name) = 'packing
  list'`, mirroring `container_status_document.py`'s existing `code = :code OR type_name = :name`
  convention (case-insensitive added because R4 doesn't guarantee the admin sets a code at all).
  Unlike that module, this lookup never auto-creates the type - a missing one is a named gap in
  the response, never a reason to fail an otherwise-successful apply (R4 is admin-set, not
  guaranteed to exist).
- **`consolidated_packing_list.build()` keeps emitting `costs` in its JSON payload.** The plan
  offered either choice ("may keep emitting costs ... or drop it; pick the smaller diff"); keeping
  it is the smaller diff and harmless - only `to_xlsx()` (the export) stops reading it.

## Deviations (lane C)

- **Q1's `forwarder_order_ref` reassignment is a change to `packing_list_service.apply()`
  itself, not something layered on top for the new dialog only.** `bl_no` fed
  `bill_of_lading_number` there since before this lane; the plan's own R14 text says the
  value moves to `forwarder_order_ref` instead, with `bill_of_lading_number` left for the
  manual form - so the SAME "Upload packing list" CTA lane A shipped (still the same
  function) now fills the SO field instead of the B/L field too, not only uploads made
  through the new supplier-documents dialog. The one existing regression test that pinned
  the old mapping (`test_packing_list_import.py`) is updated to the new one, named for what
  it now proves.
- **A stated `pi_number` shared by two containers gets a container suffix at STORAGE time,
  not at read time.** The Jiexia proforma invoice states ONE invoice number
  (`2026JXL0726`) for two containers, and `scm.proforma_invoice`'s identity is
  `(company, supplier, pi_number)` - one row per number. Applying both container
  "documents" the reader now yields would have the second silently overwrite the first
  (same row, its lines replaced). `proforma_invoice_service.pi_number_for` now appends the
  container when the document ALSO names one (`2026JXL0726-WHSU6243088`), so each container
  gets its own row and its own priced lines; a document naming no container (every fixture
  before this one) is unaffected and keeps its number verbatim. The READER's own
  `pi_number` field (what the preview shows, what AC-F2 pins) is untouched - only the
  service's derived storage key changed.
- **`classify()` does not use bare `"INVOICE"` as a proforma-invoice title marker**, only
  `发票` / `PROFORMA INVOICE`. The packing list's own labelled cell states `INVOICE NO.:
  ...` (the SAME invoice number both documents carry), which made every packing list
  misclassify as `combined` under the plan's literal marker list.
- **R14's price matching does not call `convert_to_draft_shipment`.** That function's whole
  job is minting a brand NEW draft shipment; the shipment already exists here (packing_list
  apply already created it, one per block, before the match runs). `supplier_document_
  service._match_prices` instead writes `proforma_invoice_shipment_link` rows directly, in
  the exact shape that function writes them, matched by the shipment line's and the PI
  line's shared `product_id` - not the supplier's own item-code text, which the two
  documents do not always spell alike (`洁厦型号`/`JIEXIA MODEL` vs `客户型号`). Runs for
  every (supplier, container) pair the supplier holds on every apply, rather than only the
  files just uploaded, so all three upload orders (together, PL after PI, PI after PL) are
  answered by the same, idempotent pass.
- **No live `TestClient` route test for `/supplier-documents/preview|apply`.** Migration
  483 has not been run with `alembic upgrade head` against the shared dev database (see
  `sorento_crm_backend/CLAUDE.md`'s note on that gap), so a route test built the usual way
  (`test_fulfilment_routes.py`'s `requires_pg` + real DB) would read an alias table missing
  this batch's rows. `tests/scm/test_supplier_document_service.py` exercises the exact same
  service the route calls, end to end, against a scratch schema seeded with the migrations'
  own `seed()` functions (`test_packing_list_kailu.py`'s pattern) instead. The tester should
  add the route-level test once the migration has actually run somewhere reachable.
- **`ProformaUploadDialog.tsx` is NOT deleted.** `PlanContainerDialog.tsx` (the loading
  plan) still imports `verdictFromPreview` from it - a named function, not the component -
  so the file stays; only `ProformaInvoicesView.tsx`'s own usage of the DIALOG COMPONENT
  moved to the shared `PackingListUploadDialog`.
- **AC-G4's Translations page uses the deferred-action delete pattern
  (`useDeferredRowAction`/`translation_memory.delete`, D7), not `ConfirmDeleteDialog`.**
  The UAC's own words ("hard delete with confirmation") predate this codebase's own
  retirement of that dialog: this worktree's current `CLAUDE.md` says "Delete = hard
  delete, no confirmation dialog ... `ConfirmDeleteDialog` is retired - a new importer of
  it ... is a defect", and every other admin list built since (message snippets,
  supplier code aliases) already uses the countdown-toast delete instead. Followed the
  code over the plan text; the row itself is still a genuine hard delete, only the
  confirmation UX changed to match the rest of the app.
- **`_pl_blocks`/`_pi_blocks`'s new `lines` array is NOT every line in the block.** Only
  a line that carries something translatable: an UNMATCHED line's own 品名 description
  (ruling 5, 3 Sep batch: a matched line shows the product master name, needs no
  translation) or a MATCHED line's remark (only a matched line becomes a shipment line,
  so only its remark ever round-trips into `remarks`). A block with a hundred plain
  matched lines and no remarks shows an empty `lines` array, which is correct, not a bug.
- **Text with no CJK character is never sent to the AI, even on a genuine miss.** A
  supplier's own English remark ("loaded first", "as packed") is not Chinese and has
  nothing to translate; asking anyway would be a network round trip on every apply,
  memory or not, and would have made every existing packing-list test whose fixtures use
  a plain-English remark column (`test_packing_list_multi_supplier.py`,
  `test_packing_list_apply_files_attachment.py`) issue a live call to the real
  `OPENAI_API_KEY` `.env` carries for the app itself. Not asked for by R15/R16 in so many
  words, but a direct consequence of "the model only fills gaps" - an English remark has
  no gap.
