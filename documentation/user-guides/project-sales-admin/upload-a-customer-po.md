# Project Sales Admin - Upload a customer PO and match its products

When a customer sends a purchase order for a project, upload the document on the project and the system reads it for you: header, every line, and the handwriting on it. You then check the lines and confirm the PO.

A quotation is not needed. A PO can be uploaded on any project, with or without one.

## How products are matched

Each line the customer printed is matched to one of our catalogue products, in this order:

1. **Exact code.** The customer printed our product code as it is. The line is matched, nothing to do.
2. **A code this customer used before.** Every match a person confirms is remembered for that customer. The next PO from the same customer that prints the same code (or, when the line has no code, the same description) is matched straight away. Capital letters, spaces, dashes and `*` marks do not matter here: `SRTWT9121 -GM **` and `SRTWT9121-GM` are the same code. Any other difference does: `2.5MM` and `25MM` are different codes.
3. **Suggested.** Anything else is judged by the AI reader, which looks at the line's code and description the way a person would: it ignores brand words, the customer's own code prefix, stray spaces and marks such as `*`. It only picks from products that could fit: this project's quotation lines first, then the codes this customer used before, then the closest catalogue products. The line shows a **Suggested** pill until you accept it.

When two products fit equally (for example a code that exists in two finishes), nothing is picked. Open the product picker on that line: the possible products are listed first, choose one.

When a line's description names a variant (a size or finish, such as 35MM) that another product carries, the line is not matched to the printed code straight away, even when the code is exactly one of ours: both products are offered and you choose.

When no product fits, the line stays without a product. You can still confirm it if it has the customer's stock code.

## Accepting suggestions

Hover the **Suggested** pill to see why the line was suggested.

- **One line:** right-click the line and choose **Accept suggestion**.
- **All lines:** click **Accept all suggestions (N)** above the lines.
- **Check them first:** choose the **Suggested (N)** view to see only the lines with a suggestion.
- **Wrong suggestion:** pick the right product on that line instead. That choice is remembered for this customer.

## Cancelling lines

To cancel several lines at once, tick them (Shift-click a second box to tick every line in between), then click **Cancel lines (N)**. If the ticked lines are already cancelled, the button reads **Put back (N)** instead. Cancelled lines stay on the PO, marked cancelled, and are left out of the total. A line that could not be changed is named in the message that follows; the others still go through. To cancel or put back just one line, use the button at the end of that line.

## Which customer the codes belong to

Codes are remembered for the customer who issued the PO, when you click **Confirm this PO**: every product you accepted or picked on this PO is remembered then. Pick the issuer in **Issued by** at the top of the PO while it is waiting to be confirmed; type part of the party's name or code to find it. When nothing is picked there, the project's customer is used.

- If no issuer is picked and the project has no customer, **Confirm this PO** asks you to choose one under **Issued by** first.
- If the issuer you picked is not linked to a customer record, the PO is still confirmed, but you are told the codes were not remembered. Link that party to its customer under **Parties** so the next PO learns.

## Quantity

If the document shows an amount and a unit price but no quantity, and the amount divided by the price is a whole number, that number is filled in as a **Suggested** quantity. Otherwise the quantity stays empty for you to type.

When the document printed no amount for a line, the amount follows quantity times unit price as you type, and stays in step whenever either changes. An amount printed on the document, or one you type yourself, is never changed for you.

**Confirm this PO** refuses while any line still has an empty (or zero) quantity, or a suggestion nobody accepted, and names those lines.

## Totals

If the document prints a grand total, the system reads it and compares it with the sum of the lines: **Document total** shows the printed figure, and you are told when the lines come out above or below it.

If no printed total could be read, the figure is labelled **Sum of lines read** instead, and there is nothing to compare it with.
