select i.inquiry_no, r.id row_id, r.state row_state, r.item_code, r.qty, l.line_no psl_line_no, cl.line_no core_line_no, cso.so_number, cl.qty_ordered, cl.qty_delivered, cl.line_status, cl.id core_line_id
from order_inquiries i join order_inquiry_rows r on r.order_inquiry_id=i.id
left join sales_order_lines l on l.id=r.so_line_id
left join public.sales_order_lines cl on cl.id=l.core_sales_order_line_id
left join public.sales_orders cso on cso.id=cl.sales_order_id
where i.inquiry_no='OI-2609-0128' order by l.line_no;
