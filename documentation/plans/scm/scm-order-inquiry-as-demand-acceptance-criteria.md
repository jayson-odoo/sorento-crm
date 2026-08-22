# UAC - the Order Inquiry sheet as a source of sales orders

**Status:** written 5 Aug 2026. Groups A to E have SHIPPED on `main`; Group F was added
2026-08-13 per [ADR 0010](../../adr/0010-order-inquiry-loop-owned-by-project-sales.md) and has
SHIPPED on `feat/project-lead-to-so` (a267eed23, the provisional-to-AutoCount reconciliation on
ingest). Plan: `PLAN-scm-order-inquiry-as-demand.md`.

> "order inquiry is essentially SO, so it needs to be a list of SO created from order inquiry.
> Previously I needed someone to upload the outstanding SO, but now, maybe, to not involve the
> CS department which handles the SO, I can ask Joey to upload order inquiries, so the SO
> should be a proper SO with header and line, then the linkage also needs to be visualized,
> location etc."

## Journey

**Who.** Joey, the buyer. He already keeps the Order Inquiry sheet - it is his working record
of what customers have asked for and which purchase order each line is waiting on. He does
NOT own sales orders; CS does, and getting CS to export the outstanding SO book on Joey's
schedule is the dependency this removes.

**Where he arrives from.** The reorder page he plans on every morning, `Upload data` in the
toolbar. Same menu as the other three feeds, because it is the same act: loading what the
plan is computed from.

**What the system already knows.** Every product code, every warehouse code, every sales
order and customer it already holds, and every purchase order claim made by any earlier
upload. Joey is asked for one thing: the file.

**Step 1 - he picks the file.** The system reads it and tells him what it WOULD do, in the
shape every other importer in this system uses: valid or not, errors that block, warnings
that do not. He is not asked to interpret raw counts. Single decision: *is this the right
file?*

**Step 2 - he confirms.** Sales orders are created for the rows whose orders we do not have,
existing orders are annotated rather than overwritten, purchase-order links are claimed, and
stock locations are written. Single decision: *go.*

**What he holds at the end.** A list of the sales orders this sheet created - number,
customer, when it is due, where it lands, and which purchase order each line waits on - and
those orders are demand in tomorrow's plan. What could not be created is named, not silently
dropped.

**What everyone else is told.** CS is not interrupted. When CS later uploads the outstanding
SO book, it is authoritative: their figures win over the sheet's for the orders they own, and
nothing Joey uploaded is duplicated.

## Acceptance criteria

### Group A - the sheet creates sales orders

- **AC-A1 [BE]** GIVEN a row whose `S/O NO` matches no sales order we hold, WHEN the sheet is
  applied, THEN a sales order is created with that number, `source_system = scm_order_inquiry`,
  and one line per row carrying item, quantity, required date and stock location.
- **AC-A2 [BE]** GIVEN two rows sharing an `S/O NO`, THEN ONE sales order is created carrying
  two lines. An order is a header with lines, not a row.
- **AC-A3 [BE]** GIVEN a row whose item code we do not hold, THEN NO line is created for it
  and the code is named on the result. `sales_order_lines.product_id` is NOT NULL, so demand
  for an unknown product cannot be represented at all - and inventing the product would put a
  fabricated item into the catalogue.
- **AC-A4 [BE]** GIVEN a row whose only unknown is its item, WHEN its sibling rows are
  resolvable, THEN the order is still created with the lines that could be built.
- **AC-A5 [BE]** GIVEN a row naming a project or customer, THEN the sales order is linked to
  that customer when one of that exact name already exists, and otherwise carries the name in
  `internal_note` with `customer_id` left NULL.

  REVISED after reading the schema, and the revision is the safer half. `customers` requires
  a `customer_code` and enforces uniqueness on `(lower(code), lower(name))`, so "create the
  customer when absent" means inventing a debtor code from a project label - master data
  Sales owns, in a table where a guessed code either collides or quietly duplicates a real
  account. The project is preserved either way, `customer_id` is nullable, and demand with no
  linked customer is still demand.
- **AC-A6 [BE]** GIVEN a created order, THEN it counts as demand: its lines are `open` with a
  `required_date`, so the netting and the Coverage Timeline read them like any other.

### Group B - who owns an order

