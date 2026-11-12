# OI-WHOLE-SO-CANCEL hand test

## URL
crew test copy

## Setup
1. On the test copy's database, pick an AutoCount sales order with live Order Inquiry rows and its AutoCount reference (read only):
```sql
SELECT so.so_number, ir.source_ref, oi.inquiry_no, count(*) AS live_rows
FROM projects.order_inquiry_rows oir
JOIN projects.order_inquiries oi    ON oi.id = oir.order_inquiry_id
JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
JOIN public.sales_order_lines sol   ON sol.id = psl.core_sales_order_line_id
JOIN public.sales_orders so         ON so.id = sol.sales_order_id
JOIN public.integration_references ir
     ON ir.entity_type = 'sales_orders' AND ir.entity_id = so.id::text
WHERE so.status = 'open' AND so.demand_class = 'project'
  AND sol.line_status = 'open' AND oir.state <> 'cancelled'
GROUP BY so.so_number, ir.source_ref, oi.inquiry_no
ORDER BY so.so_number DESC LIMIT 5;
```
2. Note one row's SO number (call it SO-A), its source_ref and its OI number (OI-A).
3. Send the AutoCount SO delete for it to the test copy's backend (test copy only, with the test copy's integration key):
```bash
curl -s -X POST "http://localhost:<be port>/api/v1/external/ingest/sales_orders/deletions" \
  -H "X-API-Key: <test copy key>" -H "Content-Type: application/json" \
  -d '{"source_refs": ["<source_ref of SO-A>"]}'
```
   The answer lists SO-A as `deactivated`.

## Steps
1. Sign in, click Fulfilment Planning in the sidebar.
2. Type SO-A in the search box.
3. Click the SO-A row.
4. Switch the board to the List view.
5. Open Order Inquiries from the sidebar, search OI-A, open it.
6. Go back to Fulfilment Planning, open SO-A again.
7. Click "Apply AutoCount change".
8. In the popup, click Apply.
9. Open OI-A again and open its History tab.
10. Repeat steps 1-4 at phone width (375 px).

## Expected
1. Step 2: SO-A is listed with the "Changed" badge and "Needs CS review".
2. Step 4: every SO-A line that has an Order Inquiry row reads "Cancelled" in the Verdict column; there is no "No lines to plan on these sales orders" message.
3. Step 5: each of those OI-A rows reads "Line Cancelled". (Status shows "Completed" while owner Q1 is open: the sync-time auto-done is still on.)
4. Step 7: the popup reads "Applies the AutoCount change ... old lines ... are retired. Nothing has been sent yet."
5. Step 8: the result reads "1 of 1 orders confirmed" and "SO-A: applied the AutoCount change ..." (the SO number, never a long code); SO-A is no longer on the Fulfilment Planning list.
6. Step 9: the OI-A rows are Cancelled; History shows "Cancelled <item>" once per row, by you, with today's date as dd/mm/yyyy.
7. Purchasing's handover email lists each of those lines as CANCEL (on the test copy: the queued handover, nothing delivered); nothing was sent at step 3.
8. Step 10: same as Expected 1 and 2, no sideways scrolling.
