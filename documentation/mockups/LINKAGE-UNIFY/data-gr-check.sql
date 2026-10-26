select a.spo_number, a.spo_line_number, a.quantity_received, w.warehouse_code spo_bin, ph.picking_number, ph.doc_key is not null ac, coalesce(pl.location_code, sw.warehouse_code) gr_bin, coalesce(pl.qty, pl.quantity_picked) gr_qty
from public.spo_allocations a join public.warehouses w on w.id=a.warehouse_id
left join public.picking_lines pl on pl.spo_allocation_id=a.id
left join public.picking_headers ph on ph.id=pl.picking_header_id and ph.picking_type='goods_received'
left join public.warehouses sw on sw.id=pl.source_warehouse_id
where (a.spo_number, a.spo_line_number) in (('SPO-2026/09-0107',9),('SPO-2026/09-0107',12),('SPO-2026/08-0046',189),('SPO-2026/09-0036',129))
order by 1,2;
