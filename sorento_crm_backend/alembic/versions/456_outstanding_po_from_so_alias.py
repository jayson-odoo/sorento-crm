"""`FromSODocList` resolves on the OUTSTANDING purchase book too (G12/D2, 2 Sep 2026).

Revision ID: 456_outstanding_from_so
Revises: 455_claim_crm_supply
Create Date: 2026-09-02

The captain's "PO & SPO outstanding.xlsx" is the same AutoCount export shape the history
book is, `FromSODocList` column and all - and that column is the ONLY place either file
states the SO<->PO pairing per LINE. The history channel has read it since migration 358
(`po_spo_history`) and writes a `po_history` claim from it; the outstanding channel read
the identical column, did not resolve it, and therefore wrote nothing.

That is the gap G12's project-bin lock landed on. The lock refuses an unattributed
project-bin line to the automatic pass, and the outstanding book is the feed that carries
most of the attribution - so without this the buyer's weekly re-upload could never seed a
single dedication and the count of unclaimed bin lines could never fall.

Aliases only. `outstanding_reader` carries the value onto the row's extras and
`outstanding_import_service` writes the claim (`source = 'po_upload'`, the value the
table's own CHECK constraint has reserved since migration 334).

`Loading Date` rides along resolved-and-not-read for the same reason migration 358 gives:
a blank `FromSODocList` beside a Loading Date remark such as "REPLACE BACK" means the line
belongs to somebody else's order (captain, 2 Sep 2026), so the column is recognised rather
than reported as unmapped, and reading it is a decision nobody has taken yet.
"""
import sqlalchemy as sa
from alembic import op

revision = "456_outstanding_from_so"
down_revision = "455_claim_crm_supply"
branch_labels = None
depends_on = None

DOC_TYPE = "outstanding_po"

_ALIASES = [
    ("so_number", "FromSODocList"),
    ("so_number", "From SO Doc List"),
    ("loading_date", "Loading Date"),
]


def _rows():
    """The seed, as tuples. Importable so `scripts/bootstrap_env` can replay it on a
    create_all database, which never runs a migration body."""
    return list(_ALIASES)


def seed(bind) -> int:
    inserted = 0
    for field, alias in _ALIASES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, locale)
                VALUES (:d, :f, :a, 'en')
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
        inserted += res.rowcount or 0
    return inserted


def upgrade() -> None:
    seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for field, alias in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias WHERE doc_type = :d AND field = :f "
                "AND alias = :a"
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
