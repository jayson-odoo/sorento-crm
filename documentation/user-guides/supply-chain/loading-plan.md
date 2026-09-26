# Supply Chain - Loading Plan

Use this flow to ask a supplier what to load into their next container: read what the Lines tab
suggests, search and sort it, and change the sales-order window a plan is worked out against.

## Where

Open **Procurement → Supply Chain → Loading Plan** (URL: `/scm/loading-plan`). The page is
titled **Loading Plan**.

## Start a plan

Click **Upload** in the list toolbar (the same button appears as the empty-state action on a
fresh list). The dialog is titled **Plan a container**:

* **Supplier** - required.
* **Sales orders needed** - **From** and **To** dates, both optional. The helper text reads
  "Empty = every open order counts." A sales order with no date of its own always counts,
  whichever dates you set. The **To** date cannot be before the **From** date - the dialog
  refuses with "The To date cannot be before the From date." rather than silently netting
  nothing.
* **Document** - **Stock list**, **Proforma invoice**, or **No file**. Picking a document shows
  a drop zone; picking **No file** does not, and skips straight to starting the plan from what
  is already on file for this supplier.

Once a **Stock list** or **Proforma invoice** file lands in the drop zone, a column-mapping panel
appears for it: two sample values from the sheet, the column's own header text (line breaks and
merged-cell splits kept, e.g. `外箱/木托尺寸 [2]`), and a field picker per column, with an
**Ignore** entry for columns that don't matter. Required fields are marked, and **Test** stays
disabled until every one has a field. If the guessed **Header row N** is wrong, the stepper beside
it nudges the row up or down and the columns re-read; when no row could be guessed the panel says
so and the stepper starts at row 1.

The first time this supplier's layout is seen, the panel is open. On a later upload of the same
layout, it is folded to "N of N columns mapped from saved layout" with a **Review** link, and it
opens again only when a column this supplier has never had before turns up.

With a document chosen, click **Test**. Test saves the column choices for this supplier and reads
the file in the same click, without writing anything else; then click **Confirm and start plan**.
With **No file**, click **Start plan** directly.

If the supplier's stock list merges a cell such as 型号 (model), 品名 (product name), 商标
(brand), 规格 (spec), a remark, or 体积 (cbm per unit) across several model rows, every row in
that block now reads the merged value, so **Supplier says** on the **Supplier codes** tab shows
the full description instead of only what the top row held. A merged quantity, such as packed or
unfinished stock, still counts once, on the first row of the block, not once per row it covers.

If a supplier writes a bare model number in 型号 (e.g. `8613`, `8066-PP`, `-7055`) instead of
our own product code, the reader builds our code from that row's 商标 (brand), 品名 (product
type), 型号 and 规格 (trap size) - for example SORENTO + 连体马桶 + 8613 + 150mm becomes
`SRTWC8613-150` - and that built code is what **Supplier says** shows and what gets matched. A
supplier who already writes our own codes is unaffected. If a word on the sheet isn't in the
**Stock list words** list yet (see the **Supplier codes** tab below), the row is left as the raw
text from the sheet and waits for a manual pick, the same as any other unmatched row.

## The four tabs

Once a plan is open, it has four tabs: **General** (metadata), **Lines** (the default), **Supplier codes**, and
**Sent**. The header shows the supplier's name and breadcrumb only.

## The General tab

The **General** tab (the first) holds the plan metadata as a card with five fields:

* **Status** - a badge reading **Planning**, **Sent**, or **Cancelled**.
* **Supplier** - the supplier's name (read-only).
* **Started** - the date and time the plan was created.
* **Plan window** - the sales-order date range the plan covers, or "every open order" when no dates are set.
* **Stock list** - the document the plan was started from (stock list, proforma invoice, or none).

## The Lines tab

### What the table lists

* **A plan started from a file** (a stock list or a proforma invoice, matched or not) lists
  only the products and sets that file's rows name. A product your company buys from this
  supplier that the file does not mention is not on the table, even if it has open sales-order
  need.
* **A plan started with No file** lists only the products bought from that supplier under
  **Product-Suppliers**.
* **A file whose codes have not been matched yet lists no rows at all**, until those codes are
  matched on the **Supplier codes** tab.
* **A product or set with no open sales-order need still appears in the same table**, at the
  bottom, muted and with no rank number, rather than in a separate collapsed line.

### Stat cards

Above the table, four cards read **Outstanding**, **On hand**, **From SPO**, and **To request**.
These summarise every row on the plan and are not affected by the **Search product** box below
(see "Search the table").

### Table / Schedule and search

