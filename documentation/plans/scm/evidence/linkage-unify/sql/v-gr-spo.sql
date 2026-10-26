-- L880 SPO line: GR lines naming it
select ph.picking_number, ph.doc_key is not null ac_gr, ph.picking_date, pl.location_code, pl.qty, pl.from_doc_no, pl.spo_allocation_id is not null on_spo, pl.po_line_id is not null on_po
from public.spo_allocations a
join public.picking_lines pl on (pl.spo_allocation_id=a.id or (pl.from_doc_no=a.spo_number and pl.product_id=a.product_id))
join public.picking_headers ph on ph.id=pl.picking_header_id and ph.picking_type='goods_received'
where a.spo_number='SPO-2026/09-0107' and a.spo_line_number=9;
-- received SPO allocations with a placement (classes c, f): how many have a GR line linked, and bin differs?
with recv as (
  select distinct a.id, a.warehouse_id from public.spo_allocations a
  where coalesce(a.quantity_received,0)>0 and (
    exists (select 1 from projects.order_inquiry_links k where k.spo_allocation_id=a.id)
    or exists (select 1 from projects.order_inquiry_links k join public.purchase_order_lines pol on pol.id=k.po_line_id join public.purchase_orders po on po.id=pol.purchase_order_id
               where a.from_po_number=po.po_number and btrim(a.from_po_line_ref)=btrim(pol.source_ref) and a.product_id=pol.product_id))
), g as (
  select r.id, bool_or(ph.doc_key is not null) ac, bool_or(coalesce(pl.location_code, sw.warehouse_code) is distinct from w.warehouse_code) differs
  from recv r join public.picking_lines pl on pl.spo_allocation_id=r.id
  join public.picking_headers ph on ph.id=pl.picking_header_id and ph.picking_type='goods_received'
  left join public.warehouses w on w.id=r.warehouse_id left join public.warehouses sw on sw.id=pl.source_warehouse_id
  group by r.id
)
select (select count(*) from recv) recv_allocs_with_placement, count(*) with_gr_line, count(*) filter (where ac) with_ac_gr, count(*) filter (where differs) gr_bin_differs from g;
