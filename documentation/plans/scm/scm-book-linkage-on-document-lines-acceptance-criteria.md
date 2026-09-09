# Acceptance criteria: the book linkage on the document lines

Companion to `PLAN-scm-book-linkage-on-document-lines.md`.

## Slice A, the purchase order's Lines tab

> **REVERSED 9 September 2026, by the owner.** AC-A1 to AC-A6 below were first written
> against `scm.order_link_claim`, read through `order_link_service.so_links_by_po_line`.
> That shipped, and the owner ruled it wrong the same day. The criteria are rewritten
> against `purchase_order_lines.from_so_line_ref` and the originals are recorded in
> "What the reversal replaced" at the end of this section, so the history stays legible
> rather than being quietly deleted.
>
> **Why**, measured on `sorento_ai_automation_0907`:
>
> * On PO `202607-S0082` all 14 lines carry `from_so_line_ref` and 0 have a resolved
>   claim. The claim-based column printed a dash on every line the book had linked.
> * The claim table is many-to-many and carries NO quantity. One line of `C-FH14` with
>   `qty_ordered = 3` carried 36 claims naming 36 different sales orders; `SO324265`
>   claimed 52 different PO lines; `qty` is NULL on all 36,397 claim rows. Only 2,365 of
>   5,613 linked lines had exactly one sales order.
> * The owner's model is ONE purchase-order line linked to ONE sales order.
>   `from_so_line_ref` is a single column holding a single value, which is exactly that.
>
> **A second correction, same day.** The first cut of the replacement resolved the ref
> against `sales_order_lines.source_ref` (the full `{database}:{DocKey}:{DtlKey}`). It now
> resolves against `sales_orders.source_ref` on the DOCUMENT key (`{database}:{DocKey}`)
> instead. The number displayed is a property of the ORDER, so it needs no line row, and
> going through the line table would let a line we do not hold suppress a number we can
> legitimately name. On today's data the two joins agree on every row (both resolve the
> same 11,592 of 33,225; no row resolves under one and not the other), so this is an
> altitude correction rather than a bug fix - recorded because an earlier draft wrongly
> claimed the line-level join resolved none of them.
>
> One consequence worth stating plainly: because a line now names at most one sales
> order, the "first plus a count" overflow the old AC-A3 required no longer has anything
> to overflow. It is REMOVED from both surfaces, not merely unused. The owner's
> complaint against it was that he could not see what was hidden behind `+N more`.

* AC-A1 A purchase-order line whose `from_so_line_ref` names a sales order this CRM holds
  prints that sales order's number in a new "S/O" column. One number, never a list.
  Resolution is at DOCUMENT level: the ref's first two segments (`{database}:{DocKey}`)
  are looked up in `sales_orders.source_ref`, and the `DtlKey` is unused. A test seeds a
  sales-order HEADER with NO `sales_order_lines` row and proves it still resolves - the
  number belongs to the order, so a line we do not hold must never suppress it.
* AC-A2 A line with no `from_so_line_ref` prints a muted dash: the book names no sales
  order for it. Not an empty cell, and not a guess from the document number.
* AC-A3 A line whose `from_so_line_ref` is SET but whose DOCUMENT key names no sales order
  here prints a distinct muted marker, "Linked, not held". This is a THIRD state and must
  be visually distinguishable from AC-A2's dash. It may not be collapsed into the dash: on
  the current database 21,633 of 33,225 refs land here (`202607-S0082`'s 14 of 14 among
  them), so collapsing would blank the column and hide the fact that linkage exists at all.
  A ref that is not the documented three-part shape lands here too, rather than raising.
* AC-A4 The raw `from_so_line_ref` value (`AED_SORENTO:<DocKey>:<DtlKey>`) NEVER appears
  anywhere in the response body or on screen, and neither does the `{database}:{DocKey}`
  half the resolution is keyed on - it is the same machine key, shortened. It is a machine key, and the repo forbids
  machine identifiers in the UI - the same reason `from_po_line_ref` is never printed.
  Asserted over the whole response body, not just the one field.
