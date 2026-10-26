select count(*) total, count(*) filter (where source_book is not null and doc_key is not null) autocount_ingested, count(*) filter (where doc_key is null) excel_or_crm from public.picking_headers;
select h.picking_number, h.status, h.source_book, h.doc_key, h.spo_number, h.created_at::date,
 l.dtl_key, l.item_code, l.location_code, l.qty, l.from_doc_no, l.from_doc_type, l.our_po_no, l.po_line_id, l.spo_allocation_id, l.spo_number_raw, l.destination_warehouse_id
from public.picking_lines l join public.picking_headers h on h.id=l.picking_header_id
where l.item_code in ('SRTWB1515','SRTWB246','MWCX7604-S-RL-NEW','WESERP10B','TPE-9201-300','MAP4944A','AP4844')
 and (h.doc_key is not null or l.from_doc_no ~ '202104-S0087|2025/12-0013|2026/03-0024|2026/04-0018|2026/05-0011|2026/09-0023' or l.our_po_no ~ '202104-S0087|2025/12-0013|2026/03-0024|2026/04-0018|2026/05-0011|2026/09-0023')
order by 5,8,1;
