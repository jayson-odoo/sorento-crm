# PLAN: the AutoCount book's linkage, visible on the document lines

Status: DRAFT, both slices unblocked (contract 2.2 merged as #762, e99dba2ba).

Owner ask, 9 September 2026, against the running lane: "our ingest takes in
linked SO for each PO line, and also linked PO for each SPO right, are they by
any means visualized in the PO form view and SPO form view". They are not. He
then ruled: "i want the linkage to belongs to Lines column".

## 0. What was measured before writing this

**The PO detail shows no sales order anywhere on its Lines tab.** Columns are
Product, Qty ordered, Qty received, Outstanding qty, Placed, Unit price,
Discount, Total, UoM, Location, Delivery date, Status.

**`OrderLinkClaim` reaches no screen at all.** It appears in no route and no
schema, so it is never serialized. The backend uses it for exactly two things:
feeding the order inquiry cascade, and refusing a line delete with "Cannot
remove a line sales order X is waiting on"
(`scm/purchase_order_service.py`). On the 7 Sep prod copy: 36,397 claims,
22,934 resolved to a purchase-order line, 16,156 to a sales-order line.

**The PO detail's allocations panel is a DIFFERENT fact** and must stay
separate. `PurchaseOrderAllocations` prints inquiry no, S/O no, customer and
agent per line, and it answers "who RESERVED this line through our own order
inquiry flow". The book linkage answers "what does AutoCount record this line
as having been raised FOR". A line can carry one, the other, both or neither.
The owner's ruling puts the book linkage in the Lines columns precisely so the
two are not confused.

**The SPO document Lines tab already has a `po` column, and it is
structurally empty.** `SPODocumentDetail.tsx` column id `po` reads
`line.po.po_number` off `SPODocumentLinePO`, built in
`procurement_service.SPOAllocationService.get_document()` from
`spo_allocations.po_line_id` joined out to `purchase_orders`. That column
means "the CRM purchase-order LINE this SPO pulled from", and it is populated
by two CRM-internal placement flows only
(`allocation_suggestion_service`, `spo_conversion_service`). The codebase
records the measurement in three places: **0 of 80,468** allocations carry
`po_line_id`; migration 337 says it is NULL on all 860 rows it saw; the order
inquiry worklist says it is NULL on every migrated SPO. The Excel/AutoCount
import never sets it.

## 1. The decision that shapes both slices

`from_po_number` does NOT feed the existing `po` column, and this is the point
of the plan rather than a detail of it.

The two are different claims. `po` is an FK to a real `purchase_orders` row
this system holds, and the cell is a LINK. `from_po_number` is a text document
number out of the AutoCount book, with no `purchase_order_lines` row behind it
in the general case. Merging them would put two meanings under one header, and
the fact that `po_line_id` is empty on essentially every row makes that merge
tempting and still wrong: nobody reading the cell later could tell which of the
two questions it answered.

So each slice ADDS a column and changes no existing one.

## 2. Slice A. The purchase order's Lines tab names the sales order

Backend, `app/services/scm/purchase_order_service.py`, the line serializer at
the `"sku"` build around line 607, and `PurchaseOrderLine` in
`app/schemas/scm_orders.py`.

* Each line gains `so_links`: the DISTINCT sales orders `scm.order_link_claim`
  resolves onto that `po_line_id`. Per entry: the sales order number as the
  book spells it, the `so_line_id` where the claim resolved one, and the
  claim's `source` so the screen can say where the pairing came from.
* Read through `order_link_service`, never a hand-rolled query, and never raw
  SQL - `OrderLinkClaim` is company-scoped and the standing gotcha is that raw
  SQL bypasses the company stamp.
* ONE query for the whole document, keyed by line id. A per-line query would
  be 89 round trips on `202405-S0045`.
* A claim with no `po_line_id` is not this line's business and must not appear
  through a fallback on document number: that is how one customer's stock gets
  attributed to another customer's order.

Frontend, `PurchaseOrderDetail.tsx`, a new column after Location:

* Header "S/O". One sales order prints its number. Several print the first
  plus a count, with the full list on the cell title.
* `size` explicit, `truncate` plus `title` on the text, per the DataGrid rules.
* Blank reads as a muted dash. Most lines will be blank and that is honest: the
  book only links what a buyer raised through Transfer from S/O.
* NOT a link for now. Sales orders live on two different screens depending on
  whether the order is a project order or an adopted book order, and picking
  the wrong one is worse than plain text. Named as a deliberate omission.

## 3. Slice B. The SPO document's Lines tab names the source purchase order

Backend, `app/services/procurement_service.py`, `get_document()`, alongside the
existing `po=` assignment.

* `SPODocumentLine` gains `from_po_number`, read straight off
  `spo_allocations.from_po_number` (the column contract 2.2 added). Text, never
  resolved, because the number belongs to the AutoCount book.
* `from_po_line_ref` stays server-side. It is a key for the resolver, not a
  thing to print.
* Leave `po` and `so_covered` exactly as they are.

Frontend, `SPODocumentDetail.tsx`, a new column immediately after `po`:

* Header "PO (book)", so the pair reads as two answers to two questions rather
  than a duplicate. Plain text, muted dash when absent.
* The existing `po` column keeps its link behaviour and its meaning.

## 4. What this plan does NOT do

* No backfill. Slice A shows what `order_link_claim` already holds; slice B
  shows what the reconcile waves will write. Neither creates data.
* No change to the allocations panel.
* No change to the order inquiry screens.
* No new permission. Both fields ride the document reads that already exist.

## 5. Risk

`spo_allocations` rows are upserted by `(product_id, warehouse_id)` group in
`app/tasks/import_tasks.py`, so a per-line value can be lost to aggregation
unless it rides the group identity the way `container_number` does. That path
is the Excel importer and does not carry `from_po_number` today, so nothing is
lost now - but a later widening of the Excel path must not assume otherwise.
Stated here so the next person meets it in the plan rather than in the data.
