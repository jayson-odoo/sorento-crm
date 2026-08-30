"""The proforma line carries its weights, and the reader knows what the supplier calls them.

Revision ID: 435_proforma_line_weights
Revises: 434_notice_shared_token
Create Date: 2026-08-27

The PI detail page now edits its lines as a draft and writes them back in one PUT, and the
line grid states what the supplier stated - including the two columns that had nowhere to
land: `净重` and `毛重`. Both real documents print them beside the volume, the reader threw
them away, and the packing list downstream had to be re-read to answer "what does this
container weigh".

* `scm.proforma_invoice_line.net_weight` / `gross_weight`, NUMERIC(15,4), NULL. Null rather
  than 0 for the same reason `cbm_per_unit` is: an unstated weight and a weightless line are
  different answers to "what does this weigh", and only one of them is honest.
* The `净重` / `毛重` / `N.W.` / `G.W.` header aliases on the `proforma_invoice` doc type.
  They exist for `packing_list` (migration 311) and not for this channel, so without them the
  columns would exist and every upload would leave them empty for ever - the same gap 428
  closed for the volume columns.

The columns are ALSO declared on the model (`app/models/scm.py`), so a create_all database is
the same shape as a migrated one, and `seed()` is importable for the same reason 375's and
428's are: a CI database is built with create_all and never runs a migration body.
"""
import sqlalchemy as sa
from alembic import op

revision = "435_proforma_line_weights"
down_revision = "434_notice_shared_token"
branch_labels = None
depends_on = None

DOC_TYPE = "proforma_invoice"

#: (field, alias). Only the weight columns: everything else this channel reads was seeded by
#: 375 and 428. `净重` / `毛重` are migration 311's `packing_list` spellings; `N.W.` / `G.W.`
#: are what the English-headed invoices print. One row per NORMALISED key - `normalize_header`
#: drops the dots, so `N.W.` already covers `NW` and a second row would be the same key twice.
_ALIASES = [
    ("net_weight", "净重"),
    # The pre-loading list prints the unit inside the header ("净重\n(kg)"), and
    # `normalize_header` KEEPS the unit's letters - `净重(kg)` folds to `净重kg`, which is a
    # different key from `净重`. Both spellings are seeded, or the column the real file
    # actually uses resolves to nothing. `总净重(kg)` is the line TOTAL and stays unmapped:
    # it folds to `总净重kg`, a third key, and it is not what this column holds.
    ("net_weight", "净重(kg)"),
    ("net_weight", "N.W."),
    ("net_weight", "NET WEIGHT"),
    ("gross_weight", "毛重"),
    ("gross_weight", "毛重(kg)"),
    ("gross_weight", "G.W."),
    ("gross_weight", "GROSS WEIGHT"),
]


def seed(bind) -> int:
    """Insert the weight aliases. Idempotent, importable - mirrors migration 428's `seed`."""
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
    op.add_column(
        "proforma_invoice_line",
        sa.Column("net_weight", sa.Numeric(15, 4), nullable=True),
        schema="scm",
    )
    op.add_column(
        "proforma_invoice_line",
        sa.Column("gross_weight", sa.Numeric(15, 4), nullable=True),
        schema="scm",
    )
    seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for field, alias in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias "
                "WHERE doc_type = :d AND field = :f AND alias = :a"
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
    op.drop_column("proforma_invoice_line", "gross_weight", schema="scm")
    op.drop_column("proforma_invoice_line", "net_weight", schema="scm")
