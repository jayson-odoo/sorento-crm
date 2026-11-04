"""The list price a quotation fixture product carries when the test is not about discounts.

PS-QUOTE-RULES (#2096): a line priced below its default price (the series selling price, else
the product's list price snapshot) is a discount, and a quotation carrying one cannot be issued
until a manager approves it (``project_quotation_service.line_default_price``, gate
``project_quotation_approval_service.assert_issuable``).

Tests that issue a quotation to check something else (the PDF, the workbook, the spec sheet,
the frozen photos, the customer's answer, the export queue) price their lines for their own
arithmetic, zero-priced components included. Their products list at nothing, so no line they
price is a discount and Issue goes through on its own merits, as it does for a full-price quote.
The rule itself is exercised with real prices in ``test_ps_quote_rules.py`` and
``test_project_quotation_approval*.py``, which do not use this constant.
"""

UNDISCOUNTED_LIST_PRICE = "0.00"
