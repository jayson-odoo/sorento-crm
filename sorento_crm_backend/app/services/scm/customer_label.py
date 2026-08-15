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

#: Assumes the query joins `sales_orders so` and `LEFT JOIN customers c`.
CUSTOMER_LABEL_SQL = (
    "COALESCE(c.customer_name, 'Debtor ' || so.debtor_code, 'No customer on order')"
)

#: The same identity, keyed. Grouped on rather than the label so two customers sharing a
#: name stay two rows, and so the drill can name exactly the one that was clicked.
CUSTOMER_KEY_SQL = (
    "CASE WHEN so.customer_id IS NOT NULL THEN so.customer_id::text "
    "     WHEN so.debtor_code IS NOT NULL THEN 'debtor:' || so.debtor_code "
    "     ELSE 'none' END"
)

#: What the FE sends for an order that names neither a customer nor a debtor code.
NO_CUSTOMER_KEY = "none"

_DEBTOR_PREFIX = "debtor:"


def customer_key_filter(key: str) -> tuple[str, dict[str, Any]]:
    """The WHERE fragment selecting the orders behind one Who-bought-it row.

    Deliberately not `CUSTOMER_KEY_SQL = :key`: an equality against a CASE cannot use the
    `customer_id` index, and the three cases are three different predicates anyway. An
    unrecognised key is treated as a customer id - it either matches a row or it does not,
    which is the honest outcome for a key nobody issued.
    """
    if key == NO_CUSTOMER_KEY:
        return "(so.customer_id IS NULL AND so.debtor_code IS NULL)", {}
    if key.startswith(_DEBTOR_PREFIX):
        return (
            "(so.customer_id IS NULL AND so.debtor_code = :ckey)",
            {"ckey": key[len(_DEBTOR_PREFIX):]},
        )
    return "so.customer_id::text = :ckey", {"ckey": key}
