# PLAN - Purchase history, stock location, and the SO<->PO linkage

**Status:** L0-L4 DONE, and both feeds are reachable from the reorder page (5 Aug 2026).
L5 (ageing signal) remains.

> "I do find something missing here is the location & linkage to SO, so we sort of need to
> curate the data first cause I am not going to ask the user to provide me anytime soon."

## The finding that changes the shape of this work

**Neither is missing.** Both are in files the user already supplied, alongside the PO listing:

| file | what it holds |
| ---- | ------------- |
| `Purchase Order Listing With Detail2020.xls` | 1,586 POs, 50,526 rows. Doc no, date, creditor, currency, and per line: item, description, UOM, qty, unit price, amount. |
| `Order Inquiry Form.xlsx` | SO DATE, S/O NO, ITEM CODE, QTY, DELIVERY DATE, PROJECT/CUSTOMER, **STOCK LOCATION**, **REMARK** |
| `JAN - DEC 2026 ORDERabc.xlsx` | the same, per month, with **PO NO** and **SUPPLIER** as their own columns |

`STOCK LOCATION` is the warehouse code (`BRW-IB`). `REMARK` is either the literal `ORDER`
(nothing placed yet) or a **PO number** - and `202605-S0042` is the same numbering family the
PO listing uses. So the SO->PO pairing and the location are already maintained by the people
who own them, in a sheet they already keep. No curation screen, and nothing new to ask for.

**Decision (user, 5 Aug 2026): ingest Order Inquiry as a third feed.** The dependency is that
the sheet stays current; that is a lighter commitment than a curation UI nobody has time to
operate, and it is the same commitment the SO and PO uploads already carry.

## The second finding, which is a gap rather than a discovery

**The PO listing cannot say what is still outstanding.** Its only quantity column is `Qty`
ordered. There is no received quantity, no outstanding quantity and no line status - the
report's own criteria line says only `Cancelled Status: Show Uncancelled`. So:

- this feed is the **order book**: what was ordered, when, from whom, at what price;
- **outstanding-ness comes from elsewhere** - the existing outstanding-PO extract, or GRN
  receipts matched against these lines.

Treating this file as an outstanding feed would import 1,586 closed 2020 orders as incoming
supply and inflate every position in the system. It must not be wired to the outstanding
channel, and the write path has to be explicit that these lines arrive already received.

## What the file actually looks like

A **banded report**, not a table. Two label rows, then repeating blocks:

```
row  9  Doc No | Date | Code | Creditor Name | Curr. | Total | Local Total      <- header labels
row 11  No. | Item Code | Description | UOM | Qty | Unit Price | Disc.          <- line labels
row 14  202001-S0001 | 2020-01-02 | 400-F020 | FOSHAN ROYAL ... | CNY | 10800 | 32400
row 20  1 | CBM1030 | CABANA MIRROR 500X700 | UNIT | 450 | 24 | 10800 | 32400
row 25  SPO-2020/01-0001 | ...                                                  <- next PO
```

Three traps, each of which silently corrupts the import if missed:

1. **Merged cells shift the columns.** The label `Curr.` sits at column 47; its value sits at
   48. `Total` at 54, value at 50. Absolute column mapping is wrong on the first block.
   Bind by **column BANDS** learned from the label row - a value belongs to the last label at
   or before its column - which is how a banded report is meant to be read.
2. **A trailing "Final Summary By Items" section** (rows 46,733-50,520) repeats every item
   with `Item Code | UOM | Qty | Amount`. It looks exactly like line rows. Parsing must stop
   at the `Doc Count:` marker or every item is counted twice.
3. **Non-stock lines.** `MISC`, `HANDLING CHARGES`, `WAREHOUSE HANDLING CHARGES` are real
   lines with real money and no product. They belong to the order's cost, not to any item's
   supply, and must not be resolved against the product catalogue or reported as unmatched.

Three doc-number families, all legitimate: `202001-S0001` (888), `SPO-2020/01-0001` (414),
`PO-2020/01-0001` (284).

## Both-way linkage, which is the part that has to be right

A PO can be uploaded before its SO exists, and an SO before its PO. Neither order may lose
the pairing, and neither may invent one.

**Match on (SO number, item code)** - the user's decision, and what the Order Inquiry sheet
itself keys on. One PO covering lines from more than one SO is visible in the sample, so
matching on SO number alone would attach the whole order to the first SO it saw.

The mechanism is a **pending-link table**, not a nullable FK:

