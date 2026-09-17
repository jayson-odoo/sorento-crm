# Supply Chain - Order inquiry handover email to purchasing

During the parallel run, every time customer service raises, changes or cancels an order
inquiry row in one write, purchasing gets an email shaped like the manual mail CS used to type
by hand. This explains what's in it, what sends it, and how to manage it.

## What purchasing receives

One email per customer-service write - one email per raise, per settle, or per cancel, not one
per line inside it.

**Subject:** `OI: <stock location> @ <S/O list>` when every line shares one stock location, for
example `OI: BRW-BB @ SO397450 , SO397460`. Across several locations the subject drops the
location: `OI: SO397450 , SO397460`.

**Body**, top to bottom:

1. A red headline naming the verb(s) in the mail: **ORDER**, **RESERVE & ORDER**, **ORDER
   BACK**, **PRE-ORDERED**, **ALREADY INBOUND**, **ADVANCE**, **DELAY**, **CHANGE SO NO**,
   **CANCEL BALANCE**.
2. A sales-order table: **S/O NO**, **CUSTOMER**, **PROJECT**. This is the only place
   **CUSTOMER** and **PROJECT** appear.
3. A line table: **SO DATE**, **S/O NO**, **ITEM CODE**, **QTY**, **QTY CHANGE TO**,
   **DELIVERY DATE**, **DELIVERY DATE CHANGE TO**, **REMARK**.
4. "Raised by \<name\> (\<email\>) on \<date\>."
5. A link, **Open in Order Inquiries**, that opens the **Order Inquiries** worklist already
   filtered to the sales orders in the mail.

**How a change reads.** **QTY** and **DELIVERY DATE** always print what the line was; when
either one moved, the new value prints in its own **QTY CHANGE TO** or **DELIVERY DATE CHANGE
TO** column next to it - no strikethrough to decode, no cell holding two numbers. A line whose
quantity moved 182 to 214 reads **QTY 182**, **QTY CHANGE TO 214**. A line whose delivery date
moved reads **DELIVERY DATE 01/09/2026**, **DELIVERY DATE CHANGE TO 01/04/2027**, and **REMARK**
reads DELAY or ADVANCE depending on which way it moved. Every date in the mail reads
`dd/mm/yyyy`. A cancelled line prints its old quantity in **QTY** and **0** in **QTY CHANGE TO**,
with **REMARK** reading **CANCEL BALANCE 280 NOS** - the same figure either way, never a
separate cancel-then-order pair. A plain new line prints **QTY** only, both **CHANGE TO**
columns blank, **REMARK ORDER**.

**How an item swap reads.** Swapping the product on a line prints as two lines in the table: a
CANCEL BALANCE line for the old item and an ORDER line for the new one, not a single combined
row.

A line whose quantity and delivery date are unchanged from the last mail never appears - only
what actually moved or was cancelled is printed. Confirming a second time with nothing left to
change sends no mail at all, not an empty one.

**Still-open amendment instructions.** If the order also carries amendment rows raised by an SO
change (DELAY, ADVANCE, CANCEL BALANCE, CHANGE SO) that purchasing has not yet actioned, they're
listed in the same line table, after this Confirm's own lines, so purchasing reads one page per
Confirm instead of having to remember an earlier mail. An order with nothing still open there
adds nothing.

## What sends it, and what doesn't

Sends one mail:

* Confirming lines on the fulfilment board.
* Applying a planning change, including **Confirm** (confirm-all).
* An SO amendment (editing a sales order's lines and clicking **Save sales order**).
* Re-uploading the sales order book (**Upload sales orders** on Reorder Planning).

Never sends anything:

* Purchasing's own actions on **Order Inquiries** - **Acknowledge**, **Reject** / **Reject
  selected**, **Link now** / **Auto-link**, **Unlink** / **Unlink selected**.
* **Upload order inquiry sheet** on Reorder Planning (the migration importer).

## How to manage it

Open **[System Management → Automation](/system-management/automation)** and edit the row
named **Order inquiry to purchasing**.

* **Recipients** - pick **Specific users**, **By role**, or type an address under **External
  emails** and click **Add** (for example `purchasing@` and the CS manager's own address).
* **Cc the person who raised it** - keeps the CS admin who made the change on the thread.
* **One email, everyone on the thread** - sends a single mail with the first purchasing address
  in **To** and everyone else, including the person who raised it, in **Cc**, so a reply-all
  reaches the whole thread instead of landing back with only one recipient.
* **Enabled** - untick this to stop the mail once the manual email is retired. Nothing else
  needs to change.

## Parallel run

While the parallel run is on, CS keeps sending the manual mail as well. Compare the two on the
same thread and report any mismatch between them.

## Not yet built

Two cases still print as separate cancel-and-order lines rather than one combined line:

* Moving lines to a different sales order number (**CHANGE SO NO** across two sales orders).
* Replacing one item for another on a single line.

Both arrive as a CANCEL BALANCE line and an ORDER line, the same as any other item swap, until a
dedicated combined line is built.

## See also

* [Sales order changes after planning](sales-order-changes.md) - the in-app notification
  purchasing gets once a change is confirmed or amended, separate from this email.
* [Buy and borrow decisions on Fulfilment Planning](local-buy-and-borrow-source.md#undo-last-confirm)
  - undoing a Confirm, which sends purchasing its own "Order inquiry undone" email instead of
  this one.
* [Run a reorder plan](run-a-reorder-plan.md)
* [Upload the data a reorder plan is built from](upload-plan-data.md)
