"""Findability sweeps: can a customer find this product by describing it?

Stores the result of asking every card in a flyer for its own product, from several
angles. Persisted rather than printed because the point is comparison - the number after
a vocabulary change only means something next to the number before it.

Keyed on the flyer's `source_id`, so the Cabana and Mocha flyers are new rows.

Revision ID: 311n_product_findability
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "311n_product_findability"
down_revision = "311m_spec_tables_uuid_id"
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "product_findability_runs"):
        op.create_table(
            "product_findability_runs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("source_id", sa.String(length=64), nullable=True),
            sa.Column("source_label", sa.String(length=200), nullable=True),
            sa.Column(
                "status", sa.String(length=16), nullable=False, server_default="running"
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("window", sa.Integer(), nullable=False, server_default=sa.text("25")),
            sa.Column("cards", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "found_by_card", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "found_by_specs", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("not_found", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    if not _has_table(bind, "product_findability_results"):
        op.create_table(
            "product_findability_results",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "run_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("product_findability_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("product_code", sa.String(length=100), nullable=False),
            sa.Column(
                "is_discontinued",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("phrase", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "boundary", sa.String(length=64), nullable=False, server_default="none"
            ),
            sa.Column(
                "ranks",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_findability_results_run", "product_findability_results", ["run_id"]
        )
        op.create_index(
            "ix_findability_results_boundary", "product_findability_results", ["boundary"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "product_findability_results"):
        op.drop_table("product_findability_results")
    if _has_table(bind, "product_findability_runs"):
        op.drop_table("product_findability_runs")
