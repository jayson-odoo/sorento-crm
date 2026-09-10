"""One-time backfill for S1's PI numbering change (AC-A4, migration 499).

`scm.proforma_invoice.pi_number` used to be the supplier's own text (or the derived
`PI-<file stem>-<block>` fallback); S1 makes it OURS, a monthly running number, and moves
the supplier's own reference to the new `supplier_ref` column. Every row that existed
before this migration needs both: its old `pi_number` sorted into `supplier_ref` (or
dropped, when it is the derived form) and a freshly minted `pi_number` in its place.

Run PER COMPANY, in `(created_at, id)` order, with the month key taken from `created_at` -
the same ordering and the same monthly-reset shape `NumberingService` gives a live upload,
so a backfilled row reads exactly as if it had been numbered on the day it arrived. Each
company's numbering rule (`app.services.numbering_defaults.seed_proforma_invoice_rule`) is
created if it does not exist yet, then left with `next_value`/`last_reset_key` at the state
the backfill's own last row for that company put it in - so the FIRST live upload after
this migration continues the same series.

`connection` is anything with `.execute(clause, params)` - an Alembic bind or the caller's
own `Session.connection()` (tests pass the latter, so the backfill runs inside the same
transaction as the rows it is backfilling). Reads and writes go through the ORM's OWN
`Table` objects (`ProformaInvoice.__table__`, `DocumentNumberingRule.__table__`) rather
than hand-written `scm.proforma_invoice` SQL text: a bare table name in a `text()` clause
resolves through the connection's `search_path`, which `tests/_pg_fixture.py`'s scratch
schema pins to its OWN copies - but a name QUALIFIED with the schema, as the real
`scm.proforma_invoice` name is, bypasses that pin entirely and would silently write to the
real database from inside a test. Core `Table` constructs go through SQLAlchemy's own
`schema_translate_map`, the same mechanism every ORM query in this test suite already
relies on, so the identical code is correct against both the scratch schema and the real
one the Alembic migration runs against.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select, update

from app.models.numbering import DocumentNumberingRule
from app.models.scm import ProformaInvoice
from app.services.numbering_defaults import (
    PROFORMA_INVOICE_DOC_TYPE,
    seed_proforma_invoice_rule,
)

#: The derived name S1 retires: `PI-<file stem>-<block>`. Matched against the OLD
#: `pi_number` to decide whether it is worth keeping as `supplier_ref` - a stem can itself
#: contain digits and dashes, so this is deliberately loose (anything, then a trailing
#: `-<digits>`) rather than trying to reconstruct the exact stem/index split.
_DERIVED_PATTERN = re.compile(r"^PI-.+-\d+$")


def backfill_pi_numbers(connection) -> dict[str, int]:
    """Mint every existing row its own `pi_number`, per company, oldest first.

    Returns `{"<company_id>:<yyyy-mm>": count}` - the minted count per company per month,
    for the migration to log (and the coder to report).
    """
    table = ProformaInvoice.__table__
    rows = connection.execute(
        select(table.c.id, table.c.company_id, table.c.pi_number, table.c.created_at)
        .order_by(table.c.company_id, table.c.created_at, table.c.id)
    ).all()

    by_company: dict[str, list] = defaultdict(list)
    for row in rows:
        by_company[str(row.company_id) if row.company_id else ""].append(row)

    minted: dict[str, int] = {}
    for company_id, company_rows in by_company.items():
        seed_proforma_invoice_rule(connection, company_id=company_id or None)
        next_value = 1
        last_reset_key: str | None = None
        for row in company_rows:
            created_at = row.created_at
            month_key = f"{created_at.year:04d}-{created_at.month:02d}"
            if month_key != last_reset_key:
                next_value = 1
                last_reset_key = month_key

            old_number = (row.pi_number or "").strip()
            supplier_ref = None if _DERIVED_PATTERN.match(old_number) else (old_number or None)
            new_number = f"PI-{created_at.year % 100:02d}{created_at.month:02d}-{next_value:03d}"

            connection.execute(
                update(table)
                .where(table.c.id == row.id)
                .values(supplier_ref=supplier_ref, pi_number=new_number)
            )
            key = f"{company_id or 'none'}:{month_key}"
            minted[key] = minted.get(key, 0) + 1
            next_value += 1

        rule_table = DocumentNumberingRule.__table__
        connection.execute(
            update(rule_table)
            .where(
                rule_table.c.doc_type == PROFORMA_INVOICE_DOC_TYPE,
                rule_table.c.company_id == (company_id or None),
            )
            .values(next_value=next_value, last_reset_key=last_reset_key)
        )

    return minted
