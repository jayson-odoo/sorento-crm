"""a price tag request records WHO claimed it

Claiming wrote the marketing user's id into ``created_by``, the column that says
who made the row, and nothing ever read it back: the detail page said "Assigned
to: Unclaimed" for the rest of the request's life, and marketing had no way to
see whose desk a design was on.

``assigned_to_id`` is that field, with a real foreign key. ``users.id`` is TEXT
on this database (``created_by`` is UUID and therefore could never carry one),
so the column is TEXT to match and the FK is enforceable.

The backfill reads the overload back out: a request that is past ``new`` and
carries a ``created_by`` was claimed by that user, and the row is filled in
before the FK goes on so an id that no longer names a user cannot fail the
alter. ``created_by`` is left alone - it is not wrong, it was only doing two
jobs.

Revision ID: ptag_0004
Revises: 445_merge_ptag_main
Create Date: 2026-08-30
"""
import sqlalchemy as sa
from alembic import op


revision = "ptag_0004"
down_revision = "445_merge_ptag_main"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_tag_requests",
        sa.Column("assigned_to_id", sa.String(), nullable=True),
    )
    op.execute(
        """
        UPDATE price_tag_requests
        SET assigned_to_id = created_by::text
        WHERE created_by IS NOT NULL
          AND status <> 'new'
          AND EXISTS (
              SELECT 1 FROM users u WHERE u.id = price_tag_requests.created_by::text
          )
        """
    )
    op.create_index(
        "ix_price_tag_requests_assigned_to_id",
        "price_tag_requests",
        ["assigned_to_id"],
    )
    op.create_foreign_key(
        "fk_price_tag_requests_assigned_to_id_users",
        "price_tag_requests",
        "users",
        ["assigned_to_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_price_tag_requests_assigned_to_id_users",
        "price_tag_requests",
        type_="foreignkey",
    )
    op.drop_index("ix_price_tag_requests_assigned_to_id", "price_tag_requests")
    op.drop_column("price_tag_requests", "assigned_to_id")
