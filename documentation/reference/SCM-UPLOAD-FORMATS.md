# SCM upload formats: stock list, proforma invoice, packing list

For anyone uploading a supplier's file into a loading plan: what the system reads, what it
needs, and what it does when the file does not say everything cleanly. Written from the code
that actually reads these files, not from a wish list.

There are two uploads this document covers in full (the stock list and the proforma invoice),
and a third (the packing list) it only points at, because that one is covered elsewhere.

## 1. Before either upload: the shared rules

**File types and size.** Both uploads accept a modern Excel file (`.xlsx`), an Excel file with
macros (`.xlsm`, the macros are quietly stripped before the file is read), and the older
`.xls` format. Which extensions are accepted is a setting, not fixed in the program, so a new
format a supplier switches to can be turned on without waiting for a release. Neither upload
enforces a file-size limit of its own; the web server in front of the CRM refuses any single
upload larger than 50 MB in production, and that is the only size ceiling either of them has.

**Which sheet is read.** Only the sheet that was open and active when the file was last saved,
which in practice is always the first tab. Other tabs in the same workbook, a set of helper
calculations, a second language, a hidden reference sheet, are not read at all. Whatever sits
on the sheet that opens first is the whole of what the upload sees.

**Column headers do not have to match exactly.** Spacing, capital letters, line breaks inside a
header cell, and full-width brackets (the kind some Chinese spreadsheets use) are all folded
away before a header is compared, so `净重` and `净重 (KG)` and a header with a line break in
the middle of it are read as the same column. The tables below list every spelling the system
already recognises. A supplier who renames a column, or writes it in a way nobody typed in
before, needs one row added to the alias list; it does not need a code change.

**The supplier always comes from the dialog, never from the file.** Neither file reliably
states who sent it. A stock list carries only model numbers and quantities and says nothing
about its author at all. A proforma invoice may carry a letterhead, but that letterhead is used
only to warn the operator if it looks like a different supplier than the one they picked (see
section 6); it is never used to decide whose stock or invoice this is. Both upload screens
require the operator to choose the supplier before the file is read, and there is no way to
upload either file without doing so.

## 2. Stock list (the supplier's own inventory)

This is the file a supplier sends listing what they currently hold: how much is packed and
ready to load, and how much is not yet finished. It replaces the ENTIRE previous stock list for
that supplier (or, when the upload is made from inside a loading plan, that plan's own copy of
it) every time a new one is uploaded. It is a snapshot, not something the system adds to over
time.

