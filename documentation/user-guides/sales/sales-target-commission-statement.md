# Sales targets: commission earned and the commission statement

Use this to see what a target has earned so far, which account the commission pays to, and to
send stakeholders a statement they can cross-check.

## Steps

1. Open **Sales**, **Targets**, then a target.
2. The card above the tabs shows:
   - **Commission earned to date (RM)**: the commission of the periods that have ended.
   - **Current period commission (RM)**: the period running today, with its dates. It can still
     change, so it is not part of the earned figure.
   - **Pays to** (dealer targets): the account the commission is paid to. The CRM does not record
     whether it has been paid.
3. The **Periods** tab lists each period's **Target**, **Achieved**, **%**, **Tier reached**,
   **Rate**, **Commission (RM)** and, on a dealer target, **Pays to**, then a **Total** row.
   **Rate** shows the reached tier's rate and its Additional, e.g. **A/C I 6.00% + 1.00%**. Click
   **Tier reached** or **Rate** to see that period's tiers with the reached one highlighted.
   **Columns** hides or shows columns.
4. The **Accounts** tab (dealer targets) lists each counted account's sales in every period that
   has started, then the **Period total** with the period's commission and the account it pays
   to. The running period reads **Period total (so far)**. Click a period to see its tiers.
5. To export, open the gear menu and choose **Export commission statement**. For several targets
   at once, tick them in the **Targets** list and choose **Commission statement (N)** (at most
   50 targets per file).
6. The statement is prepared in the background: open **My Downloads** (the download icon at the
   top of the page) and download the file once it reads ready.

## Tiers and the Additional

On the **Commission** tab each tier has a threshold, a rate and an **Additional**: a % on top of
the rate, or a fixed RM (pick **%** or **RM** beside it in Edit). **Period** narrows the list to
the periods you pick.

Additional pays only on its own tier; set it on each tier where it should apply.

Example: tiers 60,000 at 5% + 1%, 75,000 at 6% + 1%, 85,000 at 7% + 1%. Sales of 76,793.92 reach
75,000, so the period pays 6% (4,607.64) plus its own 1% (767.94) = 5,375.58. The 60,000 tier's
Additional does not also pay.

## How you'll be notified

A toast says the statement is being prepared; the file appears in **My Downloads**.

## What the statement holds

An Excel workbook:

- **Summary**: one row per target with its dealer or agent, what it counts, **Pays to**, the
  commission earned to date and the current period so far.
- One sheet per target, named by its number:
  - the period summary (the same figures as the **Periods** tab);
  - per period, the **Tier table used** (each tier's threshold and rate, and which were reached);
  - per period, the **Documents counted in Achieved**: document no., date, account and the amount
    it added to that period. The documents add up to the period's Achieved to the cent.

Dates read dd/mm/yyyy and money has 2 decimals. The figures are worked out when you export, so a
statement is a snapshot of that moment.

## What "Achieved" counts

- **Invoiced**: invoices, cash sales and debit notes, less credit notes, net of tax, each on its
  own document date. In the statement a credit note is a negative amount.
- **Ordered**: each sales order's line totals, including tax, on the sales order date.
- **Delivered**: the delivered share of each line's total, including tax, on the delivery order
  date. A document's amount is the part delivered inside that period.
- Cancelled sales orders, cancelled lines and consignments never count.
- A dealer target counts the sales orders of its accounts, whoever the agent was.

## See also

- Sales targets: what counts.
