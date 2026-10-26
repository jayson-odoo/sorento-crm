# Inventory C: AutoCount ingest, timing gap, SO side, emails, chatbot/MCP, SPO/PO screens

Worktree HEAD 1a92da8b91 (= origin/main 263643ae36 + a docs commit). All paths relative to
`sorento_crm-linkage-unify/`; `BE` = `sorento_crm_backend/`, `FE` = `sorento_crm_frontend/`,
`MCP` = `sorento_crm_mcp/`. Read-only scout, nothing run (no DB, no tests). Anything not read
in code is marked UNVERIFIED.

Correction to the brief: `outstanding_import_service.py` lives at
`BE/app/services/scm/outstanding_import_service.py` (not `app/services/`), and
`procurement_service.py:4537-4566` is now GRN picking-line creation
(`_create_grn_lines_with_spo_fifo`), not the receipt write. The receipt write is
`_write_received` at `BE/app/services/procurement_service.py:4745`.

---------------------------------------------------------------------------
## 0. Vocabulary: five different things are all called "received"

| Column | Written by | Meaning in practice |
| --- | --- | --- |
| `purchase_order_lines.qty_received` | AutoCount push `qty_received` = TransferedQty (`BE/app/services/document_ingest_service.py:276`, `line_delivered_field="qty_received"` at :286); xlsx upload `qty_fulfilled` (`BE/app/services/scm/outstanding_import_service.py:226`, `_write_settled` :1945) | TRANSFERRED onto another document, never "landed". Includes Cancel PO quantity (`BE/app/models/procurement.py:927-930`: "`qty_received` stays TransferedQty, which INCLUDES this [qty_cancelled]"). Owner 24 Sep: "PO received 7 means it is converted to SPO, it doesn't mean it is received" (`documentation/plans/scm/PLAN-r7-landed-reads-spo-received.md:23-32`). |
| `spo_allocations.quantity_received` | (a) AutoCount push `qty_received` rounded, max-with-stored (`BE/app/services/shipping_order_ingest_service.py:899,907,1022-1023`); (b) xlsx upload `_write_spo_lines` (`outstanding_import_service.py:1497-1566`); (c) GRN recompute `_write_received` (`procurement_service.py:4745-4770`, sums APPROVED goods_received picking lines) | The only column that can mean landed, but (a) is AutoCount's SPO TransferedQty (transferred onward to GR/PI), (c) is a CRM GRN. `stated_received` (`models/procurement.py:580`) = the declared floor; "received shown = received - qty_cancelled" for SPO (`:583`). |
| `inbound_shipment_lines.quantity_received` | `refresh_shipment_line_statuses` (`procurement_service.py:1301`) from APPROVED GRN picking lines only (`get_received_quantities_by_product` :1094) | GRN-proven physical receipt per container line. Independent of the two above. |
| `inbound_shipments.actual_arrival_date` | packing-list external API (`BE/app/api/v1/external/packing_lists.py:184,193`) or the shipment screens. NOT AutoCount. | "Landed" flag used by `spo_supply.open_incoming_clauses` (`BE/app/services/scm/spo_supply.py:76`). |
| `stock.quantity_on_hand` | AutoCount `stock_balances` push (`BE/app/services/stock_balance_ingest_service.py`, `_apply` :521) | On hand. Written alone, independent of every SPO/PO/shipment column above. |

---------------------------------------------------------------------------
## 1. AutoCount ingest / writers (question 1)

### W1 PO document ingest (`DocumentIngestService`, entity `purchase_orders`)
- PO line values: `_line_values` `BE/app/services/document_ingest_service.py:1318`. `qty_received`
  straight from the payload (TransferedQty); `line_status` from `_line_status` :1881 (cancelled
  wins, else `closed` iff delivered >= ordered > 0, else `open`). The V5 raw pass-through
  `from_so_line_ref`, `from_po_line_ref`, `from_po_number` (:1403-1406) are written only when
  named in the payload (`model_fields_set`, absent-vs-null) so a narrower re-push never clears
  them.
- Nothing in this service looks at SPOs. A PO line flips to `qty_received>0` / `closed` the
  moment the PO push says so, whether or not any SPO row exists.
- Post-commit hooks, `BE/app/api/v1/external/ingest.py`:
  `supersede_crm_raised_pos` (:~523), `ProjectOrderInquiryService.relink_to_matching_lines`
  (:~534; moves a link ONLY between lines of ONE PO to the line whose warehouse fits, never to
  an SPO: `project_order_inquiry_service.py:13195`, write at :13328 `link.po_line_id = target`),
  `follow_book_repairing` for SO ref moves, `_run_follow_book_po_hook` (:699).

### W2 SPO (shipping order) ingest (`ShippingOrderIngestService`, entity `shipping_orders`)
- `_line_values` `BE/app/services/shipping_order_ingest_service.py:863`: `allocated_quantity=
  round(qty_ordered)`, `quantity_received=round(qty_received)`, `receipt_status = pending |
  fully_received`, `line_status = open | closed` from `ordered - received` (:899-914),
  `expected_date = line.expected_date or header.expected_date` (:909). `from_po_line_ref` and
  `from_po_number` pass through raw only if named (:934-937). No shipment arrival date, no ETA
  other than `expected_date` comes from this ingest.
