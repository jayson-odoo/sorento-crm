"""product set proposals: what the catalogue suggests, before anybody agrees

Explicit ``op.create_table`` rather than an autogenerate stub. New tables are
absent on a database built by ``create_all``, so a migration that only carries an
index leaves the model with no table behind it and every read 500s on
``UndefinedTable`` long after the branch looked green.

Deliberately thin. The flyer-spec proposal batch this shape follows carries a
status, an error message, a job id and seven counts because it wraps an LLM read
on an RQ job. This pass is a synchronous pure derivation over code shape, so
there is no state to report and nothing to poll, and the counts are derived on
read so they cannot drift from the rows they count.

Revision ID: 413_product_set_proposals
Revises: 412_link_provenance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "413_product_set_proposals"
down_revision = "412_link_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_set_proposal_batches",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_product_set_proposal_batches_company_id",
        "product_set_proposal_batches",
        ["company_id"],
    )

    op.create_table(
        "product_set_proposals",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "batch_id",
            UUID(as_uuid=False),
            sa.ForeignKey("product_set_proposal_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("family_key", sa.String(length=100), nullable=False),
        sa.Column("set_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        # Product IDS and the price tick only. A stored price snapshot goes stale
        # the moment somebody edits the product and becomes a second source of
        # truth for the same number, so codes, descriptions and live list prices
        # are hydrated from `products` at read time instead.
        sa.Column("members", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("batch_id", "set_code", name="uq_product_set_proposal_code"),
    )
    op.create_index("ix_product_set_proposals_batch", "product_set_proposals", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_product_set_proposals_batch", table_name="product_set_proposals")
    op.drop_table("product_set_proposals")
    op.drop_index(
        "ix_product_set_proposal_batches_company_id",
        table_name="product_set_proposal_batches",
    )
    op.drop_table("product_set_proposal_batches")
