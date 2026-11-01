# Sales - Search sales by account type

A customer's **account type** is the debtor type AutoCount holds for that customer ledger, such as SORENTO, CERAMIC or CABANA. It is the same split as the columns of AutoCount's sales report by account. Use it when you want a figure to tally with that report.

Account type is not the item's brand. An invoice to a CABANA account can carry items of several brands, and a CABANA brand item can be sold on another account, so the two figures differ.

## Where to find it

Open **Sales > Sales & outstanding**. Every tab (Invoiced, Delivered, Ordered, Undelivered orders, Pending delivery, Unpaid invoices) has an **Account type** filter.

## Sales for one account type

1. Pick the tab, usually **Invoiced** to compare with AutoCount.
2. Set the **Period** and, if you need it, the **Sales agent**.
3. Choose one or more types in **Account type**.

The filter adds to the others. Choosing a brand and an account type gives that brand's sales on that account only.

## Sales split by account type

Open **Configure summary** and choose **Account type** for the rows. You get one row per type, and the rows add up to all sales. A blank row is customers AutoCount gives no type.

## Ask the AI assistant

The AI assistant reads the same figures. You can name the account by its number or its type: "account type 4", "A/C IV", or "CABANA account". The reply shows the account the way you asked.

If you name a number the customers do not carry, the assistant says so and lists the account types it does have.

## Why does my number look different

- **You filtered by brand, not account type.** Check which filter you set. A brand figure will not tally with AutoCount's report by account.
- **The customer's type changed.** A sale counts under the customer's account type today, not the one it had on the invoice date.
- **The account types are not loaded.** If you see "Account types are not loaded from AutoCount yet", the types have not reached the CRM. Nothing is wrong with the sales themselves.
- **The number means the type most of that number's ledgers carry.** "Account type 4" finds every customer of that type, including a ledger whose own name has no account number on it.
