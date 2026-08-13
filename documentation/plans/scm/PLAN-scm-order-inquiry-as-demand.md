# PLAN - the Order Inquiry sheet as a source of sales orders

**Status:** written 5 Aug 2026, pre-code. UAC: `scm-order-inquiry-as-demand-acceptance-criteria.md`.

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

## The ownership rule

**Whoever created the order owns its figures.**

| the order | the sheet does |
| --------- | -------------- |
| does not exist | creates it, `source_system = scm_order_inquiry` |
| exists, created by the sheet | refreshes its lines, keyed by (order, item) |
| exists from any other source | annotates only: stock location + PO claim, exactly as today |

And the reverse: when CS's outstanding book later names an order the sheet created, it ADOPTS
it - matching on `so_number` as it already does - and from then on CS's quantities and dates
win, because the outstanding extract is a statement of the whole open book and the sheet is
one person's working record.

Stated as a rule rather than left to whichever upload runs last, because "last writer wins"
across two feeds with different refresh rhythms is how a quantity silently reverts.

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
