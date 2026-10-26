with recv as (
  select distinct a.id, a.warehouse_id, a.quantity_received from public.spo_allocations a
  where coalesce(a.quantity_received,0)>0 and (
    exists (select 1 from projects.order_inquiry_links k where k.spo_allocation_id=a.id)
    or exists (select 1 from projects.order_inquiry_links k join public.purchase_order_lines pol on pol.id=k.po_line_id join public.purchase_orders po on po.id=pol.purchase_order_id
               where a.from_po_number=po.po_number and btrim(a.from_po_line_ref)=btrim(pol.source_ref) and a.product_id=pol.product_id))
), gl as (
  select r.id, ph.doc_key is not null ac, coalesce(pl.location_code, sw.warehouse_code) gr_bin, w.warehouse_code spo_bin, pl.qty, pl.quantity_picked
  from recv r join public.picking_lines pl on pl.spo_allocation_id=r.id
  join public.picking_headers ph on ph.id=pl.picking_header_id and ph.picking_type='goods_received'
  left join public.warehouses w on w.id=r.warehouse_id left join public.warehouses sw on sw.id=pl.source_warehouse_id
)
select ac, (gr_bin is distinct from spo_bin) differs, count(distinct id) allocs, count(*) gr_lines from gl group by 1,2 order by 1,2;
-- top differing bin pairs, AutoCount GRs only
with recv as (select a.id, a.warehouse_id from public.spo_allocations a where coalesce(a.quantity_received,0)>0)
select w.warehouse_code spo_bin, pl.location_code gr_bin, count(*) n
from recv r join public.picking_lines pl on pl.spo_allocation_id=r.id
join public.picking_headers ph on ph.id=pl.picking_header_id and ph.picking_type='goods_received' and ph.doc_key is not null
left join public.warehouses w on w.id=r.warehouse_id
where pl.location_code is distinct from w.warehouse_code group by 1,2 order by 3 desc limit 8;
-- L64 links
select k.qty, case when k.po_line_id is not null then 'po '||po.po_number else 'spo '||a.spo_number||' L'||a.spo_line_number end target
from projects.order_inquiry_links k join projects.order_inquiry_rows r on r.id=k.row_id join projects.order_inquiries oi on oi.id=r.order_inquiry_id
join projects.sales_order_lines psl on psl.id=r.so_line_id join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id
left join public.purchase_order_lines pol on pol.id=k.po_line_id left join public.purchase_orders po on po.id=pol.purchase_order_id
left join public.spo_allocations a on a.id=k.spo_allocation_id
where oi.inquiry_no='OI-2609-0194' and csl.line_no=64 and k.reserve_request_row_id is null;
