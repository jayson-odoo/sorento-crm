"""Per-supplier word list for bare stock-list model codes (S2,
`PLAN-stock-list-bare-model-codes.md` D6/D7).

A supplier who writes a bare 型号 (`8613`, `-7055`) needs their brand and product-name words
translated into our own code prefixes before the matcher can bind them at all (see
`app/services/scm/supplier_code_composer.py`). The word list this reads is the existing
`import_field_alias` table, doc type `supplier_inventory_word` - one more admin surface on a
mechanism that already exists, not a new table.

`supplier_id` nullable: NULL is a SHARED row, answering for every supplier unless one of
their own overrides it (D6, R3). Review round 3: `uq_import_field_alias_triple` on
`(doc_type, field, alias)` stays EXACTLY as migration 311 created it - not touched, not
replaced with a per-supplier variant. Two reasons landed on that ruling:

  - 22 other call sites (every seeder, `scripts/bootstrap_env.py`, 9+ scm tests) `INSERT ...
    ON CONFLICT (doc_type, field, alias) DO NOTHING` against this exact constraint by name.
    Rounds 1-2 replaced it with two partial unique indexes, and Postgres has no unique index
    matching that column list once the plain triple is gone - every one of those sites 500s
    with "no unique or exclusion constraint matching the ON CONFLICT specification" (CI red
    on #1000). Rewriting 23 sites for one migration's own column is not this migration's
    call to make.
  - It is also the RIGHT rule, not just the safe one: an override changes the WORD'S TOKEN
    for one supplier (`对冲` normally unmapped; DAFUYUAN's own row says `SH`) - a different
    `field` value for the same `alias`, which is a DIFFERENT (doc_type, field, alias) triple
    and was never blocked. What the triple correctly refuses is a SECOND row naming the
    SAME (field, alias) pair that a shared or another supplier's row already names - that
    mapping already exists, and duplicating it (scoped or not) is not an override, it is
    exactly the answer "use the existing row" restated as a new row.

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

    Idempotent (`ON CONFLICT (doc_type, field, alias) DO NOTHING`, against the triple
    migration 311 created - see the module docstring), and pulled out to its own function
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
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
        inserted += res.rowcount or 0
    return inserted


def upgrade() -> None:
    bind = op.get_bind()

    # `uq_import_field_alias_triple` (migration 311) is left exactly as it is - see the
    # module docstring for why. Only the column and its FK are new here.
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

    # `scm.supplier_inventory.model_no` (owner feedback round 5): the 型号 exactly as the
    # supplier wrote it, alongside `item_code` which may be a COMPOSED guess for a bare
    # model - "Supplier says" has to lead with what the sheet printed, not our derivation.
    op.add_column(
        "supplier_inventory",
        sa.Column("model_no", sa.String(length=120), nullable=True),
        schema="scm",
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

    op.drop_column("supplier_inventory", "model_no", schema="scm")

    op.drop_constraint(
        "fk_import_field_alias_supplier_id", "import_field_alias", type_="foreignkey"
    )
    op.drop_column("import_field_alias", "supplier_id")
