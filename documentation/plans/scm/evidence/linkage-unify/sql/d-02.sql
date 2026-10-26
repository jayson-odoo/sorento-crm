\echo == links of row
select k.id link_id, k.qty, k.po_line_id, k.spo_allocation_id, k.document, k.auto, k.reserve_request_row_id from order_inquiry_links k where k.row_id='ffcde9a6-6538-4913-a3e7-c7ba9bc8b5ce';
\echo == PO line
select po.po_number, po.status po_status, pol.source_ref, pol.line_status, pol.qty_ordered, pol.qty_received, pol.qty_cancelled, pol.expected_date, pol.product_id, pol.warehouse_id
from order_inquiry_links k join public.purchase_order_lines pol on pol.id=k.po_line_id join public.purchase_orders po on po.id=pol.purchase_order_id where k.row_id='ffcde9a6-6538-4913-a3e7-c7ba9bc8b5ce';
\echo == derived SPO allocations (OI-SPO-EXACT)
select s.id, s.spo_number, s.spo_line_number, s.from_po_number, s.from_po_line_ref, s.allocated_quantity, s.quantity_received, s.receipt_status, s.line_status, s.retired_at, s.expected_date, w.warehouse_code, s.location_code, sh.shipment_number, sh.shipment_status, sh.estimated_arrival_date, sh.actual_arrival_date, sh.warehouse_arrival_date
from order_inquiry_links k join public.purchase_order_lines pol on pol.id=k.po_line_id join public.purchase_orders po on po.id=pol.purchase_order_id
join public.spo_allocations s on s.from_po_number=po.po_number and btrim(s.from_po_line_ref)=btrim(pol.source_ref) and s.product_id=pol.product_id
left join public.warehouses w on w.id=s.warehouse_id left join public.inbound_shipments sh on sh.id=s.inbound_shipment_id
where k.row_id='ffcde9a6-6538-4913-a3e7-c7ba9bc8b5ce';
\echo == all spo_allocations of product on that PO number
select s.spo_number, s.spo_line_number, s.from_po_number, s.from_po_line_ref, s.allocated_quantity, s.quantity_received, s.receipt_status from public.spo_allocations s join order_inquiry_rows r on r.id='ffcde9a6-6538-4913-a3e7-c7ba9bc8b5ce' join sales_order_lines l on l.id=r.so_line_id where s.product_id=l.product_id and s.from_po_number='202607-S0100';
\echo == stock balance at SPO bin for product
select w.warehouse_code, sb.* from public.stock_balances sb join public.warehouses w on w.id=sb.warehouse_id join order_inquiry_rows r on r.id='ffcde9a6-6538-4913-a3e7-c7ba9bc8b5ce' join sales_order_lines l on l.id=r.so_line_id where sb.product_id=l.product_id;
