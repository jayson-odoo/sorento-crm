with pl as (select pol.id pol_id, po.po_number, p.product_code item, p.id product_id, pol.qty_received, pol.warehouse_id, w.warehouse_code wh
 from public.purchase_order_lines pol join public.purchase_orders po on po.id=pol.purchase_order_id join public.products p on p.id=pol.product_id left join public.warehouses w on w.id=pol.warehouse_id
 where pol.id in ('4e7541a1-5491-4034-89e5-daa404514c1f','71249a9c-fc7c-40a0-b692-8a9e4d9a1a38','c7b91f57-8968-49ff-abf5-cee4bd0f3205','d3f32cef-328f-4295-a6d9-018076cee32c','5caea141-e559-4896-acee-8ab89cf5f9ce','13989c43-a3f2-4a54-a5aa-54e7f18ac32f','5f1221a8-eb50-424d-bd02-f7e6e8617c62'))
select pl.po_number, pl.item, pl.qty_received po_rcv, pl.wh po_wh,
  case when h.doc_key is not null then 'AC-synced' else 'excel/crm' end src,
  count(distinct h.id) n_gr, sum(l.qty) gr_qty, string_agg(distinct l.location_code, ',') gr_locs,
  sum(l.qty) filter (where l.po_line_id=pl.pol_id) qty_line_linked,
  sum(l.qty) filter (where l.po_line_id is null) qty_unlinked_line
from pl join public.picking_lines l on l.product_id=pl.product_id
join public.picking_headers h on h.id=l.picking_header_id and h.picking_type='goods_received' and h.picking_status<>'cancelled'
 and (l.po_line_id=pl.pol_id or h.spo_number=pl.po_number or l.from_doc_no=pl.po_number or l.our_po_no=pl.po_number or l.spo_number_raw=pl.po_number)
group by 1,2,3,4,5 order by 1,2,5;
