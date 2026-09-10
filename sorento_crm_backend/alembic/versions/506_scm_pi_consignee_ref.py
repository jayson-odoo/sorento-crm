"""The consignee on the proforma invoice header, and the labels that state it (ruling 28).

A supplier's document header carries four facts the packing list needs: the container, the
seal, the forwarder's SO (`提单号`, held in `bl_ref` - the column name is historical, the 6
Sep ruling put that value in the SO field) and WHO IT IS BILLED TO. The first three already
have a home on `scm.proforma_invoice`; this adds the fourth.

The aliases are the Jinbaichuan labels the readers could not place: its consignee cell says
`Customer Name 客户名：` where every other document says `客户`, and its seal says `封条号`
where Jiexia says `封签号`. Both readers get both spellings - the sheet is a COMBINED file
and is read as an invoice and as a packing list.

Revision ID: 506_scm_pi_consignee_ref
Revises: 505_import_field_aliases_perms
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "506_scm_pi_consignee_ref"
down_revision = "505_import_field_aliases_perms"
branch_labels = None
depends_on = None

#: (doc_type, field, alias, locale)
_ALIASES = [
    ("proforma_invoice", "consignee", "Customer Name 客户名", "zh"),
    ("packing_list", "consignee", "Customer Name 客户名", "zh"),
    ("proforma_invoice", "consignee", "客户名", "zh"),
    ("packing_list", "consignee", "客户名", "zh"),
    ("proforma_invoice", "consignee", "Customer Name", "en"),
    ("packing_list", "consignee", "Customer Name", "en"),
    ("proforma_invoice", "seal_no", "封条号", "zh"),
    ("packing_list", "seal_no", "封条号", "zh"),
]


def seed(bind) -> None:
    """Exposed for the tests, which build their schema from the migrations by hand."""
    for doc_type, field, alias, locale in _ALIASES:
        bind.execute(
            sa.text(
                "INSERT INTO import_field_alias (doc_type, field, alias, locale) "
                "VALUES (:d, :f, :a, :l) "
                "ON CONFLICT (doc_type, field, alias) DO NOTHING"
            ),
            {"d": doc_type, "f": field, "a": alias, "l": locale},
        )


def upgrade() -> None:
    op.add_column(
        "proforma_invoice",
        sa.Column("consignee_ref", sa.String(150), nullable=True),
        schema="scm",
    )
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
    op.drop_column("proforma_invoice", "consignee_ref", schema="scm")
