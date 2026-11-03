# Inventory - Read the stock position

Use **Inventory > Stock position** to see, for every item and every supplier, the stock per location, what is
incoming, what is still owed, and monthly sales, on one sheet.

## Steps

1. Open **Inventory**, then **Stock position**.
2. Search by item code or description, or open the filters to narrow by **Supplier**, **Brand** or **Warehouse**.
3. Click any column header to sort the whole list by it (sorting runs over every item, not just the page you see).
4. Use the **Columns** menu to choose which columns show. Your choice is saved for you and comes back next time.
5. Click an item code to open **Stock status** for that item with the documents behind each figure.
6. Click **Export to Excel** to download the same list, sorted and filtered as on screen.

## The two totals follow the columns you show

| Column | Adds up |
| --- | --- |
| **Total stock** | every location column you show (BRW, DC1 and so on) + **Incoming BRW**, if shown |
| **Total incoming** | **Incoming BRW** + **Incoming (Project)**, whichever you show |

* Hide a location column and Total stock drops that location's quantity on every row straight away. Show it again
  and it comes back.
* Hide **Incoming BRW** and it leaves both totals; hide **Incoming (Project)** and it leaves Total incoming.
* Hide every location column and Total stock is just Incoming BRW (0 if that is hidden too).
* Hover over the **Total stock** or **Total incoming** header to see exactly which columns it adds up, for example
  "Sum of BRW, DC1, Incoming BRW".
* Hiding any other column (Supplier, Outstanding PO, Monthly sales and so on) does not change either total.
* Sorting by a total sorts by the total you see. Changing which columns show takes you back to page 1.

## What's captured

Nothing: the page only reads. The quantities are the ones **Stock status** shows for each item.

## Export

**Export to Excel** writes the location and incoming columns you show, in the screen's order, and the same totals
as the screen, so each row of the workbook adds up to its own Total stock and Total incoming.
