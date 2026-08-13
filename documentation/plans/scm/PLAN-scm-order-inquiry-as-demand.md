# PLAN - the Order Inquiry sheet as a source of sales orders

**Status:** written 5 Aug 2026. Slices N1 to N5 have SHIPPED on `main`: the reader
(`app/services/scm/order_inquiry_reader.py`), the importer
(`app/services/scm/order_inquiry_service.py`), the `/api/v1/scm/order-inquiry/preview|apply`
routes, the SCM sales-order list, and their tests (`tests/scm/test_order_inquiry_*.py`,
`tests/scm/test_order_link_both_ways.py`) all exist. Ownership was then revised with the client
on 2026-08-13 and recorded in
[ADR 0010](../../adr/0010-order-inquiry-loop-owned-by-project-sales.md); read
"Ownership revision" below before the ownership rule it amends. UAC:
`scm-order-inquiry-as-demand-acceptance-criteria.md`.

## What changes, and why it is not a small change

Today the sheet is an ANNOTATION: it writes a stock location onto a sales-order line that
already exists, and claims a purchase-order link. 15,787 of its 15,797 rows name orders we do
not hold, so they are counted, named, and dropped.

The decision (user, 5 Aug 2026) is that the sheet is a DEMAND FEED: those rows become sales
orders. The reason is organisational rather than technical, and it is the part worth
remembering - the outstanding SO book belongs to CS, and waiting on CS to export it is what
stops the buyer planning on today's demand. Joey already keeps this sheet.

That promotes a second writer onto `sales_orders`, which is exactly the shape that has gone
wrong here before: `apply` once branched on doc type to pick a reader and then unconditionally
wrote SalesOrder rows, so the purchase-order book created sales orders whose `so_number` was a
PO number. Two writers on one table need an explicit ownership rule, not good intentions.

## Ownership revision (client, 2026-08-13; ADR 0010)

The plan above was written when the sheet looked like a general demand feed sitting in SCM.
It is not. Three things the client settled on 2026-08-13, recorded in ADR 0010:

- **Joey's sheet carries ONLY project demand.** It is derived from published project sales
  orders, not from the whole order book.
- **The loop is owned end to end by the Project Sales module** - derive, export, human edit,
  import. The Excel round trip is deliberate: Joey's edit between export and import IS the buy
  signal, and it is the reason the loop is not collapsed into a publish-writes-through.
- **The importer relocates from `scm` to `projects` ownership.** The route path
  `/api/v1/scm/order-inquiry/*` and the permission `scm.reorder.run` stay STABLE through the
  move so the FE upload dialog keeps working; moving them into the projects namespace is a
  recorded follow-up, not part of the move.
- **Publishing a project sales order never writes core `sales_orders`.** Only the import does.
  So there is no project-publish row in the ownership table below.
- **SCM remains a reader only.** `scm.committed_v` and `demand.py` read core `sales_orders`
  and never a module table. That is the role SCM already had, unchanged.

## The ownership rule

**Whoever created the order owns its figures.**

| the order | the sheet does |
| --------- | -------------- |
| does not exist | creates it, `demand_origin = 'scm_order_inquiry'`, `so_number` = the project's `provisional_ref` |
| exists, created by the sheet | refreshes its lines, keyed by (order, item) |
| exists from any other source | annotates only: stock location + PO claim, exactly as today |

And the reverse: when CS's outstanding book later names an order the sheet created, it ADOPTS
it - matching on `so_number` as it already does - and from then on CS's quantities and dates
win, because the outstanding extract is a statement of the whole open book and the sheet is
one person's working record.

Stated as a rule rather than left to whichever upload runs last, because "last writer wins"
across two feeds with different refresh rhythms is how a quantity silently reverts.

### The two numbers, and who reconciles them

The sheet is exported BEFORE AutoCount has issued the SO number, so a sheet-created row
carries the project's `provisional_ref` as its `so_number`. The outstanding-book importer
matches on `so_number` only and inserts on a miss, so the same demand would otherwise land
twice under two different numbers.

Duplicate prevention is module-side, at the one place where both references are known at
once: `project_so_ingest_service`, at the moment it learns `autocount_doc_no`.

| when the real number arrives | `project_so_ingest_service` does |
| ---------------------------- | -------------------------------- |
| no core row holds it yet | RENUMBERS the sheet-created row in place - matched on `so_number = provisional_ref` AND `demand_origin = 'scm_order_inquiry'` - to the real number. No second row is created. |
| the outstanding book created the real-numbered row first | LINKS `so_id` to that row and RETIRES the provisional sheet-created row, so committed demand is never counted twice. |
| the row is not stamped `demand_origin = 'scm_order_inquiry'` | nothing at all. Foreign rows are never renamed, retired or otherwise touched. |

`outstanding_import_service` is unchanged: it keeps matching on `so_number` and knows nothing
about provisional refs. Putting the reconciliation on the ingest side means the core importer
carries no module knowledge.

`sales_orders.source_doc_no` is NOT used as the key here - `so_history_service` already stamps
that column on the same rows with its own doc-number semantics, so claiming it would collide.

The `demand_origin` literal stays `'scm_order_inquiry'` even though ownership moves to
projects. The string is baked into raw SQL (`scm/demand.py`), into migration 346's backfill,
and into the `OrderLinkClaim` CHECK constraint; renaming it is a data migration that buys no
correctness. ADR 0010 records why, so the mismatch between the string and the owning module
reads as a decision rather than a leftover.

## What a row can and cannot become

`sales_order_lines.product_id` is NOT NULL. A row whose item code we do not hold therefore
CANNOT be demand, and the honest options are to skip it or to invent a product. It is skipped
and named: a fabricated catalogue entry would be wrong in the one place the whole plan reads.

`sales_orders.customer_id` IS nullable, so a sheet with no customer column still produces
orders. Where a project or customer IS named, it is linked when a customer of that exact name
already exists and otherwise kept as text in `internal_note`.

Not created. `customers` requires a `customer_code` and enforces uniqueness on
`(lower(code), lower(name))`, so creating one from a project label means inventing a debtor
code in a table Sales owns - and a guessed code either collides with a real account or
silently duplicates it. The name is preserved and visible either way, and linking it later is
a one-field edit; unpicking an invented debtor is not.

## Slices

- **N1. Validate, as the standard.** `?validate_only=true` on both new apply routes, returning
  `{valid, errors, warnings, summary}` - the shape `import-tracking` and the GRN import already
  use. Errors block, warnings do not. One rule, server-side, so the browser cannot disagree
  with what apply will actually do.
- **N2. Test button.** Every SCM upload dialog gets it, beside Confirm, rendering the standard
  green/red/amber blocks. The SCM uploads were the odd ones out; this is the fix for that,
  not a feature of the new feed.
- **N3. Create the orders.** Header + lines, the ownership rule above, idempotent on re-upload,
  provenance stamped. Items we do not hold named and skipped.
- **N4. Adoption from the other side.** The outstanding SO importer adopts an inquiry-created
  order instead of duplicating it. Tested in BOTH orderings in one test.
- **N5. The list.** Sales orders created from Order Inquiry, with customer, dates, location,
  line count, and the purchase orders each line waits on with resolved/waiting state. Row
  opens the EXISTING sales-order detail page - a second detail page for the same entity is
  how two screens start disagreeing.

## What "done" looks like

Joey uploads his sheet and, without CS touching anything, tomorrow's plan is computed against
the demand it carries. He can see the orders it created, what each is waiting on, and where
the stock lands. What could not be created is named on the screen. When CS's book eventually
arrives, nothing duplicates and their numbers take over.
