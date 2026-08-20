"""Read the captain's "PO & SPO outstanding.xlsx" export, whose money and quantity
columns spell differently from every `outstanding_po` header seeded so far.

Revision ID: 399_po_book_aliases
Revises: 397_so_class_from_agent
Create Date: 2026-08-20

The real file (3,632 lines) already resolves seven columns through migrations 311 and 338
(`Doc No`, `Doc Date`, `Transfered Qty`, `Remaining Qty`, `Location`, `Creditor Name`,
`Item Code`), but three were unmapped and both `qty_ordered` and `expected_date` are in
`_REQUIRED_COLUMNS` for `outstanding_po` (`app/services/scm/outstanding_reader.py`), so the
whole file was rejected before a single row was read:

    `Qty`            -> qty_ordered   (the netting column - `Transfered Qty` /
                                        `Remaining Qty` already resolve, so this is the
                                        ordered-quantity leg of the same three-shape rule
                                        migration 338 documented)
    `Delivery Date`  -> expected_date (the arrival date the plan needs)
    `Unit Price`     -> unit_cost     (an EXTRA the reader carries but does not require;
                                        confirmed non-empty on the real file, e.g. 9.5 on
                                        row 2)

Confirmed against the real export: 3,632 lines read, `unit_cost` fills, and the remaining
unmapped headers (`Loading Date`, `Agent`, `Ref`, `Description`, `Shipping Order`, `ICB
Name`, `FromSODocList`) are the same shape as migration 357's deliberately-ignored set -
resolved to nothing this book has a use for, not silently dropped.

**Caveat, not a regression.** This export carries no `CREDITOR CODE` column, only
`CREDITOR NAME` (migration 338). `outstanding_import_service` resolves the purchase order's
`supplier_id` from `creditor_code` alone (`party_fk="supplier_id", party_code="creditor_code"`
in `_BINDINGS`); `supplier_name` is read and shown as a label but never used to resolve a
row. So purchase orders written from this file carry no `supplier_id` and display the
creditor NAME only - existing binding behaviour for any `outstanding_po` file that omits
the code column, not something this revision changes or could fix without inventing a
name-to-code match this file gives no grounds for.
"""
from alembic import op
import sqlalchemy as sa

revision = "399_po_book_aliases"
down_revision = "397_so_class_from_agent"
branch_labels = None
depends_on = None


#: (doc_type, field, alias, locale). Aliases are stored normalised by the resolver, so the
#: casing here is only for reading.
_ALIASES = [
    ("outstanding_po", "qty_ordered", "QTY", "en"),
    ("outstanding_po", "expected_date", "DELIVERY DATE", "en"),
    ("outstanding_po", "unit_cost", "UNIT PRICE", "en"),
]


def _rows():
    """The seed, as tuples. Importable so `bootstrap_env` can replay it on a create_all
    database, which never runs a migration body."""
    return list(_ALIASES)


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint, so a re-run
    on an already-seeded database is a no-op. Mirrors migration 338's `seed` rather than
    restating its SQL differently."""
    inserted = 0
    for doc_type, field, alias, locale in _ALIASES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, locale)
                VALUES (:d, :f, :a, :l)
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": doc_type, "f": field, "a": alias, "l": locale},
        )
        inserted += res.rowcount or 0
    return inserted


def upgrade() -> None:
    seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for doc_type, field, alias, _locale in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias "
                "WHERE doc_type = :d AND field = :f AND alias = :a"
            ),
            {"d": doc_type, "f": field, "a": alias},
        )
