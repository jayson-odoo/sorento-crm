select oi.inquiry_no, r.state, r.qty, l.qty link_qty, l.po_line_id is not null on_po, l.spo_allocation_id, po.po_number, pol.qty_ordered, pol.qty_received, pol.line_status,
 a.spo_number, a.spo_line_number, a.allocated_quantity, a.quantity_received, a.receipt_status, a.line_status a_ls, a.retired_at, s.shipment_status, s.actual_arrival_date, s.warehouse_arrival_date
from projects.order_inquiry_rows r join projects.order_inquiries oi on oi.id=r.order_inquiry_id
join projects.sales_order_lines psl on psl.id=r.so_line_id join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id
join projects.order_inquiry_links l on l.row_id=r.id
left join public.purchase_order_lines pol on pol.id=l.po_line_id left join public.purchase_orders po on po.id=pol.purchase_order_id
left join public.spo_allocations a on a.from_po_number=po.po_number and btrim(a.from_po_line_ref)=btrim(pol.source_ref) and a.product_id=pol.product_id
left join inbound_shipments s on s.id=a.inbound_shipment_id
where oi.inquiry_no='OI-2609-0128' and csl.line_no=880;
