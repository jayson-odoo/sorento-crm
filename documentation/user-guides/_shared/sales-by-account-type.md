# Sales - Search sales by account type

A customer's **account type** is the debtor type AutoCount holds for that customer ledger, such as SORENTO, CERAMIC or CABANA. It is the same split as the columns of AutoCount's sales report by account, so use it when you compare with that report.

Account type is not the item's brand. An invoice to a CABANA account can carry items of several brands, and a CABANA brand item can be sold on another account, so the two figures differ.

## Where to find it

Open **Sales > Sales & outstanding**. Every tab (Invoiced, Delivered, Ordered, Undelivered orders, Pending delivery, Unpaid invoices) has an **Account type** filter.

## Sales for one account type

1. Pick the tab, usually **Invoiced** to compare with AutoCount.
2. Set the **Period** and, if you need it, the **Sales agent**.
3. Choose one or more types in **Account type**.

The filter adds to the others. Choosing a brand and an account type gives that brand's sales on that account only.

## Sales split by account type

Open **Configure summary** and choose **Account type** for the rows. You get one row per type, and the rows add up to all sales. The blank row is customers AutoCount gives no type, and any sale with no customer linked.

## Ask the chatbot

You can ask the same thing in chat, on any sales or outstanding question.

- **By number:** "AGENT A sales for account type 4 in January", "account 4" or "A/C IV". The reply shows the account the way you asked: "Account type: 4".
- **By name:** "ceramic sales in January", when that word is an account type and not a brand.
- **Split:** "sales by account type in January" gives one row per type.

### When the bot asks "brand or account type?"

Some words are both a brand and an account type, such as CABANA. For those the bot asks "Cabana: brand or account type?". Answer either one and it runs your question as you asked it, without asking the agent or period again. The two answers give different figures.

To skip the question, say which you mean: "cabana account" or "cabana debtor type". "Cabana brand" says which too, but the bot may still ask; just answer "brand".

If you give a word and a number together, there is no question:

- "cabana sales for account 4", when 4 is the CABANA account, is that account.
- "cabana on account type 3" is the CABANA brand on account 3.

### What the numbers mean

A number means the type most of that company's customers tagged with it carry, for example `[A/C IV]` at the end of the customer name. If the bot does not know a number, it says so and lists the ones it has. If it says "Account types are not loaded from AutoCount yet", the types have not reached the CRM. A customer's own account, such as "ZZT TRADING a/c 3", still means that customer's ledger.

Customers asking on WhatsApp cannot ask by account type.

## Why does my number look different

- **You filtered by brand, not account type.** Check which filter you set. A brand figure will not tally with AutoCount's report by account.
- **The customer's type changed.** A sale counts under the customer's account type today, not the one it had on the invoice date.
- **The Account type filter has no choices.** The types have not reached the CRM from AutoCount yet. Nothing is wrong with the sales themselves.
