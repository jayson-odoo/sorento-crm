"""CATALOG-IMAGES: catalogue photo readings and the photos cut out of them.

Revision ID: cim_0001_catalogue_photos
Revises: sales_unified_0002
Create Date: 2026-10-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Kept <= 32 chars: alembic_version.version_num is varchar(32).
revision = "cim_0001_catalogue_photos"
down_revision = "sales_unified_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalogue_photo_readings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("photo_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column(
            "pdf_attachment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "directory_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("attachment_directories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_catalogue_photo_readings_company_id", "catalogue_photo_readings", ["company_id"])
    op.create_index(
        "ix_catalogue_photo_readings_company_created",
        "catalogue_photo_readings",
        ["company_id", "created_at"],
    )

    op.create_table(
        "catalogue_photos",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "reading_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("catalogue_photo_readings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "attachment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("dhash", sa.String(16), nullable=True),
        sa.Column("printed_code", sa.String(120), nullable=True),
        sa.Column("block_codes", postgresql.JSONB(), nullable=False),
        sa.Column("placeholders", postgresql.JSONB(), nullable=False),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rung", sa.String(16), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("suggestion", sa.String(120), nullable=True),
        sa.Column("other_block_products", postgresql.JSONB(), nullable=False),
        sa.Column("also_attach_product_ids", postgresql.JSONB(), nullable=False),
        sa.Column(
            "duplicate_of_attachment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("duplicate_distance", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("attached_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_catalogue_photos_reading_page", "catalogue_photos", ["reading_id", "page", "position"]
    )
    op.create_index("ix_catalogue_photos_attachment_id", "catalogue_photos", ["attachment_id"])
    op.create_index("ix_catalogue_photos_product_id", "catalogue_photos", ["product_id"])
    op.create_index("ix_catalogue_photos_duplicate_of", "catalogue_photos", ["duplicate_of_attachment_id"])


def downgrade() -> None:
    op.drop_index("ix_catalogue_photos_duplicate_of", table_name="catalogue_photos")
    op.drop_index("ix_catalogue_photos_product_id", table_name="catalogue_photos")
    op.drop_index("ix_catalogue_photos_attachment_id", table_name="catalogue_photos")
    op.drop_index("ix_catalogue_photos_reading_page", table_name="catalogue_photos")
    op.drop_table("catalogue_photos")
    op.drop_index("ix_catalogue_photo_readings_company_created", table_name="catalogue_photo_readings")
    op.drop_index("ix_catalogue_photo_readings_company_id", table_name="catalogue_photo_readings")
    op.drop_table("catalogue_photo_readings")
