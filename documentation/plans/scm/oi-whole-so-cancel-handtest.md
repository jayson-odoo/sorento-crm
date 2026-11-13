# OI-WHOLE-SO-CANCEL hand test (v2: Waiting for CS, owner round 12 Nov evening)

No Excel step: neither OI export changes (owner 12 Nov 14:57 and 15:10, an exception to the export = screen rule).

## URL
crew test copy

## Setup
1. Crew fixture sales orders only, never real orders, ingested through the test copy's own ingest, adopted,
   board-confirmed as Buy:
   - SO-A (OI-A): three lines on items with NO free stock at their location; purchasing acknowledged.
   - SO-B (OI-B): three lines; purchasing acknowledged.
   - SO-C (OI-C): three lines, not confirmed by purchasing.
2. SO-A: re-push line 1 through the test copy's ingest with its delivery date 30 days later (D-old -> D-new).
3. SO-B: send the AutoCount SO delete to the test copy's backend only:
```bash
curl -s -X POST "http://localhost:<be port>/api/v1/external/ingest/sales_orders/deletions" \
  -H "X-API-Key: <test copy key>" -H "Content-Type: application/json" \
  -d '{"source_refs": ["<source_ref of SO-B>"]}'
```

4. OI-C's reserve request, seeded with no send: this SQL writes the two crew-owned rows directly (no
   reserve service call, so no email, WhatsApp or notification is queued). Run it on the test copy's DB with
   `psql -v oi=<OI-C number> -f seed.sql`:
```sql
-- Seed ONE open reserve request on one live row of a crew fixture OI (no service call: nothing is queued).
-- Set :oi to the fixture OI number (e.g. OI-C) before running.
BEGIN;
WITH target AS (
    SELECT oir.id AS row_id, oir.order_inquiry_id, oir.company_id, oir.qty
    FROM projects.order_inquiry_rows oir
    JOIN projects.order_inquiries oi ON oi.id = oir.order_inquiry_id
    WHERE oi.inquiry_no = :'oi' AND oir.state <> 'cancelled'
    ORDER BY oir.item_code, oir.id
    LIMIT 1
), req AS (
    INSERT INTO projects.order_inquiry_reserve_requests
        (id, order_inquiry_id, company_id, ordinal, state, note, requested_at)
    SELECT gen_random_uuid(), t.order_inquiry_id, t.company_id,
           COALESCE((SELECT max(ordinal) FROM projects.order_inquiry_reserve_requests r
                     WHERE r.order_inquiry_id = t.order_inquiry_id), 0) + 1,
           'requested', 'crew hand-test seed OI-WHOLE-SO-CANCEL', now()
    FROM target t
    RETURNING id, order_inquiry_id, company_id
)
INSERT INTO projects.order_inquiry_reserve_request_rows (id, request_id, row_id, company_id, qty_requested)
SELECT gen_random_uuid(), req.id, t.row_id, req.company_id, LEAST(t.qty, 1)
FROM req JOIN target t ON t.order_inquiry_id = req.order_inquiry_id;
COMMIT;
```
   Revert after the pass (removes only the rows the seed wrote, matched by its note):
```sql
BEGIN;
DELETE FROM projects.order_inquiry_reserve_request_rows
WHERE request_id IN (SELECT id FROM projects.order_inquiry_reserve_requests
                     WHERE note = 'crew hand-test seed OI-WHOLE-SO-CANCEL');
DELETE FROM projects.order_inquiry_reserve_requests WHERE note = 'crew hand-test seed OI-WHOLE-SO-CANCEL';
COMMIT;
```

## Steps
1. Sign in, click Order Inquiries in the sidebar (Documents view, Outstanding), search the three OIs.
2. Open OI-A, Lines tab. Open the State filter and read its options; then pick each of "Waiting for CS",
   "To order", "Done" in turn. Then open OI-B, Lines tab, and pick "Line cancelled", then "Waiting for CS".
