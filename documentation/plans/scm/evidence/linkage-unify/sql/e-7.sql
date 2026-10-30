select p.product_code item, h.picking_number, h.source_system, h.doc_key, h.picking_date, h.spo_number, l.po_line_id, l.quantity_picked, l.qty, l.location_code, sw.warehouse_code src_wh, dw.warehouse_code dst_wh, l.spo_number_raw
from public.picking_lines l join public.picking_headers h on h.id=l.picking_header_id join public.products p on p.id=l.product_id
left join public.warehouses sw on sw.id=l.source_warehouse_id left join public.warehouses dw on dw.id=l.destination_warehouse_id
where h.picking_type='goods_received' and h.doc_key is null and p.product_code in ('WESERP10B','TPE-9201-300','MAP4944A','AP4844','SRTWB1515','SRTWB246','MWCX7604-S-RL-NEW')
 and (h.spo_number in ('PO-2026/03-0024','PO-2026/04-0018','PO-2026/05-0011','PO-2026/09-0023','202104-S0087','PO-2025/12-0013') or l.spo_number_raw in ('PO-2026/03-0024','PO-2026/04-0018','PO-2026/05-0011','PO-2026/09-0023','202104-S0087','PO-2025/12-0013'))
order by 1,5;
