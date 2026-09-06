"""Customer identity (D13): the (code, name) pair, not the code alone.

The same Sage/AutoCount debtor code legitimately hosts more than one customer
name (e.g. "300-D093" for both "Deluxe Home Center (KTN)" and "Deluxe Home
Center AC (I)"), so a code-only match can silently adopt or rename the wrong
row. `order_service.CustomerService.create_customer` matches on
`lower(btrim(code)), lower(btrim(name))` - the same key as the
`uq_customers_company_code_name_lower` composite unique index - and the
masters ingest (`master_ingest_service.py`) uses this same function so the two
can never drift apart.
"""
from __future__ import annotations


def customer_identity(code: str, name: str) -> tuple[str, str]:
    """Lower-trimmed (code, name) pair used to match/adopt a customer row."""
    return ((code or "").strip().lower(), (name or "").strip().lower())
