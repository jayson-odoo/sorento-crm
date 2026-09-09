# Supply Chain - Run a reorder plan

Use this flow to launch a reorder plan, read what it suggests, decide what to buy, and confirm.
This is the day-to-day planning journey; for loading the underlying sales orders, purchase
orders, order inquiry sheet and reorder levels the plan is built from, see
[Upload the data a reorder plan is built from](upload-plan-data.md).

## Where

Open **[Supply Chain → Planning → Reorder Planning](/scm/reorder)** (URL: `/scm/reorder`). The
page is titled **Reorder Planning**.

## Start a plan

Click **Start Plan** in the list toolbar. The dialog is titled **Start Plan**:

* **Sales orders needed** - **From** and **To** dates, both optional. The helper text reads
  "Empty = every open order counts." A sales order with no date of its own always counts,
  whichever dates you set. Leaving both blank plans every open order, same as today.
* **Warehouses** - optional; leave empty to plan every warehouse.
* **Products** - optional; leave empty to plan every product.

Click **Start Plan** to launch. A product with **Exclude from reorder planning** switched on
(see [Manage products](../product/manage-products.md#exclude-a-product-from-reorder-planning))
never appears in the run, even when you name it directly in Products.

## The Header tab

Once a plan is open, it has two tabs: **Lines** and **Header**.

The **Header** tab shows the Plan card with:

* **Sales orders needed** - reads as "01/01/2025 to 31/10/2026", "up to 31/10/2026", "from
  01/01/2025", or "every open order", matching whatever you set at Start Plan.
* **Warehouses** and **Products** - the scope the run was launched with.

**Edit** is the primary button on the Plan card. Editing lets you change the From and To dates
(and warehouses/products) and **Re-plan**: this launches a new run rather than editing the old
one in place, and carries your decisions across, the same as before.

## The Lines tab

The **Lines** tab is where you read and decide the plan.

### Filters

The **Filters** popover holds the filter builder only - there are no separate preset dropdowns
for status, decided, price answer, suggested action or level answer. Add conditions on any
field, including **Rec type** and **Decision state** ("Already decided" / "Still to decide"),
to slice the grid.

### Money and prices

Every money figure on the grid and in the row panel renders with exactly two decimals, for
example "RM 9,070,460.00" or "RM 0.00".

Expand a row's panel to see **Last price**. It reads in the currency the last purchase was
actually made in, for example "CNY 110.00" - never relabelled to MYR. If nothing has ever been
purchased, it falls back to the line's own currency.

Under **Line cost**, if the last purchase's currency has no MYR exchange rate on file, the
panel shows "No MYR rate for CNY, set it under SCM policies" (a link) instead of a bare dash.
Follow the link to **[Supply Chain → Policies](/scm/policies)**, **Exchange rates** tab, to add
the missing rate.

## Deciding a row

Expand a row's panel to decide it.

* **Product health** arrives with a suggestion already selected: a **Dead** product
  pre-selects **Discontinue**; anything else (fast moving, slow moving, or no history)
  pre-selects **Keep selling**. Change it if you disagree, then **Save**.
* The suggested reorder level (**ADU** in the row panel) is now built from retail deliveries
  only - shipments out of a dealer-pool warehouse. A one-off shipment out of a project bin no
  longer lifts the suggested level; the terms line reads "ADU 1.911 / day (retail)" so you can
  tell it was computed this way.
* The Project figure on a row carries an info icon; open it to see every source behind the
  number, including Order Inquiry Form rows (tagged **OI form**) that have not yet been linked
  to a supply decision. The total always matches the row's Project figure.

## Confirm

**Confirm (N)** only buys rows you decided - either you saved a decision on the row, or you
used **Use suggestion**. Rows nobody touched are never bought, however strong the engine's own
suggestion. If nothing has been decided yet, the button reads **Confirm (0)** and is disabled
with the tooltip "Decide at least one row first".

## See also

* [Upload the data a reorder plan is built from](upload-plan-data.md)
* [Print the order summary](print-the-order-summary.md)
* [Manage products](../product/manage-products.md)
