-- LINKAGE-UNIFY mock: read-only verification queries (dev DB sorento_cagent_stack, search_path projects,public).
-- Q-A: lines of OI-2609-0128 with links and the chain each link sits on.
select csl.line_no, r.item_code, r.qty row_qty, r.state, r.stock_location, r.delivery_date,
       l.qty link_qty, po.po_number, pol.qty_ordered po_ord, pol.qty_received po_rcv, pol.line_status pol_status,
       a.spo_number, a.spo_line_number, a.allocated_quantity, a.quantity_received, a.receipt_status, a.line_status spo_ls, a.retired_at,
       s.shipment_status, s.actual_arrival_date
from projects.order_inquiry_rows r
join projects.order_inquiries oi on oi.id=r.order_inquiry_id
join projects.sales_order_lines psl on psl.id=r.so_line_id
join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id
left join projects.order_inquiry_links l on l.row_id=r.id
left join public.purchase_order_lines pol on pol.id=l.po_line_id
left join public.purchase_orders po on po.id=pol.purchase_order_id
left join public.spo_allocations a on (l.spo_allocation_id=a.id)
   or (l.po_line_id is not null and a.from_po_number=po.po_number and btrim(a.from_po_line_ref)=btrim(pol.source_ref) and a.product_id=pol.product_id)
left join public.inbound_shipments s on s.id=a.inbound_shipment_id
where oi.inquiry_no='OI-2609-0128' and csl.line_no in (832,880,944,1024,1040)
order by csl.line_no;

-- Q-B: worklist sample rows: row qty, PO-linked and SPO-linked sums (the service's _PO_LINKED_QTY / _SPO_LINKED_QTY),
-- plus each link's chain. OI-2609-0194 line 64, OI-2609-0252 line 784, OI-2609-0194 line 16 (class z), OI-2609-0128 line 880.
select oi.inquiry_no, so.so_number, csl.line_no, r.item_code, r.qty row_qty, r.state, r.stock_location,
  (select coalesce(sum(qty),0) from projects.order_inquiry_links k where k.row_id=r.id and k.po_line_id is not null) po_linked,
  (select coalesce(sum(qty),0) from projects.order_inquiry_links k where k.row_id=r.id and k.spo_allocation_id is not null) spo_linked
from projects.order_inquiry_rows r
join projects.order_inquiries oi on oi.id=r.order_inquiry_id
join projects.sales_order_lines psl on psl.id=r.so_line_id
join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id
join public.sales_orders so on so.id=csl.sales_order_id
where (oi.inquiry_no,csl.line_no) in (('OI-2609-0128',880),('OI-2609-0194',64),('OI-2609-0252',784),('OI-2609-0194',16))
order by 1,3,5;

-- Q-C: chain status of the SPO lines named above (bin = spo_allocations.warehouse_id, shipment still in_transit).
select a.spo_number,a.spo_line_number,a.allocated_quantity,a.quantity_received,a.receipt_status,a.retired_at is not null retired,a.line_status,w.warehouse_code,s.shipment_status
from public.spo_allocations a left join public.warehouses w on w.id=a.warehouse_id left join public.inbound_shipments s on s.id=a.inbound_shipment_id
where (a.spo_number,a.spo_line_number) in (('SPO-2026/09-0107',9),('SPO-2026/09-0107',12),('SPO-2026/09-0107',7),('SPO-2026/10-0046',172),('SPO-2026/08-0046',189),('SPO-2026/09-0036',129),('SPO-2026/10-0008',76))
order by 1,2;

-- Q-D: the OI-2609-0194 line 64 links (701 + 3 + 194 on PO 202607-S0105, 194 direct on SPO-2026/10-0008 L76).
select left(l.id::text,4) link, l.qty, l.po_line_id is not null on_po, l.spo_allocation_id is not null on_spo, l.document
from projects.order_inquiry_links l join projects.order_inquiry_rows r on r.id=l.row_id join projects.order_inquiries oi on oi.id=r.order_inquiry_id
join projects.sales_order_lines psl on psl.id=r.so_line_id join public.sales_order_lines csl on csl.id=psl.core_sales_order_line_id
where oi.inquiry_no='OI-2609-0194' and csl.line_no=64 order by l.created_at;

-- Q-E: class-z row (PO line cancelled, nothing received, live placement on an open SO line):
-- OI-2609-0194 line 16, SO396348, SRTWT165 728 on PO 202607-S0083 (po_line cancelled, qty_received 0). Full list of the 20:
-- run documentation/plans/scm/evidence/linkage-unify/sql/d-03.sql with its final select replaced by: select ... from c where cls='z_po_not_open_no_transfer'.
