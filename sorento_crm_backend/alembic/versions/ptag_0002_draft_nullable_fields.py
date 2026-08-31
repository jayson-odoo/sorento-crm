"""a price tag request draft may have no debtor and no needed-by date (D48a)

Save Draft validates nothing: the salesperson types the form over several
sittings and what is there so far has to be storable. Both columns were NOT NULL,
so the very first draft with an empty debtor was refused by Postgres.

Completeness moves to SUBMIT, enforced in ``PriceTagRequestService`` where the
refusal can name each missing field. A constraint could only produce a violation
nobody can read, so none replaces these.

Down re-imposes NOT NULL, and fills any row that was saved as a draft in the
meantime so the alter cannot fail on the way back.

Revision ID: ptag_0002
Revises: a67d68a2ed9a
Create Date: 2026-08-30
"""
import sqlalchemy as sa
from alembic import op


revision = "ptag_0002"
down_revision = "a67d68a2ed9a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "price_tag_requests",
        "debtor_name",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "price_tag_requests",
        "needed_by_date",
        existing_type=sa.Date(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE price_tag_requests
        SET debtor_name = COALESCE(debtor_name, '')
        WHERE debtor_name IS NULL
        """
    )
    op.execute(
        """
        UPDATE price_tag_requests
        SET needed_by_date = COALESCE(needed_by_date, CURRENT_DATE)
        WHERE needed_by_date IS NULL
        """
    )
    op.alter_column(
        "price_tag_requests",
        "needed_by_date",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.alter_column(
        "price_tag_requests",
        "debtor_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )
