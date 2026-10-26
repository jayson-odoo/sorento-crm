select oi.inquiry_no, csl.line_no so_line, so.so_number, r.item_code, k.qty, a.spo_number, a.spo_line_number, a.quantity_received, w.warehouse_code spo_bin, ph.picking_number, pl.location_code gr_bin, pl.qty gr_qty,
 (select coalesce(sum(st.quantity_on_hand),0) from public.stock st where st.product_id=a.product_id and st.warehouse_id=a.warehouse_id) spo_bin_on_hand
from projects.order_inquiry_links k
join projects.order_inquiry_rows r on r.id=k.row_id and r.state<>'cancelled'
join projects.order_inquiries oi on oi.id=r.order_inquiry_id
join projects.sales_order_lines psl on psl.id=r.so_line_id
join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id and csl.line_status='open' and csl.qty_ordered>csl.qty_delivered
join public.sales_orders so on so.id=csl.sales_order_id
join public.spo_allocations a on a.id=k.spo_allocation_id and coalesce(a.quantity_received,0)>0
join public.warehouses w on w.id=a.warehouse_id
join public.picking_lines pl on pl.spo_allocation_id=a.id
join public.picking_headers ph on ph.id=pl.picking_header_id and ph.picking_type='goods_received' and ph.doc_key is not null
where k.reserve_request_row_id is null and pl.location_code is distinct from w.warehouse_code
order by spo_bin_on_hand asc, k.qty desc limit 5;
