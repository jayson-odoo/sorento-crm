-- LINKAGE-UNIFY U4 mock: read-only queries on sorento_cagent_stack (26 Oct 2026).
-- PGOPTIONS='-c search_path=projects,public -c default_transaction_read_only=on'. Section letters match the notes in index.html.
-- A: PO 202607-S0100 lines. B: SPO-2026/09-0107 lines (L1, L7 retired with 0 received). C: placements on either. D: Goods Received lines (bin per SPO line).
-- E: PO 202607-S0083 and 202607-S0105 lines with matching SPO lines (in transit, withdrawn, cancelled). F: ack_state of placements (acknowledged = Confirmed, changed = Proposed). I, J: placements on S0083 lines and direct on SPO-2026/10-0046.

\echo --- A. PO 202607-S0100 lines
select right(pol.source_ref,9) ref_tail, p.product_code, pol.qty_ordered, pol.qty_received, pol.line_status, po.status, pol.id
from public.purchase_orders po join public.purchase_order_lines pol on pol.purchase_order_id=po.id join public.products p on p.id=pol.product_id where po.po_number='202607-S0100' order by pol.source_ref;
\echo --- B. SPO-2026/09-0107 allocs
select a.spo_line_number ln, p.product_code, a.allocated_quantity alloc, a.quantity_received rcv, a.receipt_status, a.line_status, a.retired_at is not null retired, a.from_po_number, right(a.from_po_line_ref,9) po_ref_tail, w.warehouse_code
from public.spo_allocations a join public.products p on p.id=a.product_id left join public.warehouses w on w.id=a.warehouse_id where a.spo_number='SPO-2026/09-0107' order by a.spo_line_number;
\echo --- C. placements touching PO 202607-S0100 lines or SPO-2026/09-0107 lines
select oi.inquiry_no, cso.so_number, csl.line_no so_line, r.item_code, k.qty,
  case when k.po_line_id is not null then 'PO '||po.po_number||' ..'||right(pol.source_ref,9) else 'SPO '||a.spo_number||' L'||a.spo_line_number end target, r.state, k.created_at::date
from order_inquiry_links k join order_inquiry_rows r on r.id=k.row_id join order_inquiries oi on oi.id=r.order_inquiry_id
join sales_order_lines psl on psl.id=r.so_line_id join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id join public.sales_orders cso on cso.id=csl.sales_order_id
left join public.purchase_order_lines pol on pol.id=k.po_line_id left join public.purchase_orders po on po.id=pol.purchase_order_id
left join public.spo_allocations a on a.id=k.spo_allocation_id
where k.reserve_request_row_id is null and (po.po_number='202607-S0100' or a.spo_number='SPO-2026/09-0107') order by 1,3,6;
\echo --- D. GR lines naming SPO-2026/09-0107 or PO 202607-S0100 lines
select ph.picking_number, ph.picking_status, ph.doc_key is not null ac, ph.picking_date::date, pl.item_code, pl.qty, pl.location_code, w.warehouse_code dest, a.spo_line_number spo_ln, right(pol.source_ref,9) po_ref
from public.picking_lines pl join public.picking_headers ph on ph.id=pl.picking_header_id and ph.picking_type='goods_received'
left join public.warehouses w on w.id=pl.destination_warehouse_id
left join public.spo_allocations a on a.id=pl.spo_allocation_id left join public.purchase_order_lines pol on pol.id=pl.po_line_id left join public.purchase_orders po on po.id=pol.purchase_order_id
where a.spo_number='SPO-2026/09-0107' or po.po_number='202607-S0100' order by ph.picking_date, pl.item_code;
\echo --- E. PO 202607-S0083 and 202607-S0105 lines + matching SPO lines
select po.po_number, right(pol.source_ref,9) ref_tail, p.product_code, pol.qty_ordered, pol.qty_received, pol.qty_cancelled, pol.line_status, a.spo_number, a.spo_line_number ln, a.allocated_quantity alloc, a.quantity_received rcv, a.receipt_status, a.line_status sls, a.retired_at is not null retired, w.warehouse_code bin, sh.shipment_status, sh.actual_arrival_date arr
from public.purchase_orders po join public.purchase_order_lines pol on pol.purchase_order_id=po.id join public.products p on p.id=pol.product_id
left join public.spo_allocations a on a.from_po_number=po.po_number and btrim(a.from_po_line_ref)=btrim(pol.source_ref) and a.product_id=pol.product_id
left join public.warehouses w on w.id=a.warehouse_id left join public.inbound_shipments sh on sh.id=a.inbound_shipment_id
where po.po_number in ('202607-S0083','202607-S0105') and p.product_code in ('SRTWT7202','SRTA8046','SRTWT165') order by 1,3,2,9;
\echo --- F. ack_state of placements on PO/SPO
select oi.inquiry_no, csl.line_no, k.qty, case when k.po_line_id is not null then 'PO' else 'SPO L'||a.spo_line_number end t, r.ack_state
from order_inquiry_links k join order_inquiry_rows r on r.id=k.row_id join order_inquiries oi on oi.id=r.order_inquiry_id
join sales_order_lines psl on psl.id=r.so_line_id join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id
left join public.purchase_order_lines pol on pol.id=k.po_line_id left join public.purchase_orders po on po.id=pol.purchase_order_id left join public.spo_allocations a on a.id=k.spo_allocation_id
where k.reserve_request_row_id is null and (po.po_number='202607-S0100' or a.spo_number='SPO-2026/09-0107') order by 1,2,4;
select distinct demand_class from (select 'project' demand_class) x;
select s.spo_number, min(a.created_at)::date created, count(*) lines from public.spo_allocations a join (select 'SPO-2026/09-0107' spo_number) s on s.spo_number=a.spo_number group by 1;
\echo --- I. placements on PO 202607-S0083 selected lines
select oi.inquiry_no, cso.so_number, csl.line_no so_line, r.item_code, k.qty, right(pol.source_ref,9) po_ref, pol.qty_ordered, pol.line_status, r.ack_state
from order_inquiry_links k join order_inquiry_rows r on r.id=k.row_id join order_inquiries oi on oi.id=r.order_inquiry_id
join sales_order_lines psl on psl.id=r.so_line_id join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id join public.sales_orders cso on cso.id=csl.sales_order_id
join public.purchase_order_lines pol on pol.id=k.po_line_id join public.purchase_orders po on po.id=pol.purchase_order_id
where k.reserve_request_row_id is null and po.po_number='202607-S0083' and right(pol.source_ref,9) in (':45528998',':45348985',':45522177',':45523850') and r.state<>'cancelled' order by 6,1;
\echo --- J. direct placements on SPO-2026/10-0046 L172 L176 L170 L138 L174
select oi.inquiry_no, csl.line_no, k.qty, a.spo_line_number ln from order_inquiry_links k join order_inquiry_rows r on r.id=k.row_id join order_inquiries oi on oi.id=r.order_inquiry_id
join sales_order_lines psl on psl.id=r.so_line_id join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id join public.spo_allocations a on a.id=k.spo_allocation_id
where k.reserve_request_row_id is null and a.spo_number='SPO-2026/10-0046' and a.spo_line_number in (172,176,170,138,174) and r.state<>'cancelled';
\echo --- K. SPO 0107 L7 line
select a.spo_line_number, a.line_status, a.retired_at::date from public.spo_allocations a where a.spo_number='SPO-2026/09-0107' and spo_line_number in (1,7);
