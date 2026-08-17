"""Where a sales-order line's stock comes from, and the claim when it belongs to somebody else.

Slice P9 (AC-H1..H5). Only the DECISION is stored. The ranked candidates behind it are
computed live from `stock` on every request, because a stored snapshot of another
project's on-hand goes stale the moment they ship, and acting on a stale figure is
precisely the failure this slice exists to stop.

Revision ID: 321_allocation_tables
Revises: 320_extraction_elapsed_ms
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "321_allocation_tables"
down_revision = "320_extraction_elapsed_ms"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Idempotent: this branch shares a development database with other worktrees, so a
    # table may already be present from another run.
    if not _has_table("allocation_claims"):
        op.create_table(
            "allocation_claims",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "from_project_id",
                UUID(as_uuid=False),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "to_project_id",
                UUID(as_uuid=False),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "so_line_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_sales_order_lines.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "product_id",
                UUID(as_uuid=False),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "warehouse_id",
                UUID(as_uuid=False),
                sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("qty", sa.Numeric(15, 4), nullable=False),
            sa.Column("state", sa.String(16), nullable=False, server_default="requested"),
            sa.Column("reason", sa.Text(), nullable=True),
            # users.id is TEXT, so every user reference here is String, never uuid.
            sa.Column(
                "requested_by",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "decided_by",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("decided_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_allocation_claims_to_project", "allocation_claims", ["to_project_id", "state"]
        )
        op.create_index("ix_allocation_claims_line", "allocation_claims", ["so_line_id"])

    if not _has_table("so_line_allocations"):
        op.create_table(
            "so_line_allocations",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "so_line_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_sales_order_lines.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("source_type", sa.String(16), nullable=False),
            sa.Column(
                "warehouse_id",
                UUID(as_uuid=False),
                sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "source_project_id",
                UUID(as_uuid=False),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("qty", sa.Numeric(15, 4), nullable=False),
            sa.Column(
                "claim_id",
                UUID(as_uuid=False),
                sa.ForeignKey("allocation_claims.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "confirmed_by",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("confirmed_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_so_line_allocations_line", "so_line_allocations", ["so_line_id"])


def downgrade() -> None:
    if _has_table("so_line_allocations"):
        op.drop_table("so_line_allocations")
    if _has_table("allocation_claims"):
        op.drop_table("allocation_claims")
