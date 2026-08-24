"""product discontinued notification: user subscription toggles + product notify watermark

Adds per-user opt-in toggles (email / whatsapp) for the "products discontinued"
batch notification, plus two product columns used by the cron batcher:
discontinued_notified_at (notify watermark - NULL means cron-eligible) and
discontinued_notify_batch_id (stable id for the batch a product was reported in;
deep-linked from the notification to the filtered product list).

Revision ID: b7c1d2e3f4a5
Revises: 5f44ff967988
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "b7c1d2e3f4a5"
down_revision = "5f44ff967988"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notify_email_on_product_discontinued",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "notify_whatsapp_on_product_discontinued",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column("discontinued_notified_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("discontinued_notify_batch_id", sa.UUID(as_uuid=False), nullable=True),
    )
    # Index the cron's hot predicate: pending = is_discontinued AND notified_at IS NULL.
    op.create_index(
        "ix_products_discontinued_pending",
        "products",
        ["is_discontinued", "discontinued_notified_at"],
    )
    # Batch lookups for the deep-linked filtered list.
    op.create_index(
        "ix_products_discontinued_notify_batch_id",
        "products",
        ["discontinued_notify_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_products_discontinued_notify_batch_id", table_name="products")
    op.drop_index("ix_products_discontinued_pending", table_name="products")
    op.drop_column("products", "discontinued_notify_batch_id")
    op.drop_column("products", "discontinued_notified_at")
    op.drop_column("users", "notify_whatsapp_on_product_discontinued")
    op.drop_column("users", "notify_email_on_product_discontinued")
