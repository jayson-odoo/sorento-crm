# GR-E: is the AutoCount Goods Received synced, and does it carry bin + qty per PO line

Answer: YES, synced (since 2026-08-21), for the 6 modern placements. NO GR exists in the CRM for the 2 old
PO 202104-S0087 lines and the cancelled MWCX7604 line (UNVERIFIED whether AutoCount has one).

## Code
- Ingest entity `goods_receive_notes` (the AutoCount GR): app/services/autocount_doc_ingest_service.py:82 (entity), :1231 `_apply_grn`,
  :985 `_grn_links`, :949 `_po_or_spo_line`, :799 `_resolve_items`. Route POST /external/ingest/{entity}: app/api/v1/external/ingest.py:1005.
  Pull-on-request path: app/services/autocount_pull_service.py:44-74, app/tasks/autocount_pull_tasks.py:1118-1172.
  Plan: documentation/plans/autocount/PLAN-autocount-grn-pull-crm-02oct.md.
- Lands in public.picking_headers (picking_type='goods_received', source_book 'db1', doc_key = AutoCount DocKey, picking_number = GR no,
  source_record jsonb = raw doc) and public.picking_lines (dtl_key, item_code, location_code = AutoCount Location = the received BIN,
  qty numeric, from_doc_type, from_doc_no = source PO number, po_line_id, spo_allocation_id, source_warehouse_id). picking_date = doc date.
  models: app/models/procurement.py:765 (PickingLine), :840 uq on header+dtl_key.
- Link rule: FromDocDtlKey>0 -> exact PO line by source_ref; FromDocDtlKey=0 (what live data sends) -> FromDocNo names the PO, then
  line-order matching by product (_grn_links). So PO line -> GR is stored as picking_lines.po_line_id.
- Not the CRM-side GRN: procurement_service _write_received creates CRM/Excel GRs (doc_key null, qty null, picking_number GR-.. too).
- stock_ledger (app/models/inventory.py:166): product, warehouse, qty change, reference_type/reference_id text. No AutoCount PO line pointer; not probed beyond columns.
- No TransferTo / to_doc / KnockOff field in PO line payload handling. The GR line itself carries the pointer back (FromDocNo, FromDocType, FromDocDtlKey, FullTransferOption in source_record Details).

## Data (dev DB sorento_cagent_stack). SQL: e-2.sql (PO lines), e-3.sql (AC GR lines), e-5.sql (the 9 placements), e-6.sql (aggregate), e-7.sql (Excel GRs)
picking_headers: 1359 goods_received, 470 AutoCount-synced (doc_key not null), picking_date range of synced 2026-08-21 .. 2026-10-15;
889 Excel/CRM (doc_key null, qty null, only quantity_picked, bin only in source_warehouse_id, header spo_number holds the PO number, po_line_id null).

Per PO line (po_wh = purchase_order_lines.warehouse_id):
| PO / item | PO qty rcv | po_wh | AC GR docs (db1) | Excel GR docs | sum = PO? |
| PO-2026/03-0024 WESERP10B | 30000 | BRW | GR-2026/08-0141 5000 BRW; 08-0159 3000 DC1-HOLD; 09-0143 3000 DC1; 09-0164 1680 BRW = 12680, all po_line_id linked | 8 GRs 06-0123 20 WH3, 06-0139 5060 WH3, 07-0008 1100 WH3, 07-0045 2000 DC1, 07-0083 3000 DC1, 07-0090 2140 WH3, 08-0070 2000 DC1, 08-0140 2000 WH3 = 17320 | 12680+17320 = 30000 yes. Bins: BRW 6680, DC1/DC1-HOLD 10000, WH3 10320 (po_wh BRW matches only 6680) |
| PO-2026/04-0018 TPE-9201-300 | 3000 | BRW | GR-2026/09-0033 1460 BRW; 09-0166 1204 BRW = 2664 linked | GR-2026/07-0184 336 BRW | 3000 yes, all BRW = po_wh |
| PO-2026/05-0011 MAP4944A | 20 | BRW-BB | none | GR-2026/05-0054 20 BRW-BB | yes, BRW-BB = po_wh |
| PO-2026/09-0023 AP4844 | 120 | BRW | GR-2026/09-0124 120 BRW (DocKey 45869763, FromDocNo PO-2026/09-0023, FromDocDtlKey 0) | none | yes, BRW = po_wh |
| 202104-S0087 SRTWB1515 | 4 | BRW-BB | none in CRM | none | NO GR row (predates sync/Excel import, UNVERIFIED in AutoCount) |
| 202104-S0087 SRTWB246 | 3 | BRW-BB | none | none | same |
| PO-2025/12-0013 MWCX7604-S-RL-NEW (cancel PO, 11 cancelled) | 11 | BRW-BB | none | none | same; qty_received=qty_cancelled=11 suggests it is a cancel, not a receipt (UNVERIFIED) |

## Gaps / caveats
- Excel GR rows carry no po_line_id and no qty (only quantity_picked); bin = source_warehouse_id. Linking them to PO lines is by header spo_number + product only (a PO with several lines of one product is ambiguous).
- WESERP10B: GR bins differ from the PO line's warehouse_id (BRW); stock actually landed in WH3/DC1/DC1-HOLD too. PO line is one row; GR is the bin truth.
- Not done: AutoCount-side confirmation for the 3 old placements; stock_ledger probe by reference (query on the join timed out, dropped).
- Smallest pull for the 3 missing (only if wanted): the existing on-request GRN pull (autocount_pull_service entity goods_receive_notes, DocDate range covering 2021 for 202104-S0087 and Dec 2025 for MWCX7604) through the shared service snapshot; applies via AutocountDocIngestService; read-only for AutoCount. No new table or code.
