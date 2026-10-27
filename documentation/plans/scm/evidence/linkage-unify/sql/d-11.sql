\echo == actual_arrival_date populated anywhere
select count(*) shipments, count(actual_arrival_date) with_actual, count(warehouse_arrival_date) with_wh_arr, max(actual_arrival_date) from public.inbound_shipments;
\echo == stock_ledger reference types
select reference_type, transaction_type, count(*), max(created_at) from public.stock_ledger group by 1,2 order by 3 desc limit 12;
\echo == gap rows: shipment landed (wh_arr or fully_received shipment) but alloc rcv=0, not retired
select s.spo_number, s.spo_line_number, s.allocated_quantity, s.quantity_received, s.receipt_status, s.line_status, sh.shipment_number, sh.shipment_status, sh.warehouse_arrival_date, sh.estimated_arrival_date, w.warehouse_code,
 (select count(*) from projects.order_inquiry_links k join projects.order_inquiry_rows r on r.id=k.row_id where k.spo_allocation_id=s.id and r.state<>'cancelled') direct_links,
 (select count(*) from projects.order_inquiry_links k join projects.order_inquiry_rows r on r.id=k.row_id join public.purchase_order_lines pol on pol.id=k.po_line_id join public.purchase_orders po on po.id=pol.purchase_order_id where r.state<>'cancelled' and po.po_number=s.from_po_number and btrim(pol.source_ref)=btrim(s.from_po_line_ref) and pol.product_id=s.product_id) po_links_via_transfer
from public.spo_allocations s join public.inbound_shipments sh on sh.id=s.inbound_shipment_id left join public.warehouses w on w.id=s.warehouse_id
where s.retired_at is null and coalesce(s.quantity_received,0)=0 and (sh.warehouse_arrival_date is not null or sh.shipment_status='fully_received')
order by sh.warehouse_arrival_date nulls last;
\echo == ledger postings for stock vs spo receipts: do ledger rows reference SPO?
select reference_type, count(*) from public.stock_ledger where reference_id in (select id::text from public.spo_allocations) group by 1;
