"""F11: the supplier's own spelling of a product code, remembered.

Revision ID: 431_supplier_code_alias
Revises: 429_scm_pi_link_qty
Create Date: 2026-08-27

R16 (captain, 27 Aug). A supplier writes their own code and it is not ours: the tokens come
in another order (`SRTWC8357-RL-300` for our `SRTWC8357-300-RL`), a trap size is spelled out
that our code omits because it is the default (`SRTWC8357-RL-250` for `SRTWC8357-RL`), a
suffix is glued on (`SRTWC286-SH-250UF`). On the uploaded JINBAICHUAN list that left 79
codes bound to nothing.

A ladder resolves them (`app/services/scm/supplier_code_matcher.py`) and THIS table is where
the answer is kept - every automatic bind and every human "Match to product" pick, per
supplier. Consulted first next time, so the ladder is never re-run against a code somebody
has already ruled on, and a wrong automatic bind can be corrected once rather than being
re-derived on every upload.

`source` says who decided (`auto` / `manual`) and `matched_by` says which rung of the ladder
did it, because an automatic bind has to be visible AS an automatic bind - a screen that
cannot tell the two apart cannot ask anyone to check the guess.

Unique on (company, supplier, supplier_code): one supplier's spelling means one product.
`company_id` is COALESCEd in the index for the same reason every other owned table here
does it - the column is nullable on legacy rows, and Postgres treats NULLs as distinct, so
an unstamped row would slip past the lock.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "431_supplier_code_alias"
down_revision = "429_scm_pi_link_qty"
branch_labels = None
depends_on = None

_NIL_COMPANY = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.create_table(
        "supplier_product_code_alias",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id", name="fk_scm_supplier_code_alias_company_id"),
            nullable=True,
        ),
        sa.Column(
            "supplier_id",
            UUID(as_uuid=False),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        #: The supplier's spelling, verbatim. Never normalised on the way in: it is what
        #: their file says, and the matcher normalises when it compares.
        sa.Column("supplier_code", sa.String(120), nullable=False),
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(10), nullable=False, server_default=sa.text("'auto'")),
        #: Which rung bound it - `exact`, `separator`, `token_set`, `size_drop`, `manual`.
        sa.Column("matched_by", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), server_default=sa.func.now(),
            nullable=False,
        ),
        schema="scm",
    )
    op.create_check_constraint(
        "ck_scm_supplier_code_alias_source",
        "supplier_product_code_alias",
        "source IN ('auto', 'manual')",
        schema="scm",
    )
    op.create_index(
        "ix_scm_supplier_code_alias_supplier",
        "supplier_product_code_alias",
        ["supplier_id"],
        schema="scm",
    )
    op.create_index(
        "ix_scm_supplier_code_alias_product",
        "supplier_product_code_alias",
        ["product_id"],
        schema="scm",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_scm_supplier_code_alias_identity "
        "ON scm.supplier_product_code_alias "
        f"(coalesce(company_id, '{_NIL_COMPANY}'::uuid), supplier_id, upper(supplier_code))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS scm.uq_scm_supplier_code_alias_identity")
    op.drop_index(
        "ix_scm_supplier_code_alias_product",
        table_name="supplier_product_code_alias",
        schema="scm",
    )
    op.drop_index(
        "ix_scm_supplier_code_alias_supplier",
        table_name="supplier_product_code_alias",
        schema="scm",
    )
    op.drop_table("supplier_product_code_alias", schema="scm")
