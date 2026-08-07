"""Read the AutoCount sales-order detail listing, and stop `Qty` meaning outstanding.

Revision ID: 338_scm_autocount_so_detail_aliases
Revises: 337_scm_on_order_from_spo
Create Date: 2026-08-07

The client's real export ("Project Sales Order 2020 - 2026.xlsx", 81,361 rows, 11,275
documents) carries this header row:

    Doc No | Doc Date | Delivery Date | Debtor Code | Debtor Name | Agent | Ref Doc No |
    Ref | Remark 1 | Item Code | Item Description | Location | Qty | Transfered Qty |
    Remaining Qty | Unit Price | Discount | Total (Inc) | Note

Two problems, and the second one is the dangerous one.

1. `Doc No`, `Doc Date`, `Debtor Name`, `Location` and `Note` resolve to nothing, so the
   file is rejected for a missing document number. Alias rows fix that: onboarding a header
   wording is data, not code.

2. **`Qty` in this layout is the quantity ORDERED, and the outstanding figure is a separate
   column.** The seeded alias already maps `QTY` to `qty_outstanding`, so the moment somebody
   added a `Doc No` alias and nothing else, every partly-delivered line would import with its
   ORDERED quantity read as outstanding: committed demand inflated, and every buy inflated
   with it, silently and stably, on a file that looked like it imported cleanly.

The fix mirrors what the purchase-order path has always done with `qty_received`: when the
file states a delivered quantity, the outstanding figure is the difference. So `QTY` keeps
its meaning as "the quantity column", and the new `qty_delivered` column nets it. A file
that carries only `QTY` is unaffected - it has no delivered column, so nothing is netted.

A third shape exists: the file states the remaining quantity outright. That gets its own
field (`qty_remaining`) rather than a second alias onto `qty_outstanding`, because two
headers mapping to one field resolve by column ORDER, and a file that happened to list the
remaining column first would silently go back to reading ORDERED as outstanding. The reader
chooses between the three shapes explicitly instead.

On this particular file every line is fully delivered, so netting takes every row to zero and
the reader skips them, which is the honest answer: the file states no outstanding demand.
"""
from alembic import op
import sqlalchemy as sa

revision = "338_scm_autocount_so_detail_aliases"
down_revision = "337_scm_on_order_from_spo"
branch_labels = None
depends_on = None


#: (doc_type, field, alias, locale). Aliases are stored normalised by the resolver, so the
#: casing here is only for reading.
_ALIASES = [
    # The AutoCount detail-listing wording, sales-order side.
    ("outstanding_so", "so_number", "DOC NO", "en"),
    ("outstanding_so", "so_date", "DOC DATE", "en"),
    ("outstanding_so", "customer_name", "DEBTOR NAME", "en"),
    ("outstanding_so", "stock_location", "LOCATION", "en"),
    ("outstanding_so", "remark", "NOTE", "en"),
    ("outstanding_so", "remark", "REMARK 1", "en"),
    # The netting column. Spelled both ways on purpose: AutoCount emits the single-R
    # "Transfered", and a hand-corrected export says "Transferred".
    ("outstanding_so", "qty_delivered", "TRANSFERED QTY", "en"),
    ("outstanding_so", "qty_delivered", "TRANSFERRED QTY", "en"),
    ("outstanding_so", "qty_delivered", "DELIVERED QTY", "en"),
    ("outstanding_so", "qty_delivered", "QTY DELIVERED", "en"),
    # The outstanding figure stated OUTRIGHT. Aliased to its own field rather than sharing
    # `qty_outstanding` with `QTY`: two headers mapping to one field resolves by column
    # order, so a file that happened to put the remaining column first would silently go
    # back to reading ORDERED as outstanding. The reader picks between them explicitly.
    ("outstanding_so", "qty_remaining", "REMAINING QTY", "en"),
    ("outstanding_so", "qty_remaining", "OUTSTANDING QTY", "en"),
    ("outstanding_so", "qty_remaining", "BALANCE QTY", "en"),
    ("outstanding_so", "qty_remaining", "QTY OUTSTANDING", "en"),
    # The same tool emits the purchase-order detail listing, so the shared wording is
    # onboarded here too rather than waiting for that file to be rejected once.
    ("outstanding_po", "po_number", "DOC NO", "en"),
    ("outstanding_po", "po_date", "DOC DATE", "en"),
    ("outstanding_po", "supplier_name", "CREDITOR NAME", "en"),
    ("outstanding_po", "stock_location", "LOCATION", "en"),
    ("outstanding_po", "qty_received", "TRANSFERED QTY", "en"),
    ("outstanding_po", "qty_received", "TRANSFERRED QTY", "en"),
    ("outstanding_po", "qty_remaining", "REMAINING QTY", "en"),
    ("outstanding_po", "qty_remaining", "OUTSTANDING QTY", "en"),
    ("outstanding_po", "qty_remaining", "BALANCE QTY", "en"),
]


def _rows():
    """The seed, as tuples. Importable so `bootstrap_env` can replay it on a create_all
    database, which never runs a migration body."""
    return list(_ALIASES)


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint, so a re-run
    on an already-seeded database is a no-op. Mirrors `seed_import_field_aliases` in
    migration 311 rather than restating its SQL differently."""
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
