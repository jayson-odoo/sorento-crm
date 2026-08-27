"""F11 / R17: "none of ours" is an answer, and it is recorded like every other one.

Revision ID: 432_supplier_code_alias_dismiss
Revises: 430_supplier_notice_xlsx
Create Date: 2026-08-27

The queue of codes nothing in our catalogue answers is a to-do list, and a to-do list a
person cannot cross a line off is one they stop reading. Some of those codes are not ours at
all - a supplier's own accessory, a spare, something they hold for somebody else - and the
only true answer is "not one of ours", which no product id can express.

So a dismissal is an alias row with NO product: `source = 'dismissed'`. It lives in the same
table as a match for the reason a match lives there - it is what somebody DECIDED about this
supplier's spelling, the ladder consults it first (rung 0) and refuses the code, and Forget
undoes it through the DELETE that already exists. A second table would have meant two places
to ask "has anybody ruled on this code" and two answers when they disagree.

Two checks rather than one, because they say different things. `source IN (...)` is the
vocabulary. `(source = 'dismissed') = (product_id IS NULL)` is the rule that the two columns
are one fact: dismissed means exactly "no product", and a row claiming both a dismissal and a
product is unreadable by every screen that renders it.

Nothing to backfill: no row on file is a dismissal, and the existing rows all carry a product,
so they pass both checks unchanged.
"""
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "432_supplier_code_alias_dismiss"
down_revision = "430_supplier_notice_xlsx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "supplier_product_code_alias",
        "product_id",
        existing_type=UUID(as_uuid=False),
        nullable=True,
        schema="scm",
    )
    op.drop_constraint(
        "ck_scm_supplier_code_alias_source",
        "supplier_product_code_alias",
        type_="check",
        schema="scm",
    )
    op.create_check_constraint(
        "ck_scm_supplier_code_alias_source",
        "supplier_product_code_alias",
        "source IN ('auto', 'manual', 'dismissed')",
        schema="scm",
    )
    op.create_check_constraint(
        "ck_scm_supplier_code_alias_dismissed",
        "supplier_product_code_alias",
        "(source = 'dismissed') = (product_id IS NULL)",
        schema="scm",
    )


def downgrade() -> None:
    # The dismissals go first: they are the only rows that cannot exist under the old shape,
    # and leaving them would make the NOT NULL fail rather than the schema go back.
    op.execute(
        "DELETE FROM scm.supplier_product_code_alias WHERE source = 'dismissed'"
    )
    op.drop_constraint(
        "ck_scm_supplier_code_alias_dismissed",
        "supplier_product_code_alias",
        type_="check",
        schema="scm",
    )
    op.drop_constraint(
        "ck_scm_supplier_code_alias_source",
        "supplier_product_code_alias",
        type_="check",
        schema="scm",
    )
    op.create_check_constraint(
        "ck_scm_supplier_code_alias_source",
        "supplier_product_code_alias",
        "source IN ('auto', 'manual')",
        schema="scm",
    )
    op.alter_column(
        "supplier_product_code_alias",
        "product_id",
        existing_type=UUID(as_uuid=False),
        nullable=False,
        schema="scm",
    )

