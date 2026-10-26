-- P4 own-arrival key (from_po_line_ref = source_ref, product) vs strict key (+ po_number, btrim)
with loose as (
  select a.id aid, pol.id plid, (a.from_po_number = po.po_number) same_po
  from public.spo_allocations a
  join public.purchase_order_lines pol on a.from_po_line_ref = pol.source_ref and a.product_id = pol.product_id
  join public.purchase_orders po on po.id = pol.purchase_order_id
  where coalesce(a.quantity_received,0) > 0
)
select count(*) pairs, count(*) filter (where not same_po) cross_po_pairs,
       count(distinct aid) filter (where not same_po) alloc_with_foreign_po,
       count(distinct plid) filter (where not same_po) pol_with_foreign_spo
from loose;
-- retired allocations never received: line_status distribution (protects P1?)
select coalesce(line_status,'null') ls, count(*) from public.spo_allocations where retired_at is not null and coalesce(quantity_received,0)=0 group by 1;
-- source_ref multiplicity on PO lines
select count(*) refs_shared from (select source_ref from public.purchase_order_lines where coalesce(source_ref,'')<>'' group by 1 having count(*)>1) t;
