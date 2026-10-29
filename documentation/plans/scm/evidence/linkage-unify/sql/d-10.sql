\echo == shipment_status x actual_arrival x warehouse_arrival x alloc receipt (all non-retired spo allocs)
select coalesce(sh.shipment_status,'(no shipment)') shst, (sh.actual_arrival_date is not null) actual_arr, (sh.warehouse_arrival_date is not null) wh_arr,
  case when coalesce(s.quantity_received,0)=0 then 'rcv=0' when s.quantity_received<s.allocated_quantity then 'rcv partial' else 'rcv full' end rcv, s.receipt_status, count(*) n, sum(s.allocated_quantity) alloc_units
from public.spo_allocations s left join public.inbound_shipments sh on sh.id=s.inbound_shipment_id
where s.retired_at is null group by 1,2,3,4,5 order by 1,2,3,4,5;
