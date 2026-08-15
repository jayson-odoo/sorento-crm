"""Who an order is for, in one place.

Three screens ask the same question about the same row - the demand behind a plan line,
who bought the product on the trend, and the orders behind one of those customers - and
they have to give the same answer, spelled the same way. So the fallback lives here once:

    the customer we hold  ->  the debtor code the document printed  ->  neither

The literal `Unnamed customer` this replaces was wrong twice. 2,546 of 2,548 uploaded
sales orders had no `customer_id` yet carried a debtor code on the face of the document,
so "unnamed" hid an attribution the buyer could act on; and for an order that names
nobody at all, "unnamed" dresses a fact about the order up as missing data.

The KEY is the same three cases in machine form, because a row the reader can see has to
be a row the reader can open: the customer id, `debtor:<code>`, or `none`.
"""
from __future__ import annotations

from typing import Any

#: Assumes the query joins `sales_orders so` and `LEFT JOIN customers c`, and that the join
#: is company-guarded (`CUSTOMER_JOIN_ON`): the label is printed on a plan screen, so a
#: customers row belonging to another company would name that company's buyer on this
#: company's order.
CUSTOMER_LABEL_SQL = (
    "COALESCE(c.customer_name, 'Debtor ' || so.debtor_code, 'No customer on order')"
)

#: The join condition that guard lives in. One constant, because a query that took the
#: label without it would print exactly what the label exists to prevent.
CUSTOMER_JOIN_ON = "c.id = so.customer_id AND c.company_id = so.company_id"

#: The same identity, keyed. Grouped on rather than the label so two customers sharing a
#: name stay two rows, and so the drill can name exactly the one that was clicked.
#:
#: Keyed off the JOINED row (`c.id`), not off `so.customer_id`, so the key says the same
#: thing the label does: an order pointing at another company's customer reads as its debtor
#: code on both sides rather than printing one identity and opening another.
CUSTOMER_KEY_SQL = (
    "CASE WHEN c.id IS NOT NULL THEN c.id::text "
    "     WHEN so.debtor_code IS NOT NULL THEN 'debtor:' || so.debtor_code "
    "     ELSE 'none' END"
)

#: What the FE sends for an order that names neither a customer nor a debtor code.
NO_CUSTOMER_KEY = "none"

_DEBTOR_PREFIX = "debtor:"

#: "This order resolves to no customer of its own company" - the same test the guarded join
#: makes, written for a query that does not join `customers` at all. Without it the drill
#: selects a different set from the row it was opened from, and the lines stop adding up to
#: the quantity printed above them.
_NO_CUSTOMER_SQL = (
    "NOT EXISTS (SELECT 1 FROM customers c2 "
    "            WHERE c2.id = so.customer_id AND c2.company_id = so.company_id)"
)


def customer_key_filter(key: str) -> tuple[str, dict[str, Any]]:
    """The WHERE fragment selecting the orders behind one Who-bought-it row.

    Deliberately not `CUSTOMER_KEY_SQL = :key`: an equality against a CASE cannot use the
    `customer_id` index, and the three cases are three different predicates anyway. An
    unrecognised key is treated as a customer id - it either matches a row or it does not,
    which is the honest outcome for a key nobody issued.
    """
    if key == NO_CUSTOMER_KEY:
        return f"({_NO_CUSTOMER_SQL} AND so.debtor_code IS NULL)", {}
    if key.startswith(_DEBTOR_PREFIX):
        return (
            f"({_NO_CUSTOMER_SQL} AND so.debtor_code = :ckey)",
            {"ckey": key[len(_DEBTOR_PREFIX):]},
        )
    return "so.customer_id::text = :ckey", {"ckey": key}