3. Open OI-C, Lines tab, State filter: pick "Request to reserve".
4. Back on Order Inquiries, switch to the Lines view. Open the Done filter (the purchasing confirm filter, labelled "Done") and read its options; pick
   "Waiting for CS", then "To order", then "Done".
5. Look at the filter panel of that Lines view for a "State" filter.
6. At phone width (375 px), repeat steps 1 and 2.
7. Click Fulfilment Planning in the sidebar, tick SO-A's row and click "Plan <SO-A number>" (or open SO-A's order page and click its "Plan" link). Keep Buy for the moved line ("Change
   decision" > "Buy the whole 2" > Save decision; do NOT click "Save all suggested"), then the board's Confirm.
8. Open SO-B from Sales Orders (sidebar) and click its "Plan" button on the order page. On the board (list
   view), read SO-B's three lines, then:
   a. Tick the header checkbox (select all), read the strip, then click Clear.
   b. Click the tick (Save as suggested) on line 1 only.
   c. Tick line 2's checkbox only, open Decide and read its items, pick "Cancel", save in the popup.
   d. Click "Save all suggested".
   e. Click "Confirm (3)" and confirm in the popup.
9. Open OI-B, Lines tab.
10. System > Messaging > Outgoing Mails, search the fixture SO numbers.

## Expected
1. Step 1: OI-A, OI-B and OI-C all read "Outstanding" (header level, owner 12 Nov 22:55) and sit under the
   Outstanding tab; the header Status filter offers only the header words (Outstanding / Completed).
2. Step 2: the State filter's options are exactly the words the State column prints, written the same way
   (To order, Waiting for CS, Done, Rejected, SO cancelled, Line cancelled, Nothing to buy, Request to
   reserve, Reserved, Not reserved). On OI-A, line 1 reads "Waiting for CS · date D-old -> D-new" (small
   "f"). On OI-B (SO deleted) every line shows the existing grey "Line cancelled" pill with a "waiting for CS"
   marker next to it. Each option shows only the lines whose State reads that word (a waiting cancelled line
   matches both "Line cancelled" and "Waiting for CS"); the choice survives a reload.
3. Step 3: only the line with the reserve request shows.
4. Step 4: the Done filter's options are the Status column's words (To order, Done, Rejected, Waiting
   for CS, SO cancelled, Line cancelled, All); each shows only rows whose Status reads that word; each
   option's count equals the rows shown.
5. Step 5: there is no "State" filter on the Lines view (it has no State column).
6. Step 6: same as Expected 1 and 2, no sideways scrolling.
7. Step 7: the result reads "SO-A: confirmed as revision 2 (1 purchase row handed over)"; OI-A goes back to
   Outstanding, line 1 "To order".
8. Step 8: the SO-B order page shows a "Plan" button (owner F1) and it opens the board. Each SO-B line reads
   "Change proposed" with Suggested "Cancel line" and Decided "Not decided" (nothing decided yet), and the
   button reads "Confirm (0)".
   a. Every line has a checkbox and select all ticks all three ("3 selected").
   b. Line 1's Decided reads "Cancel line", lines 2 and 3 still "Not decided"; "Confirm (1)".
   c. The Decide menu shows "Cancel" (not "Transfer to Cancel SO"); after saving, line 2's Decided reads
      "Cancel line"; "Confirm (2)".
   d. Line 3's Decided reads "Cancel line"; "Confirm (3)".
   e. Nowhere on the board, the popup or the result is "Apply AutoCount
   change" (owner F2: one Decide -> Confirm path). The result reads "SO-B: confirmed as revision 1 (3
   purchase rows handed over)", with no "Posted ..., server confirmed ..." warning under it; SO-B leaves the planning list.
9. Step 9: the Lines tab reads "Every line on this order inquiry is cancelled." (not "Nothing was raised on
   this order inquiry."); History shows "Cancelled <item>" once per row.
10. Step 10: SO-A's handover lists the moved line with remark DELAY; SO-B's lists every line CANCEL ALL;
    queued only, nothing delivered from the test copy.
