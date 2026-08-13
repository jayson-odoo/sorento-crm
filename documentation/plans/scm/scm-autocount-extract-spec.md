# AutoCount extract specification - outstanding SO and outstanding PO

> For Josephine and Joey. Needed **before day 1** of the SCM purchasing and fulfilment build.
> Two reports, exported to Excel. Column order does not matter and header wording does not have
> to match exactly - the system resolves headers through an alias table, and both English and
> Chinese headers are supported. What matters is that each listed **fact** is present in a
> column of its own.
>
> One row per order line. Do not merge cells and do not repeat header rows mid-sheet.

## Report 1 - Outstanding Sales Orders

Every sales-order line not yet fully delivered.

| Fact | Why it is needed | Have it today? |
|---|---|---|
| SO number | Identifies the order across weekly uploads | yes (S/O NO) |
| SO date | Ranking and reporting | yes (SO DATE) |
| **Debtor code** | Resolves the customer, and through the customer whether this is project or retail demand. Without it the system cannot tell a project order from a retail one, and fulfilment priority is decided by that. | **no - please add** |
| Customer or project name | Shown on screen so a planner recognises the row | yes (PROJECT/CUSTOMER) |
| Item code | Resolves the product | yes (ITEM CODE) |
| **UOM** | A quantity without a unit cannot be compared to stock or to a purchase order | **no - please add** |
| Outstanding quantity | The quantity still to deliver | yes (QTY) - **please confirm this is outstanding, not originally ordered** |
| Delivery date | Per line, not per order. This is what the whole plan is built on. | yes (DELIVERY DATE) |
| Stock location | Which location the line is to be delivered from | yes (STOCK LOCATION) |
| Remark | Carried through for context | yes (REMARK) |

**Scope.** Please export the **whole open book** in one file where possible. A single-project
extract is also accepted, but it must be uploaded with its scope declared, otherwise the system
would read the absence of every other project as those orders having been delivered.

## Report 2 - Outstanding Purchase Orders

Every purchase-order line not yet fully received. This report is needed by **both** halves of
the build: the buying plan needs it to know what is already on order, and the container loading
plan needs it to know what is outstanding with each supplier.

| Fact | Why it is needed |
|---|---|
| PO number | Identifies the order, and is the default ranking key for loading and allocation |
| PO date | Ranking, and the fallback fairness tie-break |
| Creditor code | Resolves the supplier |
| Supplier name | Shown on screen |
| Item code | Resolves the product |
| UOM | As above |
| Quantity ordered | Together with received, gives what is still incoming |
| Quantity received | If your report gives outstanding quantity instead, that is fine - say which it is |
| Expected arrival date or ETA | Without it the system cannot tell whether incoming stock arrives in time for an order. A blank is acceptable and will be flagged; a wrong date is not. |
| Stock location | Which location the PO is destined for |
| Unit cost | Answers "what did this last cost from this supplier" without a phone call |
| Currency | Costs are not comparable across currencies |
| PO status | So cancelled and closed lines can be excluded |

## Two questions we need answered, not exported

1. **Is the SO quantity column outstanding or originally ordered?** Both are usable; guessing
   wrong makes every number wrong.
2. **Which stock locations hold stock that is not available to sell?** We can see `BRW-HOLD`
   holds 27,925 units, `WH3-HOLD` 11,605, `BRW-REWO` 13,044, `BRW-RSV` 6,949. We intend to treat
   `-HOLD`, `-REWO`, `-RSV`, `-DFCT`, `-DISP` and `-CLR` as **not** available for planning, and
   everything else as available. Please confirm, and tell us specifically about `-IB`, `-IR`,
   `-BB`, `-NTC`, `-SMC`, `-HP` and `SPARE/P`, where we are guessing from the name. Counting held
   stock as available makes the plan buy too little; excluding the wrong location makes it buy
   too much.

## What we do with a bad file

Nothing silently. Every upload shows what will change before anything is saved - how many lines
are new, how many changed quantity, how many changed date, how many will be closed - and waits
for confirmation. Rows we cannot resolve are reported with the reason and the original file is
kept, so a bad export is a five-minute correction rather than a day of unpicking.