* AC-A5 The whole document costs ONE resolution query however many lines it has. Assert
  the query count, not the wall time. A document whose lines carry no ref at all costs
  ZERO queries.
* AC-A6 The resolution is company-scoped: a sales order stamped to another company is
  invisible, and such a line reads as AC-A3's "linked, not held" rather than borrowing a
  stranger's number. The read goes through `order_link_service` by plain ORM query on
  `sales_orders`, never raw SQL, so the `do_orm_execute` company filter applies.
* AC-A7 The allocations panel below is UNCHANGED. Its S/O column still shows who reserved
  the line through the order inquiry flow, and a line can show one fact, the other, both
  or neither. A test seeds a line where the two name DIFFERENT sales orders and proves
  neither is overwritten by the other.
* AC-A8 The column carries an explicit `size`, and long text truncates with a `title`.
  Usable at 375 and at 1280.
* AC-A9 Both surfaces that show this fact (this Lines tab and the order-inquiry PO
  lightbox) render it IDENTICALLY, through one shared component. One fact, one
  presentation.

### What the reversal replaced

The criteria as they read before 9 September, kept verbatim so a reader can see what
changed and why the tests were rewritten rather than deleted:

* ~~AC-A1 A purchase-order line that `scm.order_link_claim` resolves to a sales order
  prints that sales order's number in a new "S/O" column.~~
* ~~AC-A2 A line with no resolved claim prints a muted dash, not an empty cell and not a
  guess.~~
* ~~AC-A3 A line resolving to MORE than one sales order prints the first plus a count, and
  the full list is on the cell's title.~~ Withdrawn entirely: a line has one sales order,
  so there is no "more than one" case and no `+N more`.
* ~~AC-A4 A claim carrying no `po_line_id` never reaches a line through a document-number
  fallback. Assert it directly: seed a document-level claim and prove no line shows it.~~
  Moot: no claim is read at all now. Its intent (never attribute one customer's stock to
  another customer's order through a document-level fallback) is preserved structurally,
  since `from_so_line_ref` is a per-LINE column with no document-level form.
* ~~AC-A5 The whole document costs ONE claim query however many lines it has.~~ Retained
  as the new AC-A5, against the resolution query instead of the claim query.
* ~~AC-A6 The claim read is company-scoped: a claim stamped to another company is
  invisible, and the read goes through `order_link_service` rather than raw SQL.~~
  Retained as the new AC-A6, against `sales_orders` / `sales_order_lines`.

## Slice B, the SPO document's Lines tab

* AC-B1 An SPO line whose ingest carried `from_po_number` prints it in a new
  "PO (book)" column.
* AC-B2 A line without one prints a muted dash.
* AC-B3 The existing `po` column is untouched: same id, same link behaviour,
  same meaning, and it still renders from `spo_allocations.po_line_id` alone.
* AC-B4 The two columns can disagree on one row without either being wrong, and
  a test seeds exactly that: `po_line_id` set to a CRM line AND
  `from_po_number` naming a different AutoCount document.
* AC-B5 `from_po_line_ref` is never printed anywhere in the UI.
* AC-B6 `so_covered` is unchanged and still opens its drill.
* AC-B7 Column carries an explicit `size`, truncates with a `title`, usable at
  375 and 1280.

## Both

* AC-C1 No new permission slug. Both fields ride the existing document reads.
* AC-C2 `response_model` does not drop any new field - asserted at the HTTP surface, not
  only at the service. Slice A's two fields are declared on BOTH `PurchaseOrderLine`
  (`app/schemas/scm_orders.py`) and `OrderInquiryPoDetailLine`
  (`app/schemas/project_order_inquiry.py`), and each surface carries its own named
  regression test, because this exact bug has already hit this feature twice.
* AC-C3 No UUID reaches either cell.