```
scm.order_link_claim
  so_number      text        the number as the source spelled it
  item_code      text
  po_number      text
  source         text        'order_inquiry' | 'po_upload' | 'so_upload'
  claimed_at     timestamp
  resolved_at    timestamp   null until BOTH sides exist
  so_line_id     uuid null   filled on resolution
  po_line_id     uuid null   filled on resolution
```

- Every feed WRITES claims for what it knows, and never waits for the other side.
- A resolver runs after each upload and fills in whichever side is now present.
- An unresolved claim is **visible**, not silent: "34 orders name a PO we have not seen" is a
  real answer, and it is how somebody finds out the PO book is a month behind.

A nullable `so_line_id` on the PO line alone cannot do this, because a claim made before the
SO exists has nowhere to live and would be dropped on the floor.

## Historical POs in planning

**Decision (user):** history is imported, and it is not inert.

> "if I order from 5 years ago and now still got stock meaning this is not very hot selling"

So a historical PO contributes three things, and each is a DIFFERENT existing consumer:

1. **Last cost - yes. Supplier lead time - no, and it cannot.** The cost flows already: the
   Summary Order Report reads `last_po_cost` / `last_po_date` straight off the purchase-order
   lines by issue date, and it deliberately keeps a supplier who is no longer linked, so the
   2020 creditors show up as the historical sources they are. Lead time does NOT, and this is
   a property of the file rather than a gap in the work: lead time is measured from the order's
   issue date to the **completing goods receipt** (`_completing_receipts`, over
   `picking_headers`), and the Purchase Order Listing has no received column, no receipt date
   and no receipt document anywhere in it. Deriving a lead time from it would mean inventing
   the receipt date, and an invented lead time is worse than a missing one because the planner
   would size safety stock on it. Lead time stays with the outstanding/GRN path.
2. **An ageing signal.** Stock still on hand against a purchase years old is the definition of
   a slow mover, and it is stronger evidence than demand variance alone because it is a fact
   about THIS stock rather than a statistic. Feeds the existing dead-stock disposition rather
   than inventing a fourth vocabulary - as a second BASIS for the same call, not a new one.
3. **The PO list.** They appear as purchase orders, because a buyer looking for what was
   bought from a supplier in 2020 should find it.

They must NOT count as incoming supply. Written with `qty_received = qty_ordered` and a
closed line status, so `scm.on_order_v` - which already excludes non-open lines - ignores them
by construction rather than by a special case.

## Slices

- **L0. Accept `.xls`, configurable.** DONE (`799887539`). Magic-byte container sniffing,
  `SCM_UPLOAD_EXTENSIONS` as the single accept list, served to the dialog.
- **L1. Banded reader** for the PO listing: label-row bands, block detection, stop at
  `Doc Count:`, non-stock lines carried as order cost and named as such. Test against a
  committed real slice of the customer's own file.
- **L2. History write path**: purchase orders written closed and fully received, idempotent on
  re-upload by doc number + line, and excluded from on-order by construction. Proven by a
  position assertion, not by reading the code.
- **L3. Order Inquiry feed**: a third upload channel. Writes the warehouse onto SO lines and
  a link claim per (SO number, item code, PO number). `ORDER` in the remark column means "no
  PO yet" and is a claim with no PO side, not a parse failure.
- **L4. Link resolver**: runs after every one of the three uploads, resolves claims both ways,
  and reports what is still unresolved on the upload result.
- **L4b. Reachable.** Two routes (`/purchase-history/*`, `/order-inquiry/*`) plus the open-link
  report, and one `Upload data` menu on the reorder page carrying all four channels grouped by
  what they do to the plan. Separate routes and a separate dialog from the outstanding
  importer, because the files are different SHAPES and different MEANINGS: one `kind`
  parameter would produce a route whose branches share nothing. The preview/confirm flow
  itself IS shared (`useTwoStepUpload`), so the sequence guard and the server-owned accept
  list cannot drift between the two dialogs.
- **L5. Ageing signal.** DONE. `disposition()` gains a second way to be dead and says WHICH
  fired (`basis`: `movement` | `ageing`), because they are different evidence and a buyer acts
  differently on each. The reason quotes the age - *"bought 1,876 days ago and has never
  moved"* - rather than asserting one.

  The rule is deliberately narrow: the ageing branch speaks ONLY where the movement rule
  abstained. That abstention ("no consumption history is not the same as a stale movement")
  was right while there was no evidence either way; the purchase history is exactly that
  missing evidence, so it is now right only while the purchase date is ALSO unknown. A SKU
  that moved recently is not dead however old its last purchase is - slow-but-selling is what
  the overstock check is for.

  `_last_purchase_map` is keyed by PRODUCT, not by (product, warehouse): the export names no
  location, so a per-warehouse lookup would read "never bought" for precisely the stock the
  signal exists to judge.