The card heading reads "What to ask *\<supplier\>* to cover *\<window\>*" (or "... for" when the
window is every open order). Beside it, a **Table** / **Schedule** toggle switches between the
row list and a schedule view of the same rows. A **Search product** box sits next to the
toggle: typing filters the whole table and the Schedule view by product code,
product name, or set code (case-insensitive, matching anywhere in the text). The stat cards and
**Save (N)** are not affected by what is typed here. Clearing the box restores every row; no
match shows "No product matches" in the table body instead of rows.

### Columns

Every column header sorts by clicking it, except **Remarks** (a free-text field with no natural
order). **Suggested qty** is read-only: it always shows the system's own figure (the open need
minus on hand minus incoming SPO minus incoming packing list, never below zero), and hovering
the cell shows the working. **Requested qty**, right beside it, is where you type what to
actually ask the supplier for; sorting either column orders by what that column shows. Changing
Requested qty never changes Suggested qty, so the original suggestion stays visible. A cancelled
plan shows both columns as plain text.

* **Product** shows the item code once. The product name only appears underneath when it
  differs from the code - a row whose name and code are the same no longer repeats itself. A
  set row keeps its **Set** badge and the driver product's code underneath, labelled "Figures
  from *\<driver code\>*".
* **On hand**, **SPO**, and **Incoming PL** are the three pieces of supply behind a row:
  * **SPO** is shipping orders already on their way, at any active location.
  * **Incoming PL** is the part of a packing list not yet placed on an SPO. A shipment that is
    already fully on an SPO does not count here and does not appear in the **Incoming PL**
    lightbox - so a container is never counted once as SPO and again as Incoming PL.
  * **Total supply** is On hand + SPO + Incoming PL.
* Clicking the **SPO** or **Incoming PL** figure opens a lightbox listing the shipments behind
  it; the rows sum to exactly the number you clicked.
* **Need**, **Project**, and **Retail** are the open sales-order demand behind a row - Need is
  Project plus Retail together. Clicking any of them opens the sales orders behind the figure.
  Project counts open project lines before the cut-off, less what is already on a shipping
  order; a purchase order does not reduce it. The popup shows each line's Open quantity and the
  Balance still to ship.

### Viewing the uploaded file

If the plan was started from a stock list or proforma invoice, open the gear menu and pick
**View uploaded list** to preview it. On an Excel or CSV file, a **Search in sheet** box sits
above the preview table. Typing filters to the rows where any cell contains the text
(case-insensitive) and highlights the match; a count reads "N of M rows" while filtering, and
"No cell matches" shows if nothing does. The search covers the whole sheet, not only the first
rows the preview displays. Clearing the box restores the plain preview, and switching between
sheet tabs keeps the same search applied. A PDF or image file shows no search box.

## Change the sales orders needed window

Open the gear menu and pick **Change cut-off**. The dialog is titled **Change the sales order
cut-off**, with the note "The suggestion is worked out again against the new window." It carries
the same **Sales orders needed** **From** / **To** fields as **Plan a container**, with the same
"Empty = every open order counts." helper and the same guard against a **To** date before
**From**. Click **Save cut-off** to re-work the suggestion against the new window; this drops
any quantities you had typed but not yet saved, the same as **Refresh suggestion** does.

A plan started before this window existed keeps whatever **To** date it already had, with no
**From** date, until you set one.

## The Supplier codes tab

A **Stock list words** link sits in the tab's toolbar - it opens **System Management → Import
Column Mappings** to the word list a bare-model-number stock list is composed from (see "Start a
plan" above). Add a missing word there, then re-upload the file to have it compose.

A search box sits above the two tables (**Needs a decision** and **Remembered**). Type a code fragment,
part of a product name, or brand name to narrow both tables to matching rows. Several words narrow further
together - for example, typing `CWC 250` shows only rows matching both words. The table headings show the
filtered count while you are typing (e.g. "Needs a decision (12 of 61)"), and return to the plain total
when the box is cleared.

**Remembered table columns:**

* **Code** - the supplier's code.
* **Matched to** - the product or set code it has been matched to. **Dismissed** rows show "Dismissed".
* **When** - the date and time it was matched.
* **By** - the name (or email if no name is held) of the person who made the match.
* **Forget** - a button that starts a 5-second countdown to delete the match; click **Cancel** to keep it.

## What's captured

* The supplier, the document the plan was started from (or none), and the **Sales orders
  needed** window (**From** / **To**) the suggestion is worked out against.
* Any quantity or remark you type on a row, once you click **Save (N)**.

## See also

* [Run a reorder plan](run-a-reorder-plan.md)
* [Upload the data a reorder plan is built from](upload-plan-data.md)
* [Print the order summary](print-the-order-summary.md)
* [Import column mappings - Stock list words](../system-management/import-column-mappings.md)
