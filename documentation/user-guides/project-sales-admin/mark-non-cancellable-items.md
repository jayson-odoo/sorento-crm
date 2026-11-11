# Mark items Non-cancellable (bathtubs and other bulky items)

Use this when an item is ordered specially for a project and cannot be cancelled or reduced once
the sales order is confirmed, for example a bathtub that Sorento cannot store.

## Steps

### On a series

1. Open **Project Sales**, then **Configuration**, then **Series**, and open the series.
2. In **Non-cancellable categories**, pick the categories whose items are Non-cancellable. Only
   the series' own **Categories** can be picked. A category also covers the categories under it.
   Select **Save changes**.
3. To set one model differently, scroll the products table right to the **Non-cancellable**
   column and pick **Yes** or **No** on its row. Clear the cell to follow the category again. The
   **Applies** column shows a **Non-cancellable** badge on every product that ends up
   Non-cancellable.
4. In the **Sets** table, tick **Non-cancellable** on a set to mark the set itself. A set is also
   Non-cancellable when any product in it is.

### Company-wide, for items outside a series

1. Open **Project Sales**, then **Configuration**, then **Non-cancellable Items**.
2. Select **Add item**. Pick the **Type** (**Product** or **Category**), the product or category,
   leave **Non-cancellable: Yes** on (or switch it to No to exempt one model from its category),
   add **Notes** if you like, and select **Add item**.
3. To change a row, select it, edit, and select **Save**. To remove it, select the bin on its row;
   the row is removed when the countdown ends (**Cancel** stops it).

## What's captured

* Which one wins: the series' own answer for the model, then the series' category, then the
  company product row, then the company category row (the nearest category up the tree).
* A quotation line records whether it is Non-cancellable when the line is saved, or when
  **Recheck alerts** is run on a proposal still being priced. Changing the setting later does
  not change a proposal already sent to the customer.
* Every change to the setting is kept in the history.

## How it shows

* On the proposal, a Non-cancellable line carries a **Non-cancellable** badge under its
  description.
* In the PDF, the customer's sign page and the Excel export, a **REMARK** column (just before
  GRAND TOTAL) reads **Non-cancellable** on those lines. A proposal with no such line prints
  without the column. Nothing is added to the terms.

## See also

* [Cancel or reduce a Non-cancellable line (manager override)](../project-sales-manager/override-a-non-cancellable-line.md)
* [Price products in a series, and take a product out of one](./price-products-in-a-series.md)
* [Work a project quotation](../project-sales-rep/work-a-project-quotation.md)