- **L5b. The PO list tells the truth about a historical order.** "It should appear in PO list
  also" - and it did, reading `Total qty 0` and `Lines 0`, because both counted OPEN lines
  only. Correct for supply, wrong for a column labelled "Total qty". The two questions now
  have two figures (`total_qty`/`line_count` = what the order says, `open_qty`/
  `open_line_count` = what is still coming), and the detail page shows the second only when it
  differs. `source` reports `import` rather than `manual`, because nobody keyed 1,586 orders.

## What the files turned out to say, once read (5 Aug 2026)

Three things that were not visible before the real data went through the parser, each of
which changed the design:

**The PO listing carries part of the linkage itself.** `**SO:174830**` appears as a
description-only NOTE line inside the order block, sometimes with the project attached
(`-HOMEPRO @ SO:174830`). 43 of 1,586 orders in the 2020 file. Captured, but ORDER-level: a
note sits between lines and nothing says which side it describes, so a per-line claim would
assign one customer's stock to another customer's order.

**A sales-order line can wait on more than one purchase order.** The Order Inquiry sheet
writes `202606-S0024 & 202607-S0043`, and `202605-S0042 & ORDER` for a line partly ordered and
partly not. Matching the cell as a whole - which is what a first implementation does - drops
both numbers and the loss is invisible, because the line still shows a PO.

**The monthly book is 35 sheets and has different columns from the form.** `STOCK LOCATION`
and `REMARK` in one, `SUPPLIER` and `PO NO` in the other, in different positions. So columns
are found by header NAME and every sheet with a header row is read: a positional reader is
right on one file and silently wrong on the other, and reading only the first sheet would
drop eleven months without saying so.

### The limit that remains, stated rather than smoothed over

**A stock location can only be written onto a sales-order line that exists.** Unlike the PO
pairing - which is a claim precisely so it can outlive a missing document - a location has
nowhere to live until its line does. Those rows are counted and their sales orders NAMED, and
re-uploading the sheet after the SO book lands applies them. Making location a claim too is a
small extension of the same table (`po_number` would have to become nullable, with the
uniqueness index coalescing it) and is worth doing if the customer's upload order makes it
bite.

**A test that asserts "this upload CREATED something" cannot own real document numbers.** The
committed fixture is a real slice, so once the same file has been uploaded through the screen
against the dev database, its orders exist before the test runs and `orders_created > 0` reads
0. Fixed by having the test delete exactly the documents it is about, inside its rolled-back
session (`blank_book`), so it is deterministic on a polluted local database AND on CI's empty
one. It is the CI seed-data trap in the mirror: do not assume a row is absent either. The
route-level twin of the same test survives only because `as_company_user` creates its own
company, which hides Sorento's rows - worth knowing rather than relying on.

## What the customer's own files did, uploaded through the screen (5 Aug 2026)

Run against the real files, via the sidebar and the dialog, not a script:

| file | result |
| ---- | ------ |
| `Purchase Order Listing With Detail2020.xls` (13.5 MB, legacy BIFF) | 1,586 orders, 12,924 lines written, 534 charge lines carried, 02/01/2020 to 31/12/2020, 43 sales-order claims |
| `JAN - DEC 2026 ORDERabc.xlsx` | 15,797 rows over 35 sheets, 3,147 purchase-order claims, 10 sales-order lines matched |

**`scm.on_order_v` did not move**: 5 rows before and after, all of them genuine open orders.
Twelve thousand history lines contributed nothing to supply, which is the invariant this feed
had to satisfy and the one that would have been most expensive to get wrong.

Two things the screen got wrong on the real files and now does not:

- The named lists are capped at 200 by the backend, and the heading counted the CHIPS. So
  15,787 sales orders we have not received read as "(200)" - a small, closed-looking problem.
  The heading now carries the real total and the chips are a stated sample.
- The 2026 book carries `SUPPLIER` / `PO NO` and no `STOCK LOCATION`, so "0 locations written"
  is correct rather than a failure, and it is now legible as such next to 3,147 links claimed.

## What "done" looks like

The customer uploads their three files in ANY order. Afterwards: every 2020 PO is in the PO
list with its supplier and cost; no 2020 order appears as incoming supply anywhere; every SO
line that the Order Inquiry sheet gives a location has one; the SO<->PO pairs resolve
regardless of which file arrived first; and the ones that do not resolve are counted on the
screen rather than lost.
