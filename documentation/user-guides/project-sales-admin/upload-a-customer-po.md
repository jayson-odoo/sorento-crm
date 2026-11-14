# Project Sales Admin - Upload a customer PO and match its products

When a customer sends a purchase order for a project, upload the document on the project and the system reads it for you: header, every line, and the handwriting on it. You then check the lines and confirm the PO.

A quotation is not needed. A PO can be uploaded on any project, with or without one.

## How products are matched

Each line the customer printed is matched to one of our catalogue products, in this order:

1. **Exact code.** The customer printed our product code as it is. The line is matched, nothing to do.
2. **A code this customer used before.** Every match a person confirms is remembered for that customer. The next PO from the same customer that prints the same code (or, when the line has no code, the same description) is matched straight away.
3. **Suggested.** Anything else is judged by the AI reader, which looks at the line's code and description the way a person would: it ignores brand words, the customer's own code prefix, stray spaces and marks such as `*`. It only picks from products that could fit: this project's quotation lines first, then the codes this customer used before, then the closest catalogue products. The line shows a **Suggested** pill until you accept it.

When two products fit equally (for example a code that exists in two finishes), nothing is picked. Open the product picker on that line: the possible products are listed first, choose one.

When no product fits, the line stays without a product. You can still confirm it if it has the customer's stock code.

## Accepting suggestions

- **One line:** right-click the line and choose **Accept suggestion**.
- **All lines:** click **Accept all suggestions (N)** above the lines.
- **Check them first:** choose the **Suggested (N)** view to see only the lines with a suggestion.
- **Wrong suggestion:** pick the right product on that line instead. That choice is remembered for this customer.

## Quantity

If the document shows an amount and a unit price but no quantity, and the amount divided by the price is a whole number, that number is filled in as a **Suggested** quantity. Otherwise the quantity stays empty for you to type.

**Confirm this PO** refuses while any line still has an empty (or zero) quantity, or a suggestion nobody accepted, and names those lines.

## Totals

If the document prints a grand total, the system reads it and compares it with the sum of the lines: **Document total** shows the printed figure, and you are told when the lines come out above or below it.

If no printed total could be read, the figure is labelled **Sum of lines read** instead, and there is nothing to compare it with.