- `_write_row` :970: `quantity_received = max(stored, declared)` (:1022-1023) so a re-push never
  lowers a receipt; `stated_received` floor; `cancelled` forces `closed` (:1033-1034);
  `retired_at` cleared when named; container linked via `shipping_order_rules.link_allocation_to_shipment`.
- A line AutoCount stops naming is closed/retired, never deleted; `visible_line_clauses`
  (`spo_supply.py:80`) hides retired-with-nothing-received lines from every reader.
- Hooks (`ingest.py`): forward-match GRN lines (:~560), `_run_shipping_order_book_repair_hook`
  (:604), shipment line refresh (:~632), `_run_follow_book_spo_hook` (:789).

### W3 xlsx "Outstanding" upload (`BE/app/services/scm/outstanding_import_service.py`)
- SPO half `_write_spo_lines` :1497: writes `allocated_quantity`, `quantity_received`
  (`_spo_quantities` :1478, from the file's `qty_fulfilled`), `receipt_status`, `line_status`
  (:1545-1566). Rows are `source_system = SPO_UPLOAD_SOURCE`; this path sets NO `from_po_number`,
  `from_po_line_ref`, `from_so_line_ref`. PO half: `_write_change` :2311 / `_write_settled`
  :1945 write `qty_received` from the file. `_claim_stated_so_links` :2522 writes
  `scm.order_link_claim` rows (source `po_upload`), not OI links.
- So an xlsx-era SPO row can never be found by the OI-SPO-EXACT key (no `from_po_*`).
  `shipping_order_ingest_service` adopts these rows by `(product, location)` (module docstring
  :19-30) but only restates fields named in the payload.

### W4 GRN receipt recompute
- `procurement_service.py:4745 _write_received`: sets `quantity_received`, `receipt_status`,
  `line_status` (closed + fully_received when received >= allocated; may re-open). This is the
  CRM-side receipt on an SPO line, distinct from AutoCount's stated figure.

### W5 stock balance ingest (`BE/app/services/stock_balance_ingest_service.py`)
- Module docstring :1-40: "Only `quantity_on_hand` is ever written". It never reads or writes
  `spo_allocations`, `purchase_order_lines`, `inbound_shipments` or `order_inquiry_links`.

### W6 Shipment arrival dates
- Only `external/packing_lists.py:184-193` (n8n / ESB packing list) and the CRM shipment screens
  set `estimated_arrival_date`, `actual_arrival_date`, `eta_delay_date`. AutoCount ingest does not.

### W7 SO<->PO book linkage (#764 and the claim writers)
- Ingest writes `scm.order_link_claim` rows via `order_link_service.write_line_ref_claims`
  (`BE/app/services/scm/order_link_service.py:526`; called from `document_ingest_service.py:845`
  and `shipping_order_ingest_service.py:644`). Claims are a separate table, consumed as "source 2"
  of `pair_needs` (`project_order_inquiry_import_service.py:2160`), not `order_inquiry_links`.
- Display of the book linkage: `order_link_service.book_so_fields` :795 (three-state
  `book_so_number` / `book_so_unresolved` off `from_so_line_ref`), PR #764 (3c3738ad76).

### Q1 answer: does any ingest rewrite `order_inquiry_links` when a PO line is transferred?
NO repoint PO-line link -> SPO link exists. Evidence:
- The only ingest hooks that write OI links are `follow_book_for_rows`
  (`project_order_inquiry_service.py:3738`, called from `_run_follow_book_po_hook`
  `ingest.py:699` and `_run_follow_book_spo_hook` :789), `follow_book_repairing` (:3415) and
  `relink_to_matching_lines` (:13195).
- `follow_book_for_rows` only ADDS links for rows that still have unmet need
  (`_unlinked_need`, :~3850) onto book-named targets, and may DISPLACE other lines' links on a
  target (D3, `_displace_other_line_holders` :~4075). An already-satisfied row (it holds a PO-line
  link) is skipped, so the PO-line link stays after the PO transfers.
- `relink_to_matching_lines` moves a link between lines of the SAME PO only.
- Instead, the transfer is handled at READ time: `_less_own_shipments`
  (`project_order_inquiry_import_service.py:2081`) shrinks the PO line's capacity by the SPOs it
  became so new placements do not double count, and readers follow the PO link to its SPO(s) by
  the OI-SPO-EXACT key (R2, R7, R13 below). Existing PO-line links therefore remain `kind=po`
  forever; the SPO appears as a synthetic "derived" entry (`links_for_rows`, :8391) or inside a
  Stock Debt hold (SUPPLY-SPO-LINK, #1850).

### Q1b: "PO received, no SPO" variant (PO line qty_received>0 but no SPO row names it)
Why it can happen, from code (none of these needs a bug):
1. PO and SPO are independent pushes (entities `purchase_orders` vs `shipping_orders`,
   separate ingest services, separate envelopes). `qty_received` on the PO is accepted as sent
   (`document_ingest_service.py:276,286`); nothing verifies an SPO exists. SPO arrives later
   (or in a later ESB cycle): between pushes the PO reads transferred, no SPO.
2. The SPO row is invisible to the join: `visible_line_clauses` hides a retired line with 0
   received (`spo_supply.py:80-114`); D30 supersede may close/remove rows; `delete_document`
   hard-deletes (`procurement_service.py:~3290`).
3. The SPO row exists but cannot match the key: SPO pushed without `from_po_*` fields (absent
   field is never written, `shipping_order_ingest_service.py:934-937`); xlsx-written SPO rows
   (W3) carry none; blank/space-padded `from_po_line_ref` (K1 trims, K2/K3/K5 do not); PO line
   with blank `source_ref` reaches nothing (`order_inquiry_worklist_service.py:2737`
   `coalesce(btrim(source_ref),'') != ''`); the August extract wrote bare ordinals as
   `source_ref` (`project_order_inquiry_import_service.py:2038-2044`); product differs between
   PO line and SPO line (K1/K2 include `product_id`); company differs (inter-company transfer
   chain, `models/procurement.py:962-967` "inter-company book transfer chain").
4. TransferedQty includes Cancel PO documents (`models/procurement.py:927-930`, AC-CANCEL-CRM):
   a line cancelled by a Cancel PO document reads `qty_received>0` with no SPO at all. The PO
   Lines tab compensates (`purchase_order_service.py:~203-205` shows `qty_received - qty_cancelled`)
   but the OI PO lightbox and `links_for_rows` read the raw figure (R7, R2).
5. UNVERIFIED: a PO transferred straight to a Purchase Invoice / Goods Received in AutoCount
   with no shipping order. Owner doctrine says "all PO received via SPO for order inquiries"
   (`PLAN-r7-landed-reads-spo-received.md:30`) but nothing in code enforces it. No measured count
   of this population exists in the repo (UNVERIFIED; no DB access in this scout).
Consequences for readers: R2 marks the PO link `received=True` (qty_received>=qty_ordered) with
no SPO to say otherwise; R10 `received_links_of` treats it as a fully received document and the
CS-reserve flow can release it; R12 (own-arrival credit) gives it 0 landed (AC-3); R13 drops it
from Stock Debt supply (PO branch only holds what is still on order).

---------------------------------------------------------------------------
## 2. Timing gap (question 2): OPEN

Source: `documentation/plans/scm/PLAN-spo-received-pin.md:27-30` and :94 ("Out of scope: the
stock-balance timing double count ... and its mirror image").
Evidence it is still open:
- No commit on origin/main touching `spo_supply.py`, `supply_assignment.py` or
  `stock_balance_ingest_service.py` after #1388 (be50317bf1, 30 Sep) addresses it. Later commits
  on those files: #1389 PO-NO-AUTO-ASSIGN, #1398 LENDABLE, #1421 SO-TRANSFERABLE (stock balance
  file, unrelated), #1538, #1589, #1597, #1658 STOCK-DEBT-STALE-PIN, #1764 BOARD-ETA-PERM, #1850
  SUPPLY-SPO-LINK. `git log --grep` for timing / balance / double count finds none that closes it.
- #1658 (509f3de16f) caps a pin at bin stock and drops a pin on an empty in-span bin. That
  protects against over-cover but does NOT detect "goods on hand AND SPO still open": the SPO
  hold is still an SPO hold while `open_incoming_clauses` passes.
- #1850 (6222c582b1) covers PO-line placements (follow the goods onto the SPO). Its own text says
  the SPO branch still keys on `open_incoming_clauses` / `_landed_qty`.
- `_landed_qty` (`BE/app/services/scm/stock_debt_service.py:158`) treats "landed" as
  `quantity_received>0`, OR shipment `actual_arrival_date` set, OR `receipt_status` received. A
  stock-balance push does not set any of these, so the window "on hand written, SPO
  quantity_received not yet written and no shipment arrival" is still counted as incoming supply
  AND on hand.
- `stock_balance_ingest_service.py` writes only `quantity_on_hand` (docstring :17-21).
- `PLAN-spo-received-pin.md` is still in `documentation/plans/scm/` (not archived), consistent
  with the plan listing the gap as out of scope.
Mirror image (also open, by design): shipment arrival date lands before the stock balance push
(attribution early; plan :94-96).

---------------------------------------------------------------------------
## 3. Match keys in use (so the table below can reference them)

- K1 OI-SPO-EXACT: `SPO.from_po_number = PO.po_number AND btrim(SPO.from_po_line_ref) =
  btrim(POL.source_ref) AND SPO.product_id = POL.product_id` (+ `source_ref` non blank on
  worklist side, company predicate by hand). Used by: `_chain_allocations`
  (`project_order_inquiry_import_service.py:2020`, strip in Python), `_derived_spo_query`
  (`order_inquiry_worklist_service.py:1107`), `_spo_numbers_by_po_line` (:2716),
  `_append_derived_spo_entries` (`project_order_inquiry_service.py:8391`),
  `_transferred_allocations` (`stock_debt_service.py:1957`, tuple IN, company predicate).
- K2 `SPO.from_po_line_ref = POL.source_ref AND SPO.product_id = POL.product_id` (NO
  `from_po_number`, NO btrim; company equality only in the single-key variant at
  `project_supply_service.py:~3140` and batched :3420): `_po_received_by_so_line_ref` :3107,
  `_po_received_by_product` :3184 (company NOT stated, :3207-3216).
- K3 `SPO.from_po_number = PO.po_number AND SPO.from_po_line_ref = POL.source_ref AND company_id
  equal` (NO btrim, NO product): `po_lines_with_open_chained_spo`
  (`project_order_inquiry_service.py:13453`, :13466-13475).
- K4 `(from_po_number, strip(from_po_line_ref))` vs `(po_number, source_ref)`, NO product:
  `_refs_from_written_spo_allocations` (`ingest.py:735`).
- K5 `(po_number, source_ref)` exact, NO strip, NO product, ambiguous (>1) = refuse:
  `_book_names_target_for_line` (`project_order_inquiry_service.py:4014`).
- K6 text only, `from_po_number` with no line ref and no link: `get_document` /
  `get_spo_detail` / `links_for_rows.source_po_number` (display).
- K7 FK `spo_allocations.po_line_id` (Sorento-raised SPOs only; AutoCount rows never set it,
  `models/procurement.py:~529`, plan #764 section 0 measured 0 of 80,468):
  `get_document` PO column, `coverage_for_so_lines`.

---------------------------------------------------------------------------
## 4. Reader inventory

Legend for "states": O=open, T=in transit (open SPO with shipment not landed), L=landed
(shipment arrived / receipt written), P=partly received, F=fully received, C=closed,
X=cancelled. Quantity column says which figure is summed or shown.

| id | screen / consumer | file:line + function | SO line -> PO line | PO line -> SPO line (key) | states counted | quantity used | how it differs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | SO detail (SCM) Lines tab, "Linked to" column and lightbox | `BE/app/services/scm/sales_order_service.py:855 _line_links`, :925 `_spo_line_links`, :943 `_linked_to_for`; FE `FE/app/(protected)/scm/sales-orders/[id]/components/SalesOrderDetail.tsx:1112-1143` | core SO line -> `ProjectSalesOrderLine.core_sales_order_line_id` -> `OrderInquiryRow.so_line_id` -> `order_inquiry_links` (real links only), via ONE call to `links_for_rows` (R2). Retail lines: `coverage_for_so_lines` (`spo_conversion_service.py:892`, SPO `source_ref.so_coverage` JSON) | via R2 (K1 derived entries, open SPO only) | whatever R2 returns; retail half has no state filter I read | sum of link `qty` (FE `reduce`), per-link `late`/`late_days`/`expected_date` | Shows ONLY where an order inquiry row placed the line. A line with no inquiry row reads "-" even if the book names PO/SPO for it (`from_so_line_ref` is not read here). No landed/received indicator on the grid itself (only inside the lightbox via R2 fields if rendered: UNVERIFIED which FE columns show `received`). |
| R2 | `links_for_rows`: the one reader of `order_inquiry_links` for a screen (SO detail, OI worklist, per-project list) | `BE/app/services/project_order_inquiry_service.py:8081`; derived SPO entries :8391 `_append_derived_spo_entries`; open predicate :366 `derived_spo_open_clauses` | link row -> its `po_line_id` / `spo_allocation_id` (real links) | K1 (PO link -> each OPEN SPO line it became, as synthetic `derived-<id>` entries, `qty = allocated - received`, only if `retired_at IS NULL AND allocated > received AND open_incoming_clauses`) | per real link: `received` = PO: `line_status=closed OR (qty_ordered>0 AND qty_received>=qty_ordered)` (:8283-8292); SPO: NOT open (line closed OR receipt_status received OR shipment `actual_arrival_date` set, :8262-8271). Derived entries: open/in transit only; a landed or fully received SPO disappears | real link `qty`; `received_qty` = PO `qty_received` (TRANSFER) or SPO `quantity_received`; derived `qty` = SPO `allocated - received` | The PO-kind `received` flag uses TRANSFER qty, so a PO line transferred to an in-transit SPO reads `received=True` (while its derived SPO entry says open). `expected_date`/`late` use PO line date for PO links, SPO `expected_date` for SPO links, never shipment ETA (`eta_delay_date`). |
| R3 | Order Inquiry worklist "PO no / SPO no / Linked to" cells and filters `kind=spo`, `linked=spo`, `spo_number` | `BE/app/services/order_inquiry_worklist_service.py:1107 _derived_spo_query` (EXISTS), :2716 | OI row -> real PO links | K1 (shares `derived_spo_open_clauses` with R2) | open/in transit only | derived cover SUM `_derived_cover_qty` | Covered by OI-screen scouts; listed only because it shares K1 and R2's open predicate. |
| R4 | SO detail Lines tab: status / outstanding / delivered / delivery date; the "Suggested / Decided / Decision" planning columns | `BE/app/services/scm/sales_order_service.py:402 serialize`, :495 `outstanding`, :512-:600 line dict; FE `SalesOrderDetail.tsx:1032-1112` (Qty delivered, Outstanding), :1244-1251 "Delivery date" (= `required_date`), :1294-1315 Status | none (SO-side facts only) | none | `line_status` open/closed/cancelled; outstanding = 0 unless open, else `max(ordered - delivered,0)` | SO `qty_delivered` (minus `qty_cancelled`) | "Delivery date" is the customer's `required_date`, not an ETA. There is NO ETA, "where is my order" or supply-location field on an SO line except via R1/R2 (`linked_to[].expected_date`, `late`) and the planning compositions `supply_decided|proposed|saved` (`sales_order_service.py:~560-590`, vocabulary `FE/app/(protected)/project-sales/_shared/lib/supplyVocabulary.ts`; UNVERIFIED what their live source is: frozen revision snapshots, not live PO/SPO state). |
| R5 | SO detail Delivery tab and truck lightbox | `BE/app/services/scm/so_line_history.py` via `GET /scm/sales-orders/{id}/deliveries` (PLAN-do-so-link-surface-25oct.md:36-40,66-68); FE `SalesOrderDetail.tsx:~2284-2314` | SO line -> DO lines (`order_lines.sales_order_line_id`, else product on the ONE SO line) | n/a | DO status | DO line qty | Purely sales-delivery side. Says nothing about supply. Read from the plan, file not opened: UNVERIFIED line detail. |
| R6 | PO detail (SCM) Lines tab | `BE/app/services/scm/purchase_order_service.py:145 serialize` (:~203 received, :~178 outstanding); FE `FE/app/(protected)/scm/purchase-orders/[id]/components/PurchaseOrderDetail.tsx:592-642 (Qty received / cancelled / Outstanding), :847-856 S/O (book_so), :861-868 "Delivery date", :896 Status` | PO line `from_so_line_ref` -> `order_link_service.book_so_numbers_by_ref` (doc-level join on `sales_orders.source_ref`, :~731) | NONE (no SPO column on this screen; #1850 added the SPO column only to the OI PO lightbox R7) | `_is_open_line`; outstanding = 0 if not open else `max(ordered - received, 0)` | `qty_received - qty_cancelled` shown as "Qty received"; outstanding uses raw `qty_received` (includes cancelled) | Shows the TRANSFER figure under the label "Qty received". Book S/O is three-state (no ref / resolves / "linked, not held"), independent of OI links. |
| R7 | OI "PO no" lightbox (shared by Stock Debt Supply / Covered by, OI screens) | `BE/app/services/order_inquiry_worklist_service.py:2595 get_po_detail`, :2716 `_spo_numbers_by_po_line`; FE `OrderInquiryDocumentDialog.tsx:344 PO_LINE_COLUMNS`, :434 `spo_numbers` column | PO id from the link / cell | K1, ALL visible allocations (landed or not), distinct sorted SPO numbers per PO line | none filtered (states not shown, numbers only) | `qty_received` raw, `remaining = ordered - received` (:2680), `allocated` = sum of live OI link qty per line | Raw transfer figure with no cancel netting. SPO numbers list is state-blind; the SPO landing state is only visible by opening the SPO lightbox (R8). |
| R8 | OI "SPO no" lightbox | `order_inquiry_worklist_service.py:2759 get_spo_detail`; FE `OrderInquiryDocumentDialog.tsx:497 received, :535 source_po_number` | SPO number | K6 text only: `source_po_number = from_po_number` (:2882); NOT linked to the PO line | every VISIBLE line, no state filter | `allocated`, `received`, `remaining = allocated - received` | Header ETA = `min(expected_date)` of lines (:2851-2857), ignores shipment `estimated_arrival_date` / `eta_delay_date` and `actual_arrival_date`. Differs from R9 which prefers shipment ETA. |
| R9 | SPO document detail page (Procurement > SPO allocations) | `BE/app/services/procurement_service.py:2942 get_document`; FE `FE/app/(protected)/procurement-management/spo-allocations/components/SPODocumentDetail.tsx` (PO col :783-805, PO (book) :806-826, strip :1030-1075) | `so_covered`: (a) `order_inquiry_links.spo_allocation_id` direct (:3055-3095), (b) retail via `po_line_id` FK + `_spo_conv._spo_so_coverage_rows` | K6 text `from_po_number` ("PO (book)", plain text, no line ref, not a link) and K7 FK `po_line_id` ("PO" column, link; empty for AutoCount rows) | `outstanding` = `open_incoming_clauses` AND `allocated > received` (:3194-3195); a closed/fully received/landed line reads balance 0 | `allocated`, `quantity_received`, `balance`, `arrival_date` = shipment `eta_delay_date or estimated_arrival_date`, else `expected_date` (:3187-3190) | The only reader that prefers shipment ETA/eta_delay. Does NOT list the SO lines that reached the SPO only through a PO-line link (the `so_covered` read at :3055 is by `spo_allocation_id`, so PO-linked OI rows never appear: derived link is not followed here). Header status `outstanding`/`completed`. |
| R10 | "Received" test for OI links; CS "Request reserve" flow; received pill | `project_order_inquiry_service.py:3346 _received_documents_for`, :13487 `received_links_of`, :13453 `po_lines_with_open_chained_spo`; consumers `order_inquiry_reserve_service.py:124-146 _requestable` | link -> its PO line / SPO line | K3 (no btrim, no product) to BLOCK a received PO link when an open chained SPO exists (:13465-13476) | PO: closed or `received>=ordered` (TRANSFER); SPO: not open (:3394-3402). PO link blocked from "received" while ANY open visible SPO names the line. | link `qty` | A PO line with transfer>0 and NO SPO row (Q1b) is "received" and releasable. K3 differs from K1 (see section 3): a space-padded `from_po_line_ref` or a different-product SPO row changes the answer between R10 and R2/R7. |
| R11 | Placement engine: `pair_needs`, follow-book, cascade, importer | `project_order_inquiry_import_service.py:2160 pair_needs`, :2310 `_through_po`, :2020 `_chain_allocations`, :2081 `_less_own_shipments`, :1849 `_target_facts`; `project_order_inquiry_service.py:3738 follow_book_for_rows` | SO line `source_ref` -> `from_so_line_ref` on SPO then on PO lines (`_bought_rows`, :~1912), then claims (`order_link_claim`, source 2) | K1: PO line -> SPOs first, PO line itself only for the remainder; PO capacity reduced by its chained SPOs (:2118-2130) | PO line live (not cancelled) via `_LIVE_PO_LINE`; SPO via `visible_line_clauses` only (no open test: a landed SPO is still a valid target here) | `qty_ordered` (PO) / `allocated_quantity` (SPO) minus existing link claims; `received` NOT read | Decides which target a NEW link lands on; never rewrites an existing link when the PO transfers (Q1). Uses `qty_ordered` not `ordered - received`: a fully transferred PO line keeps full gross capacity unless an SPO row names it. |
| R12 | Own-arrival credit (board, confirm recheck) | `BE/app/services/project_supply_service.py:3107 _po_received_by_so_line_ref`, :3184 `_po_received_by_product`, :3312 `_prefetch_own_arrival`, :3593 `_own_arrival_credit_components` | SO line `source_ref` -> `PurchaseOrderLine.from_so_line_ref`, same product | K2 (no `from_po_number`, no btrim) | any SPO row whatever its status (inner join); "A PO line with no SPO row naming it contributes nothing" (:3118-3123) | `SPOAllocation.quantity_received` summed per SO ref, capped by on hand at bin | Landed = SPO quantity_received only. Different key from K1 (a same `source_ref` ordinal on another PO with same product would match here; K1 would not). Other agents cover board/supply; recorded for key comparison. |
| R13 | Stock Debt `_holds` (placement -> hold) | `BE/app/services/scm/stock_debt_service.py:1614 _holds`, :1957 `_transferred_allocations`, :158 `_landed_qty`, :175 `_follow_capacity` | OI link -> PO line | K1 (company predicate by hand) | SPO incoming -> SPO hold; landed (`received>0` OR shipment arrived OR receipt_status received) -> on-hand hold at bin; closed with nothing landed -> nothing; PO line holds only `min(link, ordered - received)` while `open_po_line_clauses` passes | SPO `allocated`/`received`; PO `ordered - received` | SUPPLY-SPO-LINK #1850. Owned by supply/stock-debt scout. Landed has three triggers here, but R2/R10 define received as "not open", which treats `line_status=closed` with nothing received as "received" while R13 treats it as holding nothing. |
| R14 | Supply events `_po_rows` | `project_supply_service.py:10067 open_po_line_clauses`, :10100 `_po_rows` | n/a | none | PO status in OPEN_PO_STATUSES, line open, `qty_ordered > qty_received`, not CRM SPO shipping leg | `ordered - received` | A transferred PO line is out of supply by construction. Product-level, not SO-line-level. |
| R15 | MCP `crm_procurement_po_placed_list` | `MCP/sorento_crm_mcp/catalog.py:1465`; endpoint `GET /api/v1/procurement/purchase-orders/placed` `BE/app/api/v1/procurement/purchase_orders.py:86`; service `BE/app/services/purchase_order_service.py:92 purchase_orders_placed_rows` | none (product / warehouse / date filters only) | NONE ("never netted", docstring :1-30 and route :119-122; docstring claim "`po_line_id` is NULL on every row" is a stale-risk statement but true for AutoCount rows) | PO: `line_status='open' AND ordered - received > 0`. SPO: `receipt_status='pending' AND inbound_shipment_id IS NULL AND allocated - received > 0 AND visible` (`_unshipped_spo_query` :~255) | PO `ordered - received`; SPO `allocated - received` | Counts an SPO WITHOUT a shipment as "placed"; an SPO WITH a shipment is excluded (it is in R17). A PO transferred to an SPO is therefore counted once (via the SPO if unshipped), but a PO transferred to a shipped SPO is counted only in R17. No SO-line awareness. ETA = line else header `expected_date`. |
| R16 | MCP `crm_procurement_spo_allocations_last_receipt_list` ("last in") | `MCP catalog.py:1517`; `GET /api/v1/procurement/spo-allocations/last-receipt`; `BE/app/services/spo_last_receipt_service.py:153 last_receipt_rows` | none | none | any visible SPO line; ordering key `expected_date` else `issue_date` else `created_at`; no receipt_status filter (docstring :10-20) | `allocated`, `quantity_received` ("gr_quantity", None when 0), GR date from approved picking | Owner ruling 8 Sep: "last in" is the last SPO line's delivery DATE, not a GRN date. |
| R17 | MCP `crm_incoming_stock_by_product` / `_list` / `_shipments` | `MCP catalog.py:1060-1150`; `/api/v1/incoming-stock/by-product|list|shipments`; `BE/app/services/incoming_stock_service.py:373 incoming_for_product`, :621 `incoming_shipments`, :721 `incoming_list`; `_warehouse_allocations_for` :268 | none (product / shipment / supplier / ETA window) | none: reads `inbound_shipment_lines`, uses `spo_allocations` only for per-warehouse allocation summary (module docstring :36-39); allocation netting uses `allocated - max(received, stated_received)` (:289-315) | line `line_status != 'received'` and `quantity_shipped - quantity_received > 0` (GRN-derived) | `remaining_incoming = shipped - quantity_received` (shipment line, GRN-proven) | Different universe from PO/SPO columns: shipment-rooted, "received" = approved GRN only, so a container that AutoCount shows transferred/landed but with no CRM GRN still reads incoming. ETA = `estimated_arrival_date` (+ contact offset via `eta_policy.py`, `eta_delay_date` gated). Never exposes received qty or SPO numbers by design. |
| R18 | MCP `crm_outstanding_report` | `MCP catalog.py:742`; `GET /api/v1/order-management/outstanding-report`; `BE/app/services/outstanding_report_service.py` | n/a | none (no PO/SPO read; imports only `Order*`, `SalesOrder*`) | SO: open lines; DO: not delivered status ids | SO `ordered`, `qty_delivered` (= transferred to DO), outstanding; DO pending | Backlog only. Cannot answer "where are the goods" at all. |
| R19 | MCP `crm_order_management_orders_list` (incl. `so_outstanding` bucket and `include_pipeline`) and `..._orders_by_product_list` | `MCP catalog.py:607,689`; backend `order_service` (`_delivered_status_ids`, `_outstanding_clause`, imported by `outstanding_report_service.py:36-41`); UNVERIFIED line-level read | n/a | none | DO status buckets (New Order, Processing, In Transit, Cancelled = outstanding; Delivered) | DO line qty; `so_outstanding_qty` over open SO lines | Sales-delivery side only. |
| R20 | Chatbot SO ask ("status of SO421624") and PO card | `BE/app/services/chatbot/so_status.py` (`lookup` :~165, `_lines_by_so` :117, `_delivery_words` :66); `chatbot/ref_status.py` (`_po_lines` :71, card :119-123) | none | none | SO: "Delivery: none / partly / in full" from `qty_delivered`; PO card: header `status`, issue date, SKU x qty_ordered only | SO `qty_ordered` / `qty_delivered` net of cancel | No supply, ETA or location statement for an SO. A dealer asking "where is my SO" gets delivery words only. PO card has no received/transfer/SPO info. |
| R21 | Chatbot stock ask "incoming" branch and dealer ETA | `BE/app/services/stock_ask_service.py` (branches `incoming`, `no_incoming`, `incoming_eta` :32-47); `BE/app/services/incoming_stock_service.py:186 earliest_packing_list_shipment`; ETA policy `BE/app/services/eta_policy.py:1-60` | none (product-level) | none | still-incoming shipment lines with packing list and ETA | `estimated_arrival_date` or `eta_delay_date`, plus `chatbot_eta_offset_days` when the contact's switch is on | Product-level, shipment-rooted (same universe as R17). Not tied to an SO line. |
| R22 | Chatbot MCP lane fetch / answer for incoming and PO tools | `BE/app/services/chatbot/lanes/business/fetch.py:450-452,597,3132-3134,3450 _eta_of`; `answer.py:1024 eta`; `alternatives.py:36-37`; `pickers.py:86 annotate_incoming` | none | none | whatever R15/R17 return | R15/R17 quantities and ETA | The chatbot composes "incoming" answers from R17 and "on order" from R15; no component reconciles PO placed vs shipment incoming vs SO line. |
| R23 | Emails: handover to purchasing (automatic and "Send to purchasing"), changed-with-links, undo, reject | `BE/app/services/project_order_inquiry_service.py:4423 handover_item`, :4393 `_record_handover`, :14015 `_build_handover_context`; `:4317 _dispatch_changed_with_links` (context :4358-4384); `BE/app/services/oi_handover_resend.py` | n/a | none | `raised|settled|cancelled`; resend: rows in `raised`/`partly_linked` (`oi_handover_resend.py:41`) | OI row `qty`, `delivery_date`, `previous_*`, SO number, customer, project | These emails state demand (what to buy, by when), never where supply is or an ETA. The only supply-ish field is `delivery_date` (the row's need date). No PO/SPO/ETA text. |
| R24 | Emails: CS reserve request / reserved notices | `BE/app/services/order_inquiry_reserve_service.py:124-146` (`_requestable` = remaining + received-link qty), :326 `_build_context`, :383 `_build_commit_context`, :374 `_context_reason` ("Released <docs> (received)") | OI row | via R10 | R10 "received" | link qty released | Names released documents as "received" using R10, so a PO line merely transferred (or "PO received, no SPO") is announced as received. |
| R25 | Reorder summary order sheet / low-stock chat workbook (PO and incoming columns) | `BE/app/services/scm/summary_order_service.py:353-361` (`po_open_qty`, `incoming_spo_qty`, docs), `:1593`; `BE/app/services/scm/low_stock_report_service.py:56,198-229`; helper `site_pool_supply.py` (`_po_open_qty_map`, `_incoming_spo_qty_map`) | n/a | none | UNVERIFIED (maps not opened) | `po_open_qty`, `incoming_spo_qty` per product | Product-level "BRW PO qty" / "BRW incoming qty"; the SPO number never printed in the incoming cell, only container. |
| R26 | Packing list / shipment line status | `procurement_service.py:1301 refresh_shipment_line_statuses`, :1344 `compute_shipment_line_figures`, `compute_inbound_shipment_line_status` :453 | n/a | shipment -> SPO via `spo_allocations.inbound_shipment_id` (FK, not from_po_*) | `in_transit | allocated | partially_allocated | partially_received | received` | `quantity_shipped`, visible allocated, GRN-picked received | Third independent "status" vocabulary; feeds R17. |
| R27 | SPO documents list and header status | `procurement_service.py:2556 list_documents`; `spo_supply.py:58 open_incoming_clauses` | n/a | n/a | open iff line open AND receipt_status not received AND shipment not landed (+ `allocated > received` in Python) | allocated / received rollups over VISIBLE lines | The canonical SPO open/landed predicate; R2/R9/R10/R13 reuse it (R15 does NOT: it uses `receipt_status='pending'` + no shipment). |

### How the readers disagree (summary for the unify design)
1. Three "received" for a PO link: R2/R10 use PO transfer qty, R12/R13 use SPO `quantity_received`
   (plus shipment arrival in R13/R27), R17 uses GRN-picked shipment-line qty.
2. Three SPO match keys (K1, K2, K3) plus K4/K5 variants differing in trim, product, company.
3. SPO "open": R27 (line open, receipt not received, shipment not landed) vs R15 (receipt_status
   pending AND no shipment) vs R13 (adds `quantity_received>0` / arrival as landed).
4. ETA: R9 shipment ETA/eta_delay else SPO `expected_date`; R8 `min(expected_date)`; R2 link
   `expected_date` (PO line date or SPO `expected_date`); R15 line else header date; R17/R21
   shipment `estimated_arrival_date` (+offset, `eta_delay_date` gated); SO line has no ETA field.
5. Where an SO line shows its supply: only R1 (via OI row). A line with no inquiry row, or an
   SO the chatbot is asked about (R20), has no PO/SPO/ETA answer anywhere.

---------------------------------------------------------------------------
## 5. UNVERIFIED list
- Population counts for the "PO received, no SPO" variant (no DB access allowed).
- Which FE columns of the SO Lines lightbox render `received` / `received_qty` (R1).
- Live source of `supply_decided|proposed|saved` on SO lines beyond the frozen snapshot (R4).
- `so_line_history.py` and DO ask internals (R5, R19).
- `summary_order_service` PO/incoming maps, `site_pool_supply.py` (R25).
- `_oi_linked_landed_by_ref` (`project_supply_service.py:3245`) detail (R12).
- Whether AutoCount SPO lines actually carry `from_so_line_ref` in prod (only the read path is
  verified: `_refs_from_written_spo_allocations` falls back to the PO line's `from_so_line_ref`
  when the SPO line names none, `ingest.py:735-786`).
- PO transferred to PI/GR with no SPO (Q1b item 5).
