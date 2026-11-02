# Price products in a series, and take a product out of one

Use this when a series needs a selling price, a maximum discount, or a product removed.

## Steps

1. Open **Project Sales**, then **Configuration**, then **Series**, and open the series.
2. In the products table, type a **Selling price** and, if a discount is allowed, a **Max discount %** on the product's row. The row saves when you move to another row or select the tick, and **Saved** confirms it. The **Minimum price** column shows the result.
3. To add a product, select **Add a product**, pick it in the **Product** cell, then type its numbers. A new row with no product says **Pick a product to save this row** and is not saved until you pick one.
4. To take a product out of the series, select the bin on its row, then **Delete**. The row disappears.
5. To put a removed product back, select **Add a product** and pick it again, or load it with **Load the sheet**.

## What's captured

* **Minimum price** is the lowest price a quotation line may carry for this series: the selling price less the max discount. A selling price with no max discount allows no discount, so the minimum price is the selling price itself. With no selling price the series sets none, and the company's minimum price rules apply.
* A removed product is no longer in the series: a quotation line with it reads **Non-standard**, and the series no longer prices it. Products the series' brand and category would list stay out until you add them back.
* A saved row's product is fixed. To quote a different product, add it as its own row.

## Good to know

* Searching or changing page saves your edited rows first. A row that cannot save (for example a max discount above 100) keeps the list where it is and a message names the row: fix it or remove it, then search again.
* Closing or reloading the page with an unsaved edit asks before leaving.

## See also

* [Work a project quotation](../project-sales-rep/work-a-project-quotation.md)
* [Set the standard terms and conditions for quotations](./set-standard-quotation-terms.md)
