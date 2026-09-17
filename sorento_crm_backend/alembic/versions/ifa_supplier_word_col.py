"""Per-supplier word list for bare stock-list model codes (S2,
`PLAN-stock-list-bare-model-codes.md` D6/D7).

A supplier who writes a bare 型号 (`8613`, `-7055`) needs their brand and product-name words
translated into our own code prefixes before the matcher can bind them at all (see
`app/services/scm/supplier_code_composer.py`). The word list this reads is the existing
`import_field_alias` table, doc type `supplier_inventory_word` - one more admin surface on a
mechanism that already exists, not a new table.

`supplier_id` nullable: NULL is a SHARED row, answering for every supplier unless one of
their own overrides it (D6, R3). The unique triple becomes a quadruple so the same word
(`SORENTO`) can carry both a shared answer and a supplier's own override without colliding -
Postgres treats NULLs as distinct by default, so two suppliers (or a supplier and the shared
row) may each hold a row for the same (doc_type, field, alias).

D7 seeds exactly what the measured data states, as shared rows: the owner types the rest from
the new admin page. Not seeded (deliberately): `对冲` `高压` `上线` `薄边` `新` `飞机`
`葫芦飞机` `大四方飞机` `2078盆` `iB` `BRAVAT` and the BRAVAT basin kinds.

Revision ID: ifa_supplier_word_col
Revises: undo_0002_seed_undone
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "ifa_supplier_word_col"
down_revision = "undo_0002_seed_undone"
branch_labels = None
depends_on = None

DOC_TYPE = "supplier_inventory_word"

#: (field, alias) - shared rows only, `supplier_id` NULL.
_SEED = [
    ("SRT", "SORENTO"),
    ("SRT", "S"),
    ("C", "CABANA"),
    ("M", "MOCHA"),
    ("WC", "连体马桶"),
    ("WC", "分体马桶"),
    ("WCX", "座头"),
    ("WCX", "分体座头"),
    ("WCY", "水箱"),
    ("WB", "盆"),
    ("WB", "盆小孔"),
    ("SC", "盖板"),
    ("P", "横排"),
]


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "import_field_alias",
        sa.Column("supplier_id", UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_import_field_alias_supplier_id",
        "import_field_alias",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_import_field_alias_triple", "import_field_alias", type_="unique"
    )
    op.create_unique_constraint(
        "uq_import_field_alias_triple",
        "import_field_alias",
        ["doc_type", "field", "alias", "supplier_id"],
    )

    for field, alias in _SEED:
        bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, supplier_id)
                VALUES (:d, :f, :a, NULL)
                ON CONFLICT (doc_type, field, alias, supplier_id) DO NOTHING
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for field, alias in _SEED:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias "
                "WHERE doc_type = :d AND field = :f AND alias = :a AND supplier_id IS NULL"
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )

    op.drop_constraint(
        "uq_import_field_alias_triple", "import_field_alias", type_="unique"
    )
    op.create_unique_constraint(
        "uq_import_field_alias_triple",
        "import_field_alias",
        ["doc_type", "field", "alias"],
    )
    op.drop_constraint(
        "fk_import_field_alias_supplier_id", "import_field_alias", type_="foreignkey"
    )
    op.drop_column("import_field_alias", "supplier_id")
