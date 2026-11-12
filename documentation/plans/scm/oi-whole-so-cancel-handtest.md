# OI-WHOLE-SO-CANCEL hand test (v2: Waiting for CS)

## URL
crew test copy

## Setup
1. On the test copy's database, pick two AutoCount sales orders with live Order Inquiry rows that purchasing
   has already confirmed (read only):
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
  AND sol.line_status = 'open' AND oir.state <> 'cancelled' AND oir.ack_state = 'acknowledged'
GROUP BY so.so_number, ir.source_ref, oi.inquiry_no
ORDER BY so.so_number DESC LIMIT 5;
```
2. Note two of them: SO-A / OI-A and SO-B / OI-B, with SO-B's source_ref.
3. SO-A: change one line's delivery date AutoCount-side (re-push SO-A through the test copy's ingest with that
   line's date 30 days later; crew's AutoCount fixture for the test copy). Note the old date (D-old) and the
   new one (D-new).
4. SO-B: send the AutoCount SO delete to the test copy's backend only:
```bash
curl -s -X POST "http://localhost:<be port>/api/v1/external/ingest/sales_orders/deletions" \
  -H "X-API-Key: <test copy key>" -H "Content-Type: application/json" \
  -d '{"source_refs": ["<source_ref of SO-B>"]}'
```

## Steps
1. Sign in, click Order Inquiries in the sidebar (Documents view, Outstanding).
2. Search OI-A, then OI-B.
3. Switch to the Lines view; search SO-A, then SO-B.
4. Click the Status column header twice (sort up, then down).
5. Tick SO-A's line and one ordinary line of another order, click Confirm, then confirm in the popup.
6. Tick only SO-A's line and look at Confirm.
7. Export the Lines view to Excel and open it.
8. Click Fulfilment Planning in the sidebar, search SO-A, open it, confirm it with the board's Confirm.
9. Search SO-B, open it, click "Apply AutoCount change", then Apply in the popup.
10. Back on Order Inquiries, open OI-A and OI-B and their History tabs.
11. Repeat steps 1-3 at phone width (375 px).

## Expected
1. Step 2: OI-A and OI-B both read "Waiting for CS" (not Completed), under Outstanding.
2. Step 3: SO-A's line shows D-new with the date "What changed" icon (Was D-old), Status "Waiting for CS";
   SO-B's lines read Status "Waiting for CS". Nothing was emailed.
3. Step 4: the rows sort by the Status words, both directions.
4. Step 5: only the ordinary line is confirmed; a notice reads "1 row is waiting for CS and was skipped".
5. Step 6: Confirm reads "Confirm (0)" and is disabled.
6. Step 7: the sheet has STATUS, WAS QTY, WAS DATE; SO-A's row reads STATUS "Waiting for CS", DELIVERY DATE
   D-new and WAS DATE D-old, both dd/mm/yyyy.
7. Step 8: the result names SO-A (no long code); OI-A goes back to Outstanding with the line "To order" for
   purchasing (changed); purchasing's handover lists the line as DELAY.
8. Step 9: the result reads "SO-B: applied the AutoCount change ..."; SO-B leaves the planning list; purchasing's
   handover lists SO-B's lines as CANCEL ALL.
9. Step 10: OI-A History shows "Reconfirmed"; OI-B's rows are Cancelled with "Cancelled <item>" once per row,
   dated dd/mm/yyyy.
10. Step 11: same as Expected 1 and 2, no sideways scrolling.
11. On the test copy the handover emails are queued only, nothing is delivered.
