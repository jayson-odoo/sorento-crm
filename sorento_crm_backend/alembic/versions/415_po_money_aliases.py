"""The rest of the purchase book's money line, in the alias table.

Revision ID: 415_po_money_aliases
Revises: 414_po_line_money

Migration 414 gave `purchase_order_lines` a `discount` and a `line_total` to land in. Nothing
resolves a header to either one on the `outstanding_po` doc type, so without this revision the
columns exist and stay empty for ever: the AutoCount PO detail listing states both, the reader
already carries `discount` / `total_inc` in its extras for whichever doc type resolves them
(`outstanding_reader`), and the write binding already lists them - the alias row is the only
missing link.

    `DISCOUNT` / `DISC.`            -> discount
    `TOTAL (INC)` / `TOTAL` / `AMOUNT` -> total_inc

A bare `DISC` gets no row of its own: `AliasResolver` normalises a header by stripping
everything that is not alphanumeric, so `DISC.` and `DISC` are ONE key and the second row
would be a duplicate map entry rather than a second spelling covered.

`UOM` needs no row either - it has resolved for this doc type since migration 311; what it
lacked was the column, which 414 added.

Same insert style as migration 399, including the importable `seed` so `bootstrap_env` can
replay it on a create_all database, which never runs a migration body.
"""
from alembic import op
import sqlalchemy as sa

revision = "415_po_money_aliases"
down_revision = "414_po_line_money"
branch_labels = None
depends_on = None


#: (doc_type, field, alias, locale). Aliases are stored normalised by the resolver, so the
#: casing here is only for reading.
_ALIASES = [
    ("outstanding_po", "discount", "DISCOUNT", "en"),
    ("outstanding_po", "discount", "DISC.", "en"),
    ("outstanding_po", "total_inc", "TOTAL (INC)", "en"),
    ("outstanding_po", "total_inc", "TOTAL", "en"),
    ("outstanding_po", "total_inc", "AMOUNT", "en"),
]


def _rows():
    """The seed, as tuples. Importable so `bootstrap_env` can replay it on a create_all
    database, which never runs a migration body."""
    return list(_ALIASES)


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint, so a re-run
    on an already-seeded database is a no-op. Mirrors migration 399's `seed` rather than
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
