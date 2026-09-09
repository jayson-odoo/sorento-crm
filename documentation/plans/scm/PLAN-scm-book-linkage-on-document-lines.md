# PLAN: the AutoCount book's linkage, visible on the document lines

Status: IN REVIEW. PR #764 open, CI green, browser verified 9 September 2026. Slice A
REVERSED and rebuilt 9 September 2026 (owner ruling: the S/O columns read
`purchase_order_lines.from_so_line_ref`, not `scm.order_link_claim` - see section 2).
Slice B unchanged. Contract 2.2 merged as #762, e99dba2ba. Review round 9 September
2026: `book_so_by_ref` made a required kwarg on `serialize()` (a forgotten default used
to read "linked, not held" for orders the CRM holds), the PO list route no longer
resolves the linkage at all (no list consumer read it), the three-state derivation
moved into one shared `order_link_service.book_so_fields`, and `sales_orders.source_ref`
gained an index the resolver was missing.

Owner ask, 9 September 2026, against the running lane: "our ingest takes in
linked SO for each PO line, and also linked PO for each SPO right, are they by
any means visualized in the PO form view and SPO form view". They are not. He
then ruled: "i want the linkage to belongs to Lines column".

## 0. What was measured before writing this

**The PO detail shows no sales order anywhere on its Lines tab.** Columns are
Product, Qty ordered, Qty received, Outstanding qty, Placed, Unit price,
Discount, Total, UoM, Location, Delivery date, Status.

**`OrderLinkClaim` reaches no screen at all.** It appears in no route and no
schema, so it is never serialized. (Still true after the 9 Sep reversal: it briefly did,
and no longer does.) The backend uses it for exactly two things:
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

**REVERSED 9 September 2026.** This section first specified a `scm.order_link_claim`
read. It shipped that way, the owner ruled it wrong the same day, and what follows is the
replacement. The original text is kept at the end of this section under "2.9 What the
reversal replaced" - deleting it would leave the rewritten tests and criteria looking
arbitrary.

### 2.1 The evidence that forced the reversal

Measured on `sorento_ai_automation_0907`:

* PO `202607-S0082`: all **14 of 14** lines carry `purchase_order_lines.from_so_line_ref`,
  and **0 of 14** have a resolved `order_link_claim`. The shipped column printed a dash on
  every line the book had linked. That is the bug the owner saw.
* The claim table is **many-to-many and quantity-free**. One line of `C-FH14` with
  `qty_ordered = 3` carries **36 claims naming 36 different sales orders**; `SO324265`
  claims **52 different PO lines**; `qty` is NULL on all **36,397** claim rows. Only
  **2,365 of 5,613** linked lines resolve to exactly one sales order. A 3-unit line cannot
  honestly be reported as belonging to 36 orders, and with no quantity there is nothing to
  split it by.
* The owner's model is **one PO line, one sales order**. `from_so_line_ref` is a single
  column holding a single value, which is that model exactly.

Ruling: **both S/O columns read `purchase_order_lines.from_so_line_ref`**, not the claim
table.

### 2.2 How the ref becomes a number: DOCUMENT level, against `sales_orders`

`from_so_line_ref` holds AutoCount's own `"{database}:{DocKey}:{DtlKey}"` - for this book
`AED_SORENTO:<DocKey>:<DtlKey>`.

**Resolve its first TWO segments (`{database}:{DocKey}`) against `sales_orders.source_ref`,
which carries exactly that. The `DtlKey` is unused.** In SQL terms:

```sql
sales_orders.source_ref = split_part(pol.from_so_line_ref, ':', 1) || ':' ||
                          split_part(pol.from_so_line_ref, ':', 2)
```

Read through `order_link_service.book_so_numbers_by_ref(db, refs) -> {full_ref: so_number}`.
The signature is keyed by the FULL ref the caller passes in: neither service needs to know
a DocKey exists, so the split lives inside the reader.

**Why document level and not `sales_order_lines.source_ref`.** The cell displays a sales
order NUMBER, which is a property of the ORDER, not of a line. Document to number is
therefore the whole question, and it needs no `sales_order_lines` row to answer. Resolving
through the line table instead lets a line we happen not to hold suppress a number we could
legitimately name: a header ingested without its lines, or a line since removed, would read
"linked, not held" while `sales_orders` names it perfectly well.

It also removes a tie-break the line-level version needed. `sales_orders.source_ref` is
UNIQUE across the `AED_SORENTO:` namespace (75,600 rows, 0 duplicate keys), so the join
cannot fan out. `sales_order_lines.source_ref` is NOT unique - 187 values repeat, every one
a legacy bare line number such as `"1"` from an old import - so the line-level reader had
to carry a deterministic `ORDER BY` just to be total.

**Measured on `sorento_ai_automation_0907`, stated precisely.** Of the 33,225 purchase
lines carrying a ref, the document-key join resolves **11,592** and leaves **21,633**
unresolved. An earlier draft of this section claimed the line-level join resolved ZERO of
them; that is **wrong** and is corrected here so the next reader does not inherit it. The
two joins agree on every single row today: same 11,592 resolved, `line_only = 0`,
`doc_only = 0`, `disagree = 0`. So this is **not a bug fix against current data** - it is
the correct altitude for the question, adopted before the latent failure mode above can
bite. (What IS true about the 41.6 million figure: the DocKeys reachable through
`sales_order_lines` stop there, which is why the 21,633 unresolved refs, pointing at 43 to
45 million, resolve under neither join.)

