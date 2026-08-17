# UAC - the product upload carries the reorder level and reorder quantity

Status: drafted 2026-08-16, awaiting sign-off
Source: user, 2026-08-16, with `Stock List 14 Aug 2026.xls` (11,649 rows) as the sample export.

> "this is the reorder level and quantity sheet, this is uploaded at the product list, we used
>  to capture item code, description etc, now we need to capture the reorder level and reorder
>  quantity which is by product"

## Journey

**Who.** The purchasing officer who maintains stock items in AutoCount. They already export a
Stock List from AutoCount and upload it at **Master Data → Products → Import** whenever the
item master changes. Nothing about how they arrive changes.

**What the system already knows.** The file they upload today already carries `Reorder Level`
and `Reorder Qty` beside `Item Code` and `Description` - the importer has simply been dropping
those two columns on the floor. Nothing new is asked of them: the number is already in the file
they already send.

**The steps.**

1. They export the Stock List from AutoCount, unchanged.
2. Products → Import → drop the file. **Test** first, as today.
3. The test result adds one line to what it already says: how many rows carry a reorder level,
   and how many of those disagree with a level somebody in the CRM set by hand.
4. They confirm. The import runs in the background, as today.
5. The job detail page reports the levels applied, and lists the disagreements by item code.

**What they hold at the end.** Every product's reorder level and reorder quantity now read off
the product detail page and the product list. The SCM plan stops saying "needs level" for items
AutoCount has a level for, and its `master` column agrees with the item master because both came
from the same upload. Nobody had to visit a second screen or key a number twice.

**What everyone else is told.** Nothing is notified. This is master data catching up with a file
the office already sends; there is no event here worth interrupting anyone for.

## Acceptance criteria

### AC-1 - the two columns are read (step 2)

Given a product import file whose header row carries `Reorder Level` and/or `Reorder Qty`,
when the import runs,
then each row's values are written to `products.reorder_level` and `products.reorder_quantity`
for that item code.

Header spellings accepted are exactly the ones the SCM reorder-level upload already accepts
(migration 347): `Reorder Level` / `Re-order Level` / `ReorderLevel` / `Min Level`, and
`Reorder Qty` / `Reorder Quantity` / `Re-order Qty` / `ReorderQty`. A new spelling is fixed by
adding an alias row, not by a release.

### AC-2 - zero is a number, blank is silence (step 4)

Given a row whose `Reorder Level` cell reads `0`,
then `products.reorder_level` is set to `0` - not NULL.

Given a row whose `Reorder Level` cell is blank,
then `products.reorder_level` is set to NULL.

The distinction is load-bearing: the SCM engine reads a NULL level as "nobody set one" and emits
the item as `needs_level`, where `0` is a real threshold it will plan against. In the sample file
7,852 of 11,649 rows read `0` and 642 are blank, so both cases are the common case, not an edge.

`Reorder Qty` follows the same rule, independently - the two columns are read per cell, and a row
may carry one without the other (25 such rows in the sample).

### AC-3 - a blank cell clears a held value (step 4)

Given a product that holds `reorder_level = 250` in the CRM,
when a file carrying the `Reorder Level` column names that item with a blank cell,
then `products.reorder_level` becomes NULL.

AutoCount owns this number. A blank cell in a file that carries the column is AutoCount saying
the level is gone, and the CRM follows.

### AC-4 - a file without the column changes nothing

Given a product import file whose header row has NO `Reorder Level` column at all (every
pre-existing product upload),
when the import runs,
then no product's `reorder_level` is read, written, or cleared.

This is the guard on AC-3. The rows arrive as dicts with blank cells omitted, so "column absent"
and "column present, all cells blank" are indistinguishable per row. The importer therefore
decides ONCE per file, by scanning for the header across all rows: a column that no row carries a
value for is treated as absent, and the import leaves every held level alone. Stated plainly
because it is a deliberate refusal to act on an ambiguous file, not an oversight.

### AC-5 - the same upload feeds the plan (step 5)

Given a row carrying a reorder level for an item that resolves to a product,
when the import runs,
then a `scm.reorder_level` row for that product with `warehouse_id` NULL (product-wide) is
created or updated with the level and quantity, `source = 'autocount'`.

The sample file has no location column, which is already how that table scopes a product-wide
level. One upload, both stores, so the item master and the plan cannot disagree about a number
that has one owner.

### AC-6 - a level a person set is never silently overwritten (step 5)

Given a `scm.reorder_level` row whose `source` is `manual` or `accepted_suggestion` and whose
`level` differs from the file,
when the import runs,
then the held level STANDS, the row is counted as a conflict, and the item code, the held level,
the file's level and who held it are reported on the job detail page.

The reorder quantity still lands in that case, through a write that leaves `level` and `source`
untouched - otherwise a quantity would flip a hand-set row to AutoCount ownership and the NEXT
upload would overwrite the level a person chose.

This is the rule `reorder_level_import_service` already enforces for its own upload. The product
import reuses it rather than restating it.

### AC-7 - blank does NOT clear the planning level (step 5, deliberate asymmetry)

Given a product that holds a `scm.reorder_level` row,
when a file carrying the `Reorder Level` column names that item with a blank cell,
then `products.reorder_level` is cleared per AC-3 but the `scm.reorder_level` row is left alone.

Flagged because it is the one place the two stores diverge. The reason is AC-6's: the planning
table holds levels people set, and a filtered or partial export full of blanks would wipe the
planning basis wholesale with no conflict reported, because a blank carries no value to disagree
with. Clearing a planning level stays a deliberate act on the SCM screen.

### AC-8 - the test button tells the truth before anything is written

Given a file at the Test step,
when the validation runs,
then it reports the number of rows carrying a level, the number that would be cleared, and the
number that would conflict with a hand-set planning level - the same numbers the confirmed run
produces for the same file.

### AC-9 - the job detail page reports what happened

Given a completed product import,
when the job detail page is opened,
then it shows levels applied, levels cleared, and conflicts, and lists each conflict by item code
with the held and file levels beside each other.

A conflict that is only counted is a conflict nobody can act on.

Mechanism, as shipped: conflicts land in `result.warnings`, which the job detail page already
renders as a list. A cleared level changes its row's outcome CODE to `reorder_level_cleared`
rather than adding a second row, so the rows card can group them without `processed_rows`
climbing past `total_rows`. No frontend change.

## Out of scope

- Per-location (per-warehouse) levels. The sample file has no location column; the SCM upload
  already handles that case for the file that does.
- Any change to the SCM reorder-level screen or its own upload. It keeps working as it does.
- Notifying anyone that a level moved.
