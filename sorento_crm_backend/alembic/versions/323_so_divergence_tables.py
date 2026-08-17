"""What AutoCount holds when it stops agreeing with what we published.

Slice P8a (AC-N1..N7, D25). Between the import file and the ESB swap the sales order
lives in two systems, and either side can be edited. Neither wins silently: the
difference is held beside our values until a person answers it line by line.

Our values are never overwritten on ingest, which is why `theirs_json` exists at all.
Rows that AGREE are stored as well as rows that differ, because the reconciliation
screen collapses them behind a count and a count nobody wrote down is not a count.

The partial unique index is the idempotency guard: one OPEN divergence per sales order,
so uploading the same export twice recomputes one reconciliation rather than stacking a
second one behind it.

Revision ID: 323_so_divergence_tables
Revises: 322_order_inquiry_derivation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "323_so_divergence_tables"
down_revision = "322_order_inquiry_derivation"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _indexes(table: str) -> set:
    return {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    # Idempotent throughout: this branch shares a development database with other
    # worktrees, so a table may already be present from another run.
    if not _has_table("project_so_divergences"):
        op.create_table(
            "project_so_divergences",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "project_sales_order_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_sales_orders.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("autocount_doc_no", sa.String(80), nullable=True),
            sa.Column("ingest_source", sa.String(16), nullable=False, server_default="upload"),
            sa.Column("status", sa.String(16), nullable=False, server_default="open"),
            sa.Column("compared_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("agreeing_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("differing_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "corrective_publish_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("corrective_publish_taken_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "detected_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
            # users.id is TEXT, so every user reference here is String, never uuid.
            sa.Column(
                "resolved_by",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    existing = _indexes("project_so_divergences")
    if "ix_project_so_divergences_order" not in existing:
        op.create_index(
            "ix_project_so_divergences_order",
            "project_so_divergences",
            ["project_sales_order_id"],
        )
    if "ix_project_so_divergences_status" not in existing:
        op.create_index(
            "ix_project_so_divergences_status",
            "project_so_divergences",
            ["status", "detected_at"],
        )
    if "uq_project_so_divergence_open" not in existing:
        op.create_index(
            "uq_project_so_divergence_open",
            "project_so_divergences",
            ["project_sales_order_id"],
            unique=True,
            postgresql_where=sa.text("status = 'open'"),
        )

    if not _has_table("project_so_divergence_lines"):
        op.create_table(
            "project_so_divergence_lines",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "divergence_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_so_divergences.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("scope", sa.String(8), nullable=False),
            sa.Column("presence", sa.String(16), nullable=False),
            # SET NULL rather than CASCADE: the audit of who accepted what survives the
            # line being cancelled, which is the point of recording it.
            sa.Column(
                "so_line_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_sales_order_lines.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("line_no", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(80), nullable=True),
            sa.Column("ours_json", JSONB, nullable=True),
            sa.Column("theirs_json", JSONB, nullable=True),
            sa.Column("differing_fields", JSONB, nullable=True),
            sa.Column("resolution", sa.String(16), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "resolved_by",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    existing_lines = _indexes("project_so_divergence_lines")
    if "ix_project_so_divergence_lines_divergence" not in existing_lines:
        op.create_index(
            "ix_project_so_divergence_lines_divergence",
            "project_so_divergence_lines",
            ["divergence_id"],
        )
    if "ix_project_so_divergence_lines_so_line" not in existing_lines:
        op.create_index(
            "ix_project_so_divergence_lines_so_line",
            "project_so_divergence_lines",
            ["so_line_id"],
        )


def downgrade() -> None:
    op.drop_table("project_so_divergence_lines")
    op.drop_table("project_so_divergences")
