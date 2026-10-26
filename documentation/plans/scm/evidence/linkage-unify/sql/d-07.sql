with pl as (  -- live placements on open SO lines
 select k.id link_id, k.qty, k.po_line_id, k.spo_allocation_id, k.row_id, r.state row_state, r.item_code, r.order_inquiry_id,
        l.id psl_id, l.core_sales_order_line_id core_line_id, cl.line_no core_line_no, cl.product_id, cl.qty_ordered so_qty, cl.qty_delivered
 from order_inquiry_links k
 join order_inquiry_rows r on r.id=k.row_id
 join sales_order_lines l on l.id=r.so_line_id
 join public.sales_order_lines cl on cl.id=l.core_sales_order_line_id
 where k.reserve_request_row_id is null and r.state<>'cancelled'
   and cl.line_status='open' and cl.cancelled_at is null and cl.qty_ordered>cl.qty_delivered
), po as (
 select pl.*, pol.qty_ordered po_ordered, pol.qty_received po_received, pol.line_status po_line_status, poh.status po_status, poh.po_number, poh.source_system po_src, pol.source_ref po_ref, pol.product_id po_product,
   (poh.status in ('active','received','partial','closed') and pol.line_status='open' and pol.qty_ordered>pol.qty_received and coalesce(poh.source_system,'')<>'crm_spo') po_open
 from pl left join public.purchase_order_lines pol on pol.id=pl.po_line_id left join public.purchase_orders poh on poh.id=pol.purchase_order_id
), d as ( -- derived allocs per po link
 select po.link_id, s.id sid, s.warehouse_id wid, s.allocated_quantity a, coalesce(s.quantity_received,0) rcv, s.retired_at, s.receipt_status, s.line_status sls, sh.actual_arrival_date arr,
   (s.retired_at is null and s.allocated_quantity>coalesce(s.quantity_received,0) and coalesce(s.line_status,'open')='open' and coalesce(s.receipt_status,'') not in ('fully_received','received') and sh.actual_arrival_date is null) r1_open,
   (s.retired_at is null or coalesce(s.quantity_received,0)>0) visible
 from po join public.spo_allocations s on po.po_line_id is not null and s.from_po_number=po.po_number and btrim(s.from_po_line_ref)=btrim(po.po_ref) and s.product_id=po.po_product and coalesce(btrim(po.po_ref),'')<>''
 left join public.inbound_shipments sh on sh.id=s.inbound_shipment_id
), dagg as (
 select link_id, count(*) filter (where visible) n_vis, count(*) filter (where r1_open) n_r1, sum(a) filter (where visible) a_vis, sum(rcv) filter (where visible) rcv_vis,
   count(*) filter (where visible and not r1_open) n_notopen
 from d group by link_id
), ds as ( -- direct spo
 select po.link_id, s.warehouse_id wid, s.receipt_status rs, sh.actual_arrival_date arr, s.line_status sls, s.allocated_quantity a, coalesce(s.quantity_received,0) rcv, s.retired_at,
   (s.retired_at is null and s.allocated_quantity>coalesce(s.quantity_received,0) and coalesce(s.line_status,'open')='open' and coalesce(s.receipt_status,'') not in ('fully_received','received') and sh.actual_arrival_date is null) incoming,
   (s.retired_at is null or coalesce(s.quantity_received,0)>0) visible
 from po join public.spo_allocations s on s.id=po.spo_allocation_id left join public.inbound_shipments sh on sh.id=s.inbound_shipment_id
), c as (
 select po.*, coalesce(dagg.n_vis,0) n_vis, coalesce(dagg.n_r1,0) n_r1, coalesce(dagg.n_notopen,0) n_notopen, ds.incoming ds_incoming, ds.visible ds_visible, ds.a ds_a, ds.rcv ds_rcv,
  case
   when po.spo_allocation_id is not null then case when ds.visible is not true then 'x_direct_spo_hidden_retired' when ds.incoming then 'e_direct_spo_incoming' else 'f_direct_spo_received_or_landed' end
   when po.po_line_id is not null and coalesce(dagg.n_vis,0)>0 then
       case when po.po_received>0 and po.po_received<po.po_ordered and po.po_open then 'g_partial_transfer_remainder_on_order'
            when dagg.n_r1>0 and dagg.n_notopen=0 then 'b_transferred_spo_incoming'
            when dagg.n_r1=0 then 'c_transferred_spo_landed_or_closed'
            else 'bc_transferred_mixed_spos' end
   when po.po_line_id is not null and (po.po_received>0) then 'd_po_transferred_no_spo_match'
   when po.po_line_id is not null and po.po_open then 'a_po_on_order'
   when po.po_line_id is not null then 'z_po_not_open_no_transfer'
   else 'y_other'
  end cls
 from po left join dagg on dagg.link_id=po.link_id left join ds on ds.link_id=po.link_id
)

, land as (
 -- per placement: landed qty over non-open visible allocs (derived) or the direct alloc
 select c.link_id, c.cls, c.qty, c.product_id,
   case when c.cls like 'c%' then (select sum(case when d.rcv>0 then d.rcv when d.arr is not null or d.receipt_status in ('fully_received','received') then d.a else 0 end) from d where d.link_id=c.link_id and d.visible and not d.r1_open)
        when c.cls like 'f%' then case when ds.rcv>0 then ds.rcv when ds.arr is not null or ds.rs in ('fully_received','received') then ds.a else 0 end end landed,
   case when c.cls like 'c%' then (select max(d.rcv) from d where d.link_id=c.link_id and d.visible and not d.r1_open) else ds.rcv end rcv_max,
   case when c.cls like 'c%' then (select bool_or(d.arr is not null) from d where d.link_id=c.link_id and d.visible and not d.r1_open) else ds.arr is not null end shipment_arrived,
   case when c.cls like 'c%' then (select max(d.wid::text) from d where d.link_id=c.link_id and d.visible and not d.r1_open)::uuid else ds.wid end bin
 from c left join ds on ds.link_id=c.link_id where c.cls like 'c%' or c.cls like 'f%'
)
select cls,
  case when landed=0 then 'landed0 (R3 holds nothing)' when landed>=qty then 'landed>=placement' else 'landed<placement (R3 holds less)' end landed_vs_qty,
  case when rcv_max>0 then 'rcv>0' when shipment_arrived then 'rcv=0 but arrived' else 'rcv=0 not arrived' end recv_basis,
  case when coalesce((select sum(s.quantity_on_hand) from public.stock s where s.warehouse_id=land.bin and s.product_id=land.product_id),0)>0 then 'bin has on-hand' else 'bin EMPTY' end bin_state,
  count(*) placements, sum(qty) units
from land group by 1,2,3,4 order by 1,2,3,4;
