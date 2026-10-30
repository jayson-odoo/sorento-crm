-- SPO rows naming a PO line by from_po_line_ref with NO from_po_number: lost by the strict key
select count(*) total_with_ref,
  count(*) filter (where from_po_number is null) ref_no_po_number,
  count(*) filter (where from_po_number is null and coalesce(quantity_received,0)>0) ref_no_po_number_received,
  count(*) filter (where from_po_number is null and exists (select 1 from public.purchase_order_lines pol where pol.source_ref = a.from_po_line_ref and pol.product_id = a.product_id)) ref_no_po_number_matching_a_po_line
from public.spo_allocations a where coalesce(from_po_line_ref,'') <> '';
