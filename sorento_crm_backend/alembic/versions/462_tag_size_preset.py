"""dealer kit: tag size presets (PLAN-price-tag-ux-r3.md S4, D2)

A saved, named tag size - a shortcut the request designer's Tag Size dropdown
offers under "Saved sizes", editable at ``/dealer-kit/tag-sizes``. Company
scoped, unique per ``(company_id, name)`` so two marketers cannot silently
shadow each other's "Shelf rail".

Revision ID: 462_tag_size_preset
Revises: 463_draft_proposed
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "462_tag_size_preset"
down_revision = "464_overdue_grace"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name, schema=SCHEMA)


def upgrade() -> None:
    # Hand-applied on the shared dev database before the reparent (see
    # 443/450/452/460/461/463 for the same shared-DB, per-worktree stamp drift):
    # a no-op if the table already exists rather than a failure.
    if _has_table("tag_size_preset"):
        return
    op.create_table(
        "tag_size_preset",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # `ForeignKey` + `index=True`, matching `CompanyScopedMixin.company_id`
        # (`app/models/base.py`) and this schema's own `tag_template.company_id`.
        sa.Column(
            "company_id", UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("width_mm", sa.Numeric(6, 2), nullable=False),
        sa.Column("height_mm", sa.Numeric(6, 2), nullable=False),
        # String, not UUID - ``users.id`` is TEXT (see ``tag_template_version.
        # created_by``); a UUID-typed column here cannot join to it without an
        # explicit cast.
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "company_id", "name", name="uq_dealer_kit_tag_size_preset_company_name"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_tag_size_preset_company_id",
        "tag_size_preset",
        ["company_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    if not _has_table("tag_size_preset"):
        return
    op.drop_index(
        "ix_dealer_kit_tag_size_preset_company_id",
        table_name="tag_size_preset",
        schema=SCHEMA,
    )
    op.drop_table("tag_size_preset", schema=SCHEMA)