**How the header row is found.** The system reads the sheet from the top, row by row, looking
for the first row that can name the model-number column. That row becomes the header, whatever
else it does or does not carry. Once found, that same row must also be able to name the
packed-quantity column, or the whole file is refused as unreadable and nothing is read from it.
Any text found in a row ABOVE the header (the file's own title, an address, a company name) is
kept as the file's "letterhead" for the supplier check in section 6.

**Required and optional columns.**

| What it holds | Required | Column headers accepted |
| --- | --- | --- |
| Model number | Yes | `型号`, `MODEL` |
| Packed quantity (ready to load) | Yes | `包装好库存` |
| Unfinished quantity (still at the factory) | No | `空瓷` |
| Volume per unit, in cubic metres | No | `体积(cbm)` |
| Volume for the whole line, in cubic metres | No | `总体积(cbm)` |
| Brand | No | `商标` |
| Spec | No | `规格` |
| Product name | No | `品名` |
| Remark | No | `备注` |

The two quantities are never added together into one number. Packed stock can go on a
container this week; unfinished stock is a request still sitting with the supplier's
production line. If the file states a line's total volume but not its per-unit volume, the
per-unit figure is worked out by dividing the total by the quantity; if the file states
neither, the volume for that line is left blank rather than treated as zero, because "nobody
measured this" and "this takes no space" are different facts.

There is no date column on this file at all. The date the stock list is treated as being "as
of" is whatever the upload dialog is set to, not anything read out of the file.

**What makes a row skipped, and how it is reported.**

- A row with no model number and no quantity in either quantity column is passed over
  silently. This covers the file's own title rows, blank spacer rows, and notes.
- A row with no model number but WITH a quantity is skipped and reported as a problem ("no
  model number on a row with stock"), because the system cannot tell whether this is a real
  item missing its label or the sheet's own totals row.
- If no row anywhere in the sheet can name both the model number and the packed-quantity
  columns, the entire file is refused; nothing is read from it.
- Two rows naming the SAME model number are combined into one, with their quantities added
  together (a supplier who lists two spec lines of one body). This is reported as models
  merged, not as a problem, because it is a normal shape for the file to take.

**Matching model numbers to our catalogue:** see section 5.

## 3. Proforma invoice

This is the supplier's priced document: what they are charging for the goods. One file can
hold ONE invoice, or several stacked one after another down the same sheet (this is how the
JINBAICHUAN pre-loading list works: five invoices, one sheet, no gap and no page break between
them).

**How the header row is found.** The system reads every row of the sheet in order. Any row
that can name THREE columns together at once, model number, quantity, and unit price, is
treated as a header row, and it also marks the START of a new invoice. Everything under it,
down to the next such header row (or the end of the sheet), belongs to that one invoice. A
row that names a model number and a quantity but no price is not a header at all: a table with
no price column is a packing list, not an invoice, and the file is refused with that column
named as missing.

**Stacked invoices and labelled fields.** Above the FIRST header row (and, for a stacked file,
in the gap between one invoice's last line and the next invoice's header row), a row can carry
document-level facts rather than a line of goods: the invoice number, its date, a container
number, a bill-of-lading number, or the currency it is priced in. These are written either as
two cells side by side (a label, then its value) or as one cell with a colon inside it (for
example `货柜号：XXXU1234567`). A cell that itself looks like another label is never read as
the previous field's value, which is what stops a blank field being answered by the next
label's own value.

**Required and optional line columns.**

| What it holds | Required | Column headers accepted |
| --- | --- | --- |
| Model number | Yes | `产品型号`, `编号`, `型号`, `ITEM CODE`, `MODEL`, `Item No` |
| Quantity | Yes | `数量`, `产品数量`, `QTY`, `Quantity` |
| Unit price | Yes | `RMB`, `单价(元)`, `单价`, `UNIT PRICE`, `Unit Price`, `PRICE` |
| Description | No | `品名`, `DESCRIPTION`, `Description`, `货名` |
| Spec | No | `规格` |
| Unit of measure | No | `单位`, `UOM`, `Unit` |
| Line amount | No | `金额（rmb）`, `金额`, `总价（元）`, `总价`, `AMOUNT`, `Amount`, `TOTAL` |
| Our PO reference | No | `其他`, `PO NO`, `PO No.`, `PO`, `订单号`, `客户订单号`, `Order No` |
| Remark | No | `备注`, `REMARK`, `Remarks` |
| Brand | No | `商标` |
| Cartons | No | `箱数` |
| Volume per unit (cbm) | No | `体积(cbm)`, `CBM`, `Volume` |
| Volume for the line (cbm) | No | `总体积(cbm)`, `Total CBM`, `Total Volume` |
| Net weight | No | `净重`, `净重(kg)`, `N.W.`, `NET WEIGHT` |
| Gross weight | No | `毛重`, `毛重(kg)`, `G.W.`, `GROSS WEIGHT` |
| Material | No | `材质`, `材料`, `MATERIAL` |
| Pieces per carton | No | `装箱数`, `装箱量`, `每箱数量`, `PCS / CTN`, `PCS PER CTN` |
| Carton size, all three numbers in one cell | No | `外箱尺寸`, `箱规`, `外箱规格`, `SIZE`, `SIZE (CM)`, `CARTON SIZE` |
| Carton length (cm) | No | `外箱长`, `长`, `L` |
| Carton width (cm) | No | `外箱宽`, `宽`, `W` |
| Carton height (cm) | No | `外箱高`, `高`, `H` |

Separate length/width/height columns win over a combined carton-size cell where a file has
both, because the separate columns are numbers the supplier typed directly and the combined
cell is a sentence describing them (`62*53*40`, `62x53x40`, and `62 × 53 × 40` are all read the
same way). If a line states a total volume but not its per-unit volume, or the other way
round, the missing one is worked out from the one that is present; if it states neither, both
stay blank.

**Required and optional document-level (labelled) fields.**

| What it holds | Column headers / labels accepted |
| --- | --- |
| Invoice number | `货单号`, `发票号`, `PI NO`, `Invoice No`, `Proforma No`, `PI No.` |
| Invoice date | `日期`, `Date`, `Date 日期`, `Invoice Date` |
| Container number | `货柜号`, `Container No`, `Container No 货柜号` |
| Bill of lading number | `提单号`, `B/L NO`, `BL No` |
| Currency | `币种`, `Currency`, `CURRENCY` |

None of these five are required. An invoice that states no number of its own is given one
built from the uploaded file's own name plus its position in the stack, so re-uploading the
same file updates the same invoices rather than creating new ones each time.

**Date formats.** A date is read in this fixed order, and the first one that fits wins: a full
date and time; year-month-day with dashes; day.month.year; year.month.day; year/month/day; and
finally day/month/year. Year-first spellings are always tried before day-first ones, so a date
written `2026/07/31` is always read as 31 July 2026, never mistaken for the 31st month. A date
that fits none of these formats is left blank and reported as a problem naming the row it came
from, rather than silently guessed at or silently dropped.

**Totals rows.** A row is read as a totals row when it carries a recognised label anywhere in
it: `合计`, `总金额`, `总计`, `金额合计`, `TOTAL`, `Grand Total`, or `Total Amount`. The number
belonging to that label is whichever number sits closest to it, first looking to its right,
then to its left (the pre-loading list's own totals row has its label sitting one column to
the left of where the number actually is). That total is kept as what the invoice SAYS it
comes to, and is compared against the sum of its own lines: if the two disagree by more than
one cent, the Test verdict warns that the stated total does not match the sum of the lines.

**What makes a row skipped, and how it is reported.**

- A row that names a model number but states no readable quantity is skipped and reported by
  name (either "quantity is not a number" or "the row states no quantity").
- A row with neither a model number nor a recognised document-level label is passed over
  silently. This is the pre-loading list's own blank, numbered filler rows.
- A row that matches a totals label becomes the invoice's stated total (see above), not a line.
- A row that carries a document-level label is absorbed into the invoice that follows it, not
  counted as a line.
- A header row found with nothing under it at all (an empty template) is dropped and never
  becomes an invoice.
- If the file's table never names a price column at all alongside a model number and a
  quantity, the WHOLE file is refused, since a table with no price is a packing list, not an
  invoice.

**Currency.** A price is never stored without knowing what money it is in. The answer is taken
from the first of these that says something, in this fixed order:

1. Whatever currency the operator typed on the upload screen.
2. Whatever currency the document itself states (a header like `RMB` or `单价(元)`, or a
   labelled `Currency:` cell).
3. The supplier's own price list on file, but only when every price on it agrees on one
   currency.
4. Otherwise, nothing is assumed. There is deliberately no house default currency: storing a
   price without knowing its currency is worse than refusing to store it.

If the operator types something that is not a recognisable three-letter currency code, the
upload is refused outright rather than quietly falling through to the document's own answer,
so what the operator typed is never silently overridden. Each invoice in a stacked file has its
own currency worked out separately, since one file can genuinely mix currencies across its
invoices.

**Matching model numbers to our catalogue:** see section 5.

## 4. Packing list (pointer only)

The packing list (what actually went into a container) is read by a separate channel that
shares its underlying block-scanning machinery with the proforma invoice reader above, because
both files are structurally the same shape: labelled cells above a table of lines, possibly
stacked more than once down one sheet. It is not repeated here in full; see the packing-list
import behaviour for its own header aliases and container-block rules.

## 5. How model numbers are matched to our catalogue

Neither upload creates new products. An unmatched model number is kept as real stock or a real
invoice line, and reported as unmatched, but it cannot be placed onto a container until
someone fixes the catalogue or the supplier's own spelling of it.

Matching is tried in a fixed order (a ladder), and the FIRST rung that gives a single, certain
answer wins:

1. Something already decided for THIS exact code, for THIS exact supplier, on an earlier
   upload or by a person correcting a match by hand. This also covers a deliberate "this code
   names nothing we hold" answer, which stops the search here rather than trying again.
2. The code matches one of our product codes exactly.
3. The code matches once the dashes and spaces are stripped out of both sides (the supplier
   writes `SRTWC8357RL`, ours is `SRTWC8357-RL`).
4. The code matches once its parts are read in any order (the supplier writes the trap size
   before the suffix, we write it after).
5. The code matches once its own trailing size number is dropped, but ONLY when our product's
   own description names that same size. A size is never guessed away without that check.
6, 7, 8. The same three questions again, this time asked of our own combined-item ("set")
   codes, for a code that matched nothing in the product catalogue at all. A supplier
   sometimes sells a whole item, for example a toilet suite, under one code even though we
   hold it as two separate products (a pedestal and a cistern); these three rungs are what
   catch that.

If a code could equally mean two different products (or two different sets), it is left
unmatched rather than guessed at, because guessing would put stock or an invoice line against
the wrong item with nothing on screen to say so.

A match found by rungs 3, 4 or 5 is written down as a remembered match FOR THAT SUPPLIER, so
the next file from the same supplier reads a decision instead of working it out again. A set
match (rungs 6 to 8) is always written down, since nothing in the product catalogue names that
code at all to begin with. A remembered match never crosses suppliers: two different suppliers
can spell the same code two different ways, or spell it the same way and mean two different
things, and the memory is kept separately for each one.

## 6. The letterhead check

Both readers look at the first row, ABOVE the header row, that contains any text at all, and
keep the first non-blank cell in it as the file's "letterhead". If the header sits on the very
first row of the sheet, there is nothing above it, so no letterhead is captured and this whole
check is skipped for that file.

The check itself: does one of our ACTIVE suppliers' names appear, word for word (after folding
away case, spacing and full-width punctuation), somewhere inside that letterhead text? If the
supplier named is the one the operator already picked in the dialog, nothing is said. If a
DIFFERENT active supplier's name appears instead, and the picked supplier's own name does not,
the Test verdict warns: "File header names X, you picked Y."

This is a literal, word-for-word check, never an approximate or fuzzy one, and it has a real
limit that comes with that choice: it will not fire on a letterhead that is close to a
supplier's name but not identical to it. For example, a real file's letterhead reads "CHAOZHOU
JINBAICHUAN SANITARY WARE TECHNOLOGY CO.,LTD", while the supplier's name on file is "CHAOZHOU
JINBAICHUAN SANITARY WARE CO., LTD" (no "TECHNOLOGY"), so the check stays silent on that file
even though a person can see at a glance it is the same supplier's own letterhead. Widening
this check (matching on the supplier's own code, a stored alternate name, or a looser
several-words-in-common rule) has been discussed and is not yet decided or built.

## 7. What the Test verdict tells you

Both upload screens carry a Test step that reads the file exactly the way applying it would,
but writes nothing at all to the database. It always answers three questions:

- **Can this file be applied at all?** Something that BLOCKS the upload, the file could not be
  read, a required column is missing, or (for a proforma invoice) a priced line has no
  currency that can be worked out for it.
- **What will not make it in, even if you go ahead?** Something that does NOT block the
  upload. The rest of the file is still worth loading. This includes model numbers not in the
  catalogue (named, not just counted), rows with no measured volume, rows that could not be
  read at all, columns in the file that were not recognised, and, for a proforma invoice, a
  stated total that disagrees with the sum of its own lines. Because these are shown before
  the Confirm button, going ahead anyway is a decision the operator makes on purpose, not
  something that slips past them.
- **A summary of what the file holds.** How many rows or lines were read, how many model
  numbers matched the catalogue and how many did not, and (for a proforma invoice) how many
  invoices were found in the file and what each one totals.

A file that reads perfectly cleanly still goes through the same Test step; there is nothing
that only shows up when the upload is actually applied, because applying performs the
identical read the Test step already did.
