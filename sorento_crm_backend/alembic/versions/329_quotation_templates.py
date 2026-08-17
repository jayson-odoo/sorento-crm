"""The company's standing cover letter and terms (S4, AC-E1).

One active template per (company, kind), enforced by a PARTIAL unique index rather than by the
service alone. The service can only deactivate-then-activate as two writes, which two concurrent
requests can interleave, and "the active template" has to identify exactly one row. This repo has
already paid for the alternative: ``system_settings`` was a singleton nothing enforced, became two
rows, and every read went non-deterministic while the screens still returned 200.

Defensively re-runnable (``_has_table`` / ``_has_column`` guards) because the dev database is a
copy of production and this branch's revisions have been applied there by hand more than once.

Revision ID: 329_quotation_templates
Revises: 328_quotation_signatures
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID


revision = "329_quotation_templates"
down_revision = "328_quotation_signatures"
branch_labels = None
depends_on = None


# Both guards pin the CURRENT schema, and that is not pedantry: an unqualified
# information_schema / pg_indexes lookup also matches the throwaway `zzt_blank_*` schemas the
# Postgres test fixtures create. A test suite running while this migration is applied made the
# guard answer "the table already exists" about somebody else's schema, so the upgrade no-opped
# and stamped a revision whose DDL never ran.
def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            text(
                "select 1 from information_schema.tables "
                "where table_name = :t and table_schema = current_schema()"
            ),
            {"t": table},
        ).scalar()
    )


def _has_index(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            text("select 1 from pg_indexes where indexname = :n and schemaname = current_schema()"),
            {"n": name},
        ).scalar()
    )


def upgrade() -> None:
    if not _has_table("quotation_templates"):
        op.create_table(
            "quotation_templates",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "company_id",
                UUID(as_uuid=False),
                sa.ForeignKey("companies.id"),
                nullable=True,
            ),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("body_html", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("created_by", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("ix_quotation_templates_company_id"):
        op.create_index(
            "ix_quotation_templates_company_id", "quotation_templates", ["company_id"]
        )
    if not _has_index("ix_quotation_templates_company_kind"):
        op.create_index(
            "ix_quotation_templates_company_kind", "quotation_templates", ["company_id", "kind"]
        )
    # THE constraint this migration exists for.
    if not _has_index("uq_quotation_templates_active"):
        op.create_index(
            "uq_quotation_templates_active",
            "quotation_templates",
            ["company_id", "kind"],
            unique=True,
            postgresql_where=sa.text("is_active"),
        )


def downgrade() -> None:
    op.drop_index("uq_quotation_templates_active", table_name="quotation_templates")
    op.drop_index("ix_quotation_templates_company_kind", table_name="quotation_templates")
    op.drop_index("ix_quotation_templates_company_id", table_name="quotation_templates")
    op.drop_table("quotation_templates")
