"""Add attachment_types.supports_field_linkage flag.

Replaces the frontend's hardcoded "is this a product photo?" name regex with an
admin-controlled toggle deciding whether an attachment type exposes the
"Linked to / Linked fields" section. Backfills existing product-photo-like types
to true so current behaviour is preserved.

Revision ID: 218_attachment_type_field_linkage
Revises: 217_complaint_product_lines
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa


revision = "218_attachment_type_field_linkage"
down_revision = "217_complaint_product_lines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachment_types",
        sa.Column(
            "supports_field_linkage",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    # Preserve current behaviour: product photo / image / picture types linked fields.
    op.execute(
        sa.text(
            "UPDATE attachment_types SET supports_field_linkage = true "
            "WHERE type_name ~* 'product\\s*(photo|image|picture)'"
        )
    )


def downgrade() -> None:
    op.drop_column("attachment_types", "supports_field_linkage")
