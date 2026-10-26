with pl as (select po.po_number, pol.id pol_id, p.product_code item, pol.qty_ordered, pol.qty_received, pol.qty_cancelled, pol.warehouse_id, w.warehouse_code wh, pol.source_ref
from public.purchase_order_lines pol join public.purchase_orders po on po.id=pol.purchase_order_id
join public.products p on p.id=pol.product_id left join public.warehouses w on w.id=pol.warehouse_id
where (po.po_number, p.product_code) in (('202104-S0087','SRTWB1515'),('202104-S0087','SRTWB246'),('PO-2025/12-0013','MWCX7604-S-RL-NEW'),('PO-2026/03-0024','WESERP10B'),('PO-2026/04-0018','TPE-9201-300'),('PO-2026/05-0011','MAP4944A'),('PO-2026/09-0023','AP4844')))
select pl.po_number, pl.item, h.picking_number, h.picking_type, h.picking_status, h.doc_key, h.source_book, h.picking_date, l.dtl_key, l.location_code, l.qty, l.from_doc_no, l.our_po_no, (l.po_line_id=pl.pol_id) linked
from pl join public.picking_lines l on (l.po_line_id=pl.pol_id or (l.item_code=pl.item and (l.from_doc_no=pl.po_number or l.our_po_no=pl.po_number)))
join public.picking_headers h on h.id=l.picking_header_id order by 1,2;
