"""Per-supplier word list for bare stock-list model codes (S2,
`PLAN-stock-list-bare-model-codes.md` D6/D7).

A supplier who writes a bare 型号 (`8613`, `-7055`) needs their brand and product-name words
translated into our own code prefixes before the matcher can bind them at all (see
`app/services/scm/supplier_code_composer.py`). The word list this reads is the existing
`import_field_alias` table, doc type `supplier_inventory_word` - one more admin surface on a
mechanism that already exists, not a new table.

`supplier_id` nullable: NULL is a SHARED row, answering for every supplier unless one of
their own overrides it (D6, R3). Review round 1, item 3: a plain `(doc_type, field, alias,
supplier_id)` unique constraint does NOT do what D6 needs, because Postgres's default
"NULLs are distinct" rule means the SAME shared row (`SORENTO`, `supplier_id` NULL) could be
inserted twice without ever violating that constraint - two NULLs never collide. The rule
this table actually wants is stricter for a shared row (one row per word, full stop) and
looser for a scoped row (one row PER SUPPLIER per word) - two different uniqueness scopes,
which is exactly what two PARTIAL unique indexes express and a single four-column constraint
cannot:

  - `uq_import_field_alias_shared` on `(doc_type, field, alias)` WHERE `supplier_id IS NULL`
  - `uq_import_field_alias_scoped` on `(doc_type, field, alias, supplier_id)`
    WHERE `supplier_id IS NOT NULL`

D7 seeds exactly what the measured data states, as shared rows: the owner types the rest from
the new admin page. Six brand rows, not four - `CABANA`'s own single-letter spelling is `C`
(coincidentally the same letter as its token) and `MOCHA`'s is `M`, each its own alias row.
Not seeded (deliberately): `对冲` `高压` `上线` `薄边` `新` `飞机` `葫芦飞机` `大四方飞机`
`2078盆` `iB` `BRAVAT` and the BRAVAT basin kinds.

Revision ID: ifa_supplier_word_col
Revises: oioh_0001_one_header_per_so
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "ifa_supplier_word_col"
down_revision = "oioh_0001_one_header_per_so"
branch_labels = None
depends_on = None

DOC_TYPE = "supplier_inventory_word"

#: (field, alias) - shared rows only, `supplier_id` NULL.
_SEED = [
    ("SRT", "SORENTO"),
    ("SRT", "S"),
    ("C", "CABANA"),
    ("C", "C"),
    ("M", "MOCHA"),
    ("M", "M"),
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
    op.create_index(
        "uq_import_field_alias_shared",
        "import_field_alias",
        ["doc_type", "field", "alias"],
        unique=True,
        postgresql_where=sa.text("supplier_id IS NULL"),
    )
    op.create_index(
        "uq_import_field_alias_scoped",
        "import_field_alias",
        ["doc_type", "field", "alias", "supplier_id"],
        unique=True,
        postgresql_where=sa.text("supplier_id IS NOT NULL"),
    )

    for field, alias in _SEED:
        bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, supplier_id)
                SELECT :d, :f, :a, NULL
                WHERE NOT EXISTS (
                    SELECT 1 FROM import_field_alias
                    WHERE doc_type = :d AND field = :f AND alias = :a
                      AND supplier_id IS NULL
                )
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )


def downgrade() -> None:
    bind = op.get_bind()
    # Every row of this doc type, not only the seed - review round 1, item 3. The admin page
    # this migration exists to feed may have written supplier-scoped rows since upgrade, and
    # the column carrying them is about to be dropped; leaving them orphaned under the old
    # triple constraint (which none of these rows were even inserted under) is worse than a
    # downgrade that removes what it introduced, full stop.
    bind.execute(
        sa.text("DELETE FROM import_field_alias WHERE doc_type = :d"), {"d": DOC_TYPE}
    )
    # `supplier_id` is a column on the WHOLE table, not scoped to this doc type - review
    # round 2, item 5. Any OTHER doc type's row that ended up carrying one (nothing seeds
    # this today, but the column does not forbid it) is about to lose the column that scopes
    # it; restoring the old (doc_type, field, alias) triple next could then collide two rows
    # that used to be distinct only by supplier. Deleted rather than silently unscoped.
    bind.execute(sa.text("DELETE FROM import_field_alias WHERE supplier_id IS NOT NULL"))

    op.drop_index("uq_import_field_alias_scoped", table_name="import_field_alias")
    op.drop_index("uq_import_field_alias_shared", table_name="import_field_alias")
    op.create_unique_constraint(
        "uq_import_field_alias_triple",
        "import_field_alias",
        ["doc_type", "field", "alias"],
    )
    op.drop_constraint(
        "fk_import_field_alias_supplier_id", "import_field_alias", type_="foreignkey"
    )
    op.drop_column("import_field_alias", "supplier_id")
