"""The Spec Registry: one spec vocabulary, read by the ranker and the chatbot parser.

Spec search only works if the CRM and the n8n parser agree on what a spec key is and
which values it may take. Held in two places they drift, and the drift is silent: the
parser emits `wall_mounted`, the ranker looks for `wall_hung`, every query scores worse
and nothing logs an error. So the vocabulary lives here and the parser reads it over
HTTP.

Seeds the T0 tracer's pilot keys only. The rest of the measured vocabulary (trap_type,
wc_form, rimless, seat_material, ...) lands in T1, where `bowl_count` also ships
INACTIVE because nothing in the catalog carries it (110 of 22,366 descriptions).

Ownership is split and the seed respects it: vocabulary is the seed's (repaired on
every run), while rank_weight and is_active belong to whoever tuned them against the
eval baseline and are never overwritten.

Revision ID: 311b_product_spec_registry
Revises: 311a_product_category_class
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "311b_product_spec_registry"
down_revision = "311a_product_category_class"
branch_labels = None
depends_on = None


TABLE = "product_spec_registry"


def _has_table(bind, table: str) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, TABLE):
        op.create_table(
            TABLE,
            sa.Column("spec_key", sa.String(length=64), primary_key=True),
            sa.Column("label", sa.String(length=150), nullable=False),
            sa.Column("data_type", sa.String(length=16), nullable=False),
            sa.Column("unit", sa.String(length=16), nullable=True),
            sa.Column(
                "allowed_values",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "synonyms",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "applies_to_classes",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "applies_when",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "rank_weight",
                sa.Numeric(precision=6, scale=3),
                nullable=False,
                server_default=sa.text("1.0"),
            ),
            sa.Column("measured_coverage", sa.Integer(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        )

    # Imported rather than duplicated as INSERT statements so the migration and the
    # re-runnable seed can never disagree about the vocabulary.
    from sqlalchemy.orm import Session

    from app.services.product_spec_registry import seed_spec_registry

    session = Session(bind=bind)
    try:
        result = seed_spec_registry(session)
        session.flush()
        print(
            f"[311b] spec registry: {result['created']} created, "
            f"{result['updated']} vocabulary repairs"
        )
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, TABLE):
        op.drop_table(TABLE)
