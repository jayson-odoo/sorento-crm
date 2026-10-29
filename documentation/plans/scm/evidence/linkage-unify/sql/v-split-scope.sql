-- PO lines with followed placements: open-SO placements vs closed-SO placements, vs followed capacity
with pl as (
  select k.id, k.qty, k.po_line_id, k.linked_at,
    (cl.line_status='open' and cl.cancelled_at is null and cl.qty_ordered>cl.qty_delivered) so_open
  from projects.order_inquiry_links k join projects.order_inquiry_rows r on r.id=k.row_id and r.state<>'cancelled'
  join projects.sales_order_lines l on l.id=r.so_line_id join public.sales_order_lines cl on cl.id=l.core_sales_order_line_id
  where k.po_line_id is not null
), cap as (
  select pol.id po_line_id, sum(a.allocated_quantity) cap
  from public.purchase_order_lines pol join public.purchase_orders po on po.id=pol.purchase_order_id
  join public.spo_allocations a on a.from_po_number=po.po_number and btrim(a.from_po_line_ref)=btrim(pol.source_ref) and a.product_id=pol.product_id
   and (a.retired_at is null or coalesce(a.quantity_received,0)>0)
  group by pol.id
), agg as (
  select p.po_line_id, sum(p.qty) filter (where p.so_open) open_q, sum(p.qty) filter (where not p.so_open) closed_q,
    bool_or(not p.so_open) has_closed, c.cap
  from pl p join cap c on c.po_line_id=p.po_line_id group by p.po_line_id, c.cap
)
select count(*) po_lines_followed, count(*) filter (where has_closed) with_closed_so_placements,
  count(*) filter (where has_closed and coalesce(open_q,0)+closed_q > cap and coalesce(open_q,0)>0) where_split_differs_possible
from agg;
