select column_name from information_schema.columns where table_schema='public' and table_name='stock_ledger' order by ordinal_position;
select h.picking_number, h.source_record->'Details'->0 as d0 from public.picking_headers h where h.picking_number='GR-2026/09-0124';
select table_schema||'.'||table_name||'.'||column_name from information_schema.columns where column_name ilike any(array['%from_po%','%po_line%','%po_number%','%source_po%']) and table_schema in ('public','projects') order by 1;
