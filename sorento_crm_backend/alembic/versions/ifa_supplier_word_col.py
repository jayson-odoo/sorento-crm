"""Per-supplier word list for bare stock-list model codes (S2,
`PLAN-stock-list-bare-model-codes.md` D6/D7).

A supplier who writes a bare 型号 (`8613`, `-7055`) needs their brand and product-name words
translated into our own code prefixes before the matcher can bind them at all (see
`app/services/scm/supplier_code_composer.py`). The word list this reads is the existing
`import_field_alias` table, doc type `supplier_inventory_word` - one more admin surface on a
mechanism that already exists, not a new table.

`supplier_id` nullable: NULL is a SHARED row, answering for every supplier unless one of
their own overrides it (D6, R3).

SUPERSEDED (owner ruling A, 24 Sep 2026, review round 2 of `PLAN-import-column-mapper-
24sep.md`, migration `ifa_supplier_uniq`): this migration originally left
`uq_import_field_alias_triple` on `(doc_type, field, alias)` exactly as migration 311
created it, reasoning that 22+ other call sites matched it by name and that a second row
naming the SAME (field, alias) pair was never a distinct override, just a duplicate of an
answer that already existed. Ruling A overturned that: a second SUPPLIER's own row for a
header an earlier supplier had already claimed genuinely is a distinct answer - THEIR
answer, for THEIR file - and the shared, table-wide triple was blocking it outright
(R11). `ifa_supplier_uniq` replaces the plain triple with `uq_import_field_alias_shared`
(scoped to `supplier_id IS NULL`) and `uq_import_field_alias_supplier` (scoped per
supplier); every one of those other call sites was updated in the same lane to target the
shared index's own predicate (`fix(alembic): alias seeders target the shared partial
index...`) rather than left to 500 on "no unique or exclusion constraint matching the ON
CONFLICT specification".

D7 seeds exactly what the measured data states, as shared rows: the owner types the rest from
the new admin page. Six brand rows, not four - `CABANA`'s own single-letter spelling is `C`
(coincidentally the same letter as its token) and `MOCHA`'s is `M`, each its own alias row.
Not seeded (deliberately): `对冲` `高压` `上线` `薄边` `新` `飞机` `葫芦飞机` `大四方飞机`
`2078盆` `iB` `BRAVAT` and the BRAVAT basin kinds.

Revision ID: ifa_supplier_word_col
Revises: oicf_0001_board_rows_to_confirm
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "ifa_supplier_word_col"
down_revision = "oicf_0001_board_rows_to_confirm"
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


def seed_supplier_word_rows(bind) -> int:
    """The D7 seed (shared word rows). Returns rows inserted.

    Idempotent (`ON CONFLICT (doc_type, field, alias) WHERE supplier_id IS NULL DO NOTHING`,
    against the shared partial index migration `ifa_supplier_uniq` created - see the module
    docstring), and pulled out to its own function
    so `upgrade()` and `scripts/bootstrap_env.py` run the SAME code rather than two copies
    that drift, mirroring migration 311's own `seed_import_field_aliases`. A database built
    by `create_all` + stamp (CI, `bootstrap_env`) never executes a migration body, so a seed
    that lives only inside `upgrade()` is invisible there - exactly the gap 311's docstring
    names, and the reason `test_ac_w2_the_migration_seeds_exactly_the_d7_rows_shared` was
    red on a shard whose database was built that way.
    """
    inserted = 0
    for field, alias in _SEED:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, supplier_id)
                VALUES (:d, :f, :a, NULL)
                ON CONFLICT (doc_type, field, alias) WHERE supplier_id IS NULL DO NOTHING
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
        inserted += res.rowcount or 0
    return inserted


def upgrade() -> None:
    bind = op.get_bind()

    # `uq_import_field_alias_triple` (migration 311) is left exactly as it is here - see
    # the module docstring for why, and for how a LATER migration (`ifa_supplier_uniq`)
    # superseded that decision. Only the column and its FK are new in THIS migration.
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

    seed_supplier_word_rows(bind)


def downgrade() -> None:
    bind = op.get_bind()
    # Every row of this doc type, not only the seed - the admin page this migration exists
    # to feed may have written more rows since upgrade, and the column carrying their scope
    # is about to be dropped.
    bind.execute(
        sa.text("DELETE FROM import_field_alias WHERE doc_type = :d"), {"d": DOC_TYPE}
    )
    # `supplier_id` is a column on the WHOLE table, not scoped to this doc type. Any OTHER
    # doc type's row that ended up carrying one (nothing seeds this today, but the column
    # does not forbid it) is about to lose the column that scopes it - deleted rather than
    # silently unscoped.
    bind.execute(sa.text("DELETE FROM import_field_alias WHERE supplier_id IS NOT NULL"))

    op.drop_constraint(
        "fk_import_field_alias_supplier_id", "import_field_alias", type_="foreignkey"
    )
    op.drop_column("import_field_alias", "supplier_id")
