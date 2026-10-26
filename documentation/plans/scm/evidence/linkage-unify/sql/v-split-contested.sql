-- PO lines where order of placements can matter: live placements (any SO line state) exceed
-- what the line can supply (followed SPO capacity + PO open rest). If none, no view filter
-- (span, dates, group, closed lines) can change a placement's chain on this data.
with pl as (
  select k.po_line_id, sum(k.qty) placed, count(*) n
  from projects.order_inquiry_links k join projects.order_inquiry_rows r on r.id=k.row_id and r.state<>'cancelled'
  where k.po_line_id is not null group by k.po_line_id
), cap as (
  select pol.id po_line_id,
    greatest(pol.qty_ordered - pol.qty_received, 0) * (case when pol.line_status='open' then 1 else 0 end) po_rest,
    coalesce((select sum(case when coalesce(a.line_status,'open')='open' and coalesce(a.receipt_status,'') not in ('fully_received','received') and a.allocated_quantity>coalesce(a.quantity_received,0)
                              then a.allocated_quantity else coalesce(a.quantity_received,0) end)
              from public.spo_allocations a join public.purchase_orders po on po.id=pol.purchase_order_id
              where a.from_po_number=po.po_number and btrim(a.from_po_line_ref)=btrim(pol.source_ref) and a.product_id=pol.product_id
                and (a.retired_at is null or coalesce(a.quantity_received,0)>0)),0) spo_cap
  from public.purchase_order_lines pol where pol.id in (select po_line_id from pl)
)
select count(*) po_lines_with_placements, count(*) filter (where n>1) multi_placement,
  count(*) filter (where n>1 and placed > po_rest + spo_cap) contested_multi,
  count(*) filter (where placed > po_rest + spo_cap) short_any
from pl join cap using (po_line_id);