The database segment is taken from the ref's own first field, never hardcoded as
`"AED_SORENTO:"`. The database name is data - it is field one of the documented format -
and every ref is `AED_SORENTO` today only because there is one book. Hardcoding would fail
silently the day a second is ingested; splitting costs nothing.

* ONE query per document, keyed by ref, never one per line. `202405-S0046` alone has 584
  lines. An all-unlinked document costs zero queries: the reader drops empty and
  unparseable refs before it goes to the database.
* `SalesOrder` is `CompanyScopedMixin`, so the plain ORM query is company-scoped by
  `do_orm_execute`. No explicit `company_id` filter, and no raw SQL, which would bypass the
  company stamp.
* A ref that is not the documented three-part shape has no document key, so it is absent
  from the result and reads as unresolved. It never raises and never leaks.

### 2.3 Three states, all three distinguishable

The wire carries two scalars per line, on BOTH response models:

| `from_so_line_ref` | resolves | `book_so_number` | `book_so_unresolved` | the cell shows |
| --- | --- | --- | --- | --- |
| NULL | n/a | `null` | `false` | a muted dash |
| set | yes | the number | `false` | the sales order number |
| set | no | `null` | `true` | a muted "Linked, not held" |

The third row is the one that has to be argued for, because the cheap design collapses it
into the dash. It must not: 21,633 of the 33,225 refs land here, and `202607-S0082`
resolves 0 of its 14 under either join (the sales orders it names, DocKeys in the 43 to 45
million range, have simply not been pushed to this CRM). Collapsing would blank the column
and hide the fact that linkage exists, which is the exact failure this slice was opened to
fix. The wording is short and non-technical, and the raw ref is NEVER printed - it is a
machine key, the same reason `from_po_line_ref` is not printed either.

`book_so_number` alone cannot carry the three states, which is why there are two fields.
The alternative, a sentinel string, would put a display decision in the database layer.

### 2.4 Backend

* `app/services/scm/order_link_service.py`: `so_links_by_po_line` DELETED, replaced by
  `book_so_numbers_by_ref`, which resolves at DOCUMENT level against `sales_orders` (2.2). Nothing else consumed the old reader, so leaving it would be a
  dead path. `PurchaseOrderLineSoLink` is deleted from `app/schemas/scm_orders.py` for the
  same reason. (`_claim_stated_so_links` in `outstanding_import_service.py` is a different
  function - the claim WRITER at import time - and is untouched.)
* `app/services/scm/purchase_order_service.py`: `_book_so_for(lines)` resolves a whole set
  in one query; `serialize(..., book_so_by_ref=...)` reads each line's own
  `ln.from_so_line_ref`. Wired on all three paths that serialize lines - `get_one`,
  `update` (or the column blanks the moment a buyer saves an unrelated edit) and `list`
  (resolved once per PAGE, not once per order, or a 50-row page is 50 round trips per
  keystroke).
* `app/services/order_inquiry_worklist_service.py`: `get_po_detail` selects
  `PurchaseOrderLine.from_so_line_ref` alongside the columns it already reads and resolves
  the document in one call.
* Both fields declared on `PurchaseOrderLine` AND `OrderInquiryPoDetailLine`, with a named
  route-level test on each surface. `response_model` silently drops an undeclared field,
  and this feature has already been bitten by that twice.

### 2.5 Frontend

One component, `app/(protected)/scm/components/BookSoCell.tsx`, used by both surfaces -
`PurchaseOrderDetail.tsx` and `OrderInquiryDocumentDialog.tsx`'s `PO_LINE_COLUMNS`. One
fact must not come to read two ways on two screens a click apart, and the previous cut had
the rendering copied into each. `SoLinksCellContent` is gone.

* Header "S/O", explicit `size`, `truncate` plus `title`, `DataGridColumnHeader` and
  `meta.headerTitle`, per the DataGrid rules.
* No `+N more` on either surface. There is nothing to overflow now, and the owner's
  complaint against it was that he could not see what it hid.
* NOT a link. Sales orders live on two different screens depending on whether the order is
  a project order or an adopted book order, and picking the wrong one is worse than plain
  text. A deliberate omission, unchanged by the reversal.

### 2.9 What the reversal replaced

The section as it read before 9 September:

> Each line gains `so_links`: the DISTINCT sales orders `scm.order_link_claim` resolves
> onto that `po_line_id`. Per entry: the sales order number as the book spells it, the
> `so_line_id` where the claim resolved one, and the claim's `source` so the screen can
> say where the pairing came from. Read through `order_link_service`, never a hand-rolled
> query, and never raw SQL. ONE query for the whole document, keyed by line id. A claim
> with no `po_line_id` is not this line's business and must not appear through a fallback
> on document number. On the frontend: one sales order prints its number, several print
> the first plus a count with the full list on the cell title.

What survived it: the one-query-per-document rule, the company-scoping rule, the
no-raw-SQL rule, the muted dash for "nothing linked", and the decision not to make the
cell a link. What did not: the claim table as the source, the per-entry `so_line_id` and
`source`, and the `+N more` overflow.

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

* No backfill. Slice A shows what `purchase_order_lines.from_so_line_ref` already
  holds; slice B shows what the reconcile waves will write. Neither creates data.
  A ref that names a sales order this CRM has not been sent is NOT a gap to backfill
  here - it is the book being ahead of us, and the column says so.
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
