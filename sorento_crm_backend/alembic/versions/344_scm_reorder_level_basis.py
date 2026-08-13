"""S10: the reorder level becomes a planning basis, beside the forecast one.

Three pieces of DDL, one idea: the number that decides a buy should be a number the buyer
owns, and the forecast should suggest it rather than replace it.

`warehouses.segment` splits dealer from project. Bare BRW is the dealer bin and BRW-BB /
BRW-IB are project bins, which means "last purchase cost" is two different numbers depending
on who is asking. The suffix convention seeds the column and is then never consulted again:
a client whose codes look nothing like Sorento's repoints rows instead of needing code, and
Sorento themselves can fix the one warehouse the convention gets wrong. Same reasoning as
`pool_warehouse_id` above it.

`scm.reorder_level` stores the level per (product, warehouse) alongside the suggestion it was
derived from. Both are kept, always: a suggestion that overwrites the stored level is the
engine deciding again, which is the exact behaviour that made the forecast basis unusable
(a 2-unit order producing a 15.933 buy). `suggestion_basis` carries the months it was built
from so the number is arguable rather than magic.

`scm.reorder_policy` gains the two dials the suggestion needs. They live on the policy, not in
settings, because the policy row is already the thing that resolves global -> product_class ->
sku, and a per-class cover period is the obvious next request.

Nothing here changes forecast behaviour. `policy_type` gains a third value; the two it already
had keep working untouched, so turning the industry-standard basis back on for a class or a
SKU is a policy row rather than a deploy.

Revision ID: 344_scm_reorder_level_basis
Revises: 343_supplier_notice
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "344_scm_reorder_level_basis"
down_revision = "343_supplier_notice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- dealer vs project -------------------------------------------------------------
    op.add_column(
        "warehouses",
        sa.Column("segment", sa.String(20), nullable=True),
    )
    # Seeded, not derived at read time. A code with no dash suffix is the site's own bin and
    # sells to dealers; every suffixed bin under it is project stock. Only fills what is
    # unset, so re-running never overwrites an admin's correction.
    op.execute(
        """
        UPDATE warehouses
           SET segment = CASE WHEN position('-' in warehouse_code) > 0
                              THEN 'project' ELSE 'dealer' END
         WHERE segment IS NULL
        """
    )
    op.create_index("ix_warehouses_segment", "warehouses", ["segment"])

    # --- the level the buyer owns ------------------------------------------------------
    op.create_table(
        "reorder_level",
        sa.Column("id", PG_UUID(as_uuid=False), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", PG_UUID(as_uuid=False), nullable=False),
        # NULL means the level applies to the product everywhere. A per-location row wins.
        sa.Column("warehouse_id", PG_UUID(as_uuid=False), nullable=True),
        # What the engine plans against. NULL is not the same as 0: 0 means "let it run to
        # nothing", NULL means nobody has set one and the item must not be planned silently.
        sa.Column("level", sa.Numeric(18, 4), nullable=True),
        # manual | accepted_suggestion. Records whether the buyer typed it or took ours.
        sa.Column("source", sa.String(30), nullable=True),
        # Kept beside the level, never merged into it.
        sa.Column("suggested_level", sa.Numeric(18, 4), nullable=True),
        sa.Column("suggested_at", sa.DateTime(timezone=False), nullable=True),
        # The months it came from, their average, and the cover applied - so the buyer can
        # disagree with the arithmetic rather than only with the answer.
        sa.Column("suggestion_basis", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("company_id", PG_UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        schema="scm",
    )
    # One row per (product, location, company). The COALESCE lets the product-wide row
    # (warehouse_id NULL) coexist with per-location rows instead of colliding with them:
    # a plain unique index would let NULLs duplicate freely, which is how a second
    # product-wide level would appear and be picked non-deterministically.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_scm_reorder_level_scope
            ON scm.reorder_level (
                product_id,
                COALESCE(warehouse_id, '00000000-0000-0000-0000-000000000000'::uuid),
                COALESCE(company_id, '00000000-0000-0000-0000-000000000000'::uuid)
            )
        """
    )
    op.create_index("ix_scm_reorder_level_product", "reorder_level",
                    ["product_id"], schema="scm")
    op.create_index("ix_scm_reorder_level_company", "reorder_level",
                    ["company_id"], schema="scm")

    # --- the dials the suggestion needs ------------------------------------------------
    # How many months of movement to study. Fixed at 3 by the business ("study 3 months
    # movement to set reorder level") but stored so it is arguable per class.
    op.add_column(
        "reorder_policy",
        sa.Column("level_study_months", sa.Integer, nullable=True,
                  server_default=sa.text("3")),
        schema="scm",
    )
    # How many months of that movement the level should cover.
    op.add_column(
        "reorder_policy",
        sa.Column("level_cover_months", sa.Numeric(6, 2), nullable=True,
                  server_default=sa.text("2")),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("reorder_policy", "level_cover_months", schema="scm")
    op.drop_column("reorder_policy", "level_study_months", schema="scm")
    op.drop_index("ix_scm_reorder_level_company", table_name="reorder_level", schema="scm")
    op.drop_index("ix_scm_reorder_level_product", table_name="reorder_level", schema="scm")
    op.execute("DROP INDEX IF EXISTS scm.uq_scm_reorder_level_scope")
    op.drop_table("reorder_level", schema="scm")
    op.drop_index("ix_warehouses_segment", table_name="warehouses")
    op.drop_column("warehouses", "segment")
