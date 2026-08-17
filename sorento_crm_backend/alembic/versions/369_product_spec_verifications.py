"""The verification ledger: who vouched for a code's specs, and who took it back.

One new table, no backfill. A ledger that has never been written has nothing to
backfill - every existing code correctly reads `unverified`, which is what "no rows"
means (AC-D.2), so seeding rows here would invent verifications nobody made.

Two indexes, and the partial one is load-bearing rather than a lookup aid: it is what
makes a concurrent double-verify land as ONE row (AC-D.4). The service inserts inside a
savepoint and reads a unique violation on this index as "somebody else got there first",
so the guarantee is enforced by the database rather than by the order two requests
happen to arrive in.

Not company-scoped, matching every other spec table: a code's specs are a property of
the model, and so is a person's confirmation of them.

Revision ID: 369_product_spec_verifications
Revises: 366_merge_363_365
Create Date: 2026-08-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "369_product_spec_verifications"
down_revision = "366_merge_363_365"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_spec_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("product_code", sa.String(length=100), nullable=False),
        sa.Column("party", sa.String(length=16), nullable=False, server_default="internal"),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=False), nullable=True),
        # Text with no FK on purpose: a deleted user must not take the history of what
        # they verified with them.
        sa.Column("verified_by_user_id", sa.Text(), nullable=True),
        sa.Column("verified_by_name", sa.Text(), nullable=True),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("values_hash", sa.String(length=64), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("invalidated_reason", sa.String(length=32), nullable=True),
        sa.Column("invalidated_diff", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("invalidated_by_user_id", sa.Text(), nullable=True),
        sa.Column("invalidated_by_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_product_spec_verifications_active",
        "product_spec_verifications",
        ["product_code", "party"],
        unique=True,
        postgresql_where=sa.text("invalidated_at IS NULL"),
    )
    op.create_index(
        "ix_product_spec_verifications_code",
        "product_spec_verifications",
        ["product_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_spec_verifications_code", table_name="product_spec_verifications")
    op.drop_index("uq_product_spec_verifications_active", table_name="product_spec_verifications")
    op.drop_table("product_spec_verifications")
