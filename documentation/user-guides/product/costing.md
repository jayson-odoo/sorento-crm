# Costing

Use **Costing** to see what every product costs to land, what it sells at, and what a party (a dealer or a
business partner such as Bath Plus) pays, all in one grid: the costing workbook, inside the CRM. Management
only: you need the **View Product Cost** permission to open it, and **Manage party costing** to change
mark-ups, transport or cost methods.

Open it from the sidebar: **Products > Products > Costing**.

## How a figure is worked out

For each product, on the **As of** date:

1. **Cost**: the supplier's unit cost in force that day, in the supplier's currency (which supplier depends on
   the **Cost method**, below).
2. **Landing (RM)** = cost converted to MYR at the exchange rate in force that day, times the **SST** factor,
   then the **Transport**: either *Add* a flat RM amount per unit (e.g. + RM 8.00 for ceramics) or *Multiply*
   by a factor (e.g. x 1.07 for taps). A product with no transport rule adds nothing and says **No transport
   rule**.
3. **Company standard** (the default view): **Final (RM)** is the **List price (AutoCount)** and **Mark-up** is
   the mark-up that list price achieves on the landing cost. Nothing here is ever sent to AutoCount.
4. **A party's view**: **Final (RM)** = landing x (1 + that party's **Mark-up**), and **Margin** is the gap
   between the list price and that final price.

A value the system cannot work out is never shown as 0. You see the reason instead: **No cost**, **Set a
primary supplier**, **Selected supplier no longer linked**, **No rate for CNY on 11/11/2026** (the currency
and date it needed), or **No list price** (the product's AutoCount list price is empty or 0).

### Cost method

Which supplier cost a product uses:

* **Primary supplier** (the company default): the supplier ticked as primary on the product.
* **Selected supplier**: a supplier you name for that product.
* **Average of supplier prices**: the average landing cost of every linked supplier that has a cost and a
  rate on the date; any supplier left out is named.
* **Last PO price**: the latest purchase order line for the product, converted at the rate on the PO's date.

A product's own method wins over the party's, which wins over the company default. A method that finds
nothing says so; it never quietly falls back to another one.

## Steps: read the costing

1. Open **Products > Products > Costing**. The toolbar holds the party select (**Company standard**), the
   **As of** date, **Search code or name**, **Filters** and **Columns**.
2. Click any column header to sort by it (click again to reverse). Empty values stay at the bottom.
3. **Filters**: pick one or more **Category**, **Brand**, **Cost method**, or **Cost** (**Has cost** /
   **No cost**). Each active filter shows as a chip above the grid; clear a chip to drop that filter.
4. Change **As of** to see the figures with the costs and rates in force on another day.
5. Click a row's arrow to see each linked supplier: **Supplier**, **Primary**, **Lead time**, **Cost**,
   **Landing (RM)**, **Final (RM)** and **Margin if bought here** (in Company standard: **Mark-up if bought
   here**).
6. The **Supplier** column shows the supplier's name; hover it for the name and code.

The address bar keeps your sort, search, page and filters, so a reload or a shared link opens the same view.

## Steps: a party's costing (dealer or business partner)

A party is an existing customer (debtor) record; there is nothing new to create. Bath Plus, for example, is
**RELATED - BATHPLUS SDN BHD (304-R017)**.

1. In the toolbar's party select, type part of the name or the code (e.g. **bathplus** or **304-R017**) and
   pick the party. The chips show **Party mark-up**, **Cost method**, **Rates as of** and **Products**.
2. If the header shows **Set up costing**, click it and enter **Party mark-up (%)** and, if you want, a
   **Cost method**, then save.
3. Open **Actions** and choose **Add products**. Tick the products (filter by category or brand, or select
   all) and add them. Products already on the party are marked **Already added**.
4. To take a product off the party, open its row menu and choose **Remove from party**. A countdown with
   **Cancel** appears; there is no confirmation dialog.
5. Clear the party select to go back to **Company standard**.

## Steps: change mark-up, transport or cost method

1. Click **Edit** in the header. The grid stays the same; the **Mark-up**, **Transport** and **Cost method**
   cells become inputs.
2. **Mark-up** (party view only): type the row's own mark-up. Clear it to go back to the party's mark-up. A
   value set on the row is marked **Set on this row**.
3. **Transport**: pick **Add** or **Multiply** and enter the value, or clear it to use the category rule.
4. **Cost method**: pick a method (with **Selected supplier**, also pick the supplier), or clear it to use
   the **Company default**.
5. Landing, Final and Margin update as you type. Click **Save** once to keep every change, or **Cancel** to
   discard them.

Transport and cost method belong to the product, so a change there applies to every party.

## Steps: settings

Click **Settings** (top right). The **Costing settings** dialog has three tabs, each a sortable, searchable
grid:

* **Exchange rates**: one row per currency per **Effective from** date, showing **Units per MYR 1**, **MYR
  per unit** and **Status** (**Scheduled**, **In force**, **Past**). To add one, pick the **Currency** (only
  currencies used on supplier costs or purchase orders are offered), pick **Effective from**, enter the rate
  as **Units per MYR 1** (e.g. 1.6 for CNY) or **MYR per unit**, and click **Add rate**. The rate used for a
  day is the latest one on or before it. A second rate for the same currency and date is refused; delete
  that row first.
* **SST and method**: the **SST factor** (1.1 = 10%) and the **Default cost method**.
* **Transport by category**: each category's **Mode** (**Add** or **Multiply**) and **Value**.

The supply chain planner uses the same exchange rates.

## Export

Open **Actions** (or click **Export**) to download the grid as Excel: the current view (Company standard or
the party) with your filters, every product rather than one page, numbers as numbers, a **Supplier name**
column, and a title row naming the view and the **As of** date.

## What's captured

* Every change to a mark-up, transport rule, cost method, party profile, exchange rate or SST is recorded:
  who, when, and the old and new value. Open a row's menu and choose **History** to see that row's changes
  (date and time in Malaysia time).
* Nothing on this page changes the product's list price or is sent to AutoCount.

## How you'll be notified

On screen only: a toast after **Save**, **Add products**, **Add rate** or a removal. No email or WhatsApp.

## See also

* [Manage products](./manage-products.md): suppliers, primary supplier and costs on a product.
* [Product categories and brands](./product-categories-and-brands.md).
