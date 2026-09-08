# Acceptance criteria: the book linkage on the document lines

Companion to `PLAN-scm-book-linkage-on-document-lines.md`.

## Slice A, the purchase order's Lines tab

* AC-A1 A purchase-order line that `scm.order_link_claim` resolves to a sales
  order prints that sales order's number in a new "S/O" column.
* AC-A2 A line with no resolved claim prints a muted dash, not an empty cell
  and not a guess.
* AC-A3 A line resolving to MORE than one sales order prints the first plus a
  count, and the full list is on the cell's title.
* AC-A4 A claim carrying no `po_line_id` never reaches a line through a
  document-number fallback. Assert it directly: seed a document-level claim and
  prove no line shows it.
* AC-A5 The whole document costs ONE claim query however many lines it has.
  Assert the query count, not the wall time.
* AC-A6 The claim read is company-scoped: a claim stamped to another company is
  invisible, and the read goes through `order_link_service` rather than raw SQL.
* AC-A7 The allocations panel below is UNCHANGED. Its S/O column still shows
  who reserved the line through the order inquiry flow, and a line can show one
  fact, the other, both or neither.
* AC-A8 The column carries an explicit `size`, and long text truncates with a
  `title`. Usable at 375 and at 1280.

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
* AC-C2 `response_model` does not drop either new field - asserted at the HTTP
  surface, not only at the service.
* AC-C3 No UUID reaches either cell.