- **AC-B1 [BE]** GIVEN a sales order that already exists from ANY other source, WHEN the sheet
  names it, THEN its quantities, dates and status are NOT touched. The sheet reverts to what
  it does today: write the stock location and claim the purchase-order link.
- **AC-B2 [BE]** GIVEN an order the sheet itself created, WHEN the sheet is uploaded again,
  THEN its lines are refreshed from the file rather than duplicated - keyed by
  `(sales order, item)`.
- **AC-B3 [BE]** GIVEN CS later uploads the outstanding SO book naming an order the sheet
  created, THEN the outstanding importer ADOPTS it rather than failing or duplicating, and
  from that point CS's figures are authoritative.
- **AC-B4 [T]** The two feeds are asserted together in one test, both orderings. A precedence
  rule that only works one way is not a precedence rule.

### Group C - the test function, as a standard

- **AC-C1 [BE]** `POST .../apply?validate_only=true` writes NOTHING and returns the shape
  every other importer returns: `{valid, errors, warnings, summary}`.
- **AC-C2 [BE]** An error BLOCKS (the file cannot be applied); a warning does not. Rows we
  cannot match are warnings, because the rest of the file is still worth loading. A header we
  cannot read is an error.
- **AC-C3 [FE]** Every SCM upload dialog carries a `Test` button beside Confirm, rendering the
  standard green "No errors" / red errors / amber warnings blocks. This is the behaviour the
  order-tracking and GRN imports already have, and the SCM uploads were the odd ones out.
- **AC-C4 [FE]** Testing is never mandatory. Confirm stays enabled on a readable file.

### Group D - seeing what arrived

- **AC-D1 [FE]** A list of the sales orders created from Order Inquiry: number, customer,
  order date, required date, line count, quantity, stock location, and the purchase orders
  its lines are waiting on.
- **AC-D2 [FE]** The linkage is visible per order: which PO each line claims, and whether that
  claim is resolved or still waiting for the other side.
- **AC-D3 [FE]** Reachable from the SCM sidebar, and the row opens the existing sales-order
  detail page rather than a second one.
- **AC-D4 [FE]** Empty state names the next step (upload the sheet), per the CRUD standard.

### Group E - the limits, stated on screen

- **AC-E1 [FE]** Items we do not hold are named, with the count, and say plainly that those
  lines were skipped.
- **AC-E2 [FE]** Orders NOT created because another source owns them are counted and
  distinguished from orders created, so "nothing happened" is never ambiguous.
- **AC-E3 [BE]** No upload ever creates a product. Asserted, not assumed.

### Group F - the two numbers, and no double count (added 2026-08-13, ADR 0010)

The sheet is exported before AutoCount has issued the SO number, so the order the sheet
creates and the order CS's outstanding book creates carry DIFFERENT numbers for the same
demand. Group B's adoption rule matches on `so_number` and therefore cannot see it. These are
the criteria for the reconciliation, which lives module-side in `project_so_ingest_service`
per ADR 0010.

- **AC-F1 [BE]** GIVEN the sheet creates a sales order, THEN that row is stamped
  `demand_origin = 'scm_order_inquiry'` at creation, and its `so_number` is the project's
  `provisional_ref` until AutoCount issues the real number. The stamp is what every rule below
  keys on, so it is written at creation and never backfilled.
- **AC-F2 [BE]** GIVEN project AutoCount ingest learns the real doc number, WHEN no core sales
  order holds that number, THEN the sheet-created row - matched on
  `so_number = provisional_ref` AND `demand_origin = 'scm_order_inquiry'` - is RENUMBERED in
  place to the real number. NO second row is created.
- **AC-F3 [BE]** GIVEN the outstanding book has already created the real-numbered row, WHEN
  project ingest learns that number, THEN the project order LINKS `so_id` to the existing row
  and the provisional sheet-created row is RETIRED. `scm.committed_v` never counts the same
  demand twice, asserted on the view and not on the row count alone.
- **AC-F4 [T]** BOTH orderings are asserted in ONE test module: sheet before book (the renumber
  case) and book before sheet (the retire case). A reconciliation that only works one way is
  not a reconciliation, and splitting the two orderings across files is how one of them quietly
  stops being run.
- **AC-F5 [BE]** GIVEN a sales order whose `demand_origin` is NOT `'scm_order_inquiry'`, THEN
  this logic never renames it, never retires it, and never otherwise touches it - whatever its
  number collides with. `outstanding_import_service` is unchanged by all of the above.
