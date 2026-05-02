"""User submission portal: tokens, OTP, attachment-type config, seed.

Revision ID: 159_user_submission_portal
Revises: 158_mcp_tools_catalog
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "159_user_submission_portal"
down_revision = "158_mcp_tools_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachment_types",
        sa.Column("max_count_per_entity", sa.Integer(), nullable=True),
    )

    # Portal-draft marker on submission tables. Set while editing in the portal,
    # cleared on Submit (which also triggers downstream notifications).
    op.add_column(
        "complaints",
        sa.Column("portal_draft_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index("ix_complaints_portal_draft_at", "complaints", ["portal_draft_at"])
    op.add_column(
        "stock_inquiries",
        sa.Column("portal_draft_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index("ix_stock_inquiries_portal_draft_at", "stock_inquiries", ["portal_draft_at"])
    op.add_column(
        "purchase_requests",
        sa.Column("portal_draft_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index("ix_purchase_requests_portal_draft_at", "purchase_requests", ["portal_draft_at"])

    op.create_table(
        "portal_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("contact_id", sa.Text(), nullable=False),
        sa.Column("space_id", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("token", name="uq_portal_tokens_token"),
    )
    op.create_index("ix_portal_tokens_token", "portal_tokens", ["token"])
    op.create_index("ix_portal_tokens_contact_id", "portal_tokens", ["contact_id"])
    op.create_index("ix_portal_tokens_expires_at", "portal_tokens", ["expires_at"])

    op.create_table(
        "portal_otp_codes",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("contact_id", sa.Text(), nullable=False),
        sa.Column("space_id", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_portal_otp_codes_contact_id", "portal_otp_codes", ["contact_id"])
    op.create_index("ix_portal_otp_codes_created_at", "portal_otp_codes", ["created_at"])

    # Seed the portal_submission attachment type. Idempotent on conflict.
    op.execute(
        sa.text(
            """
            INSERT INTO attachment_types (id, code, type_name, description, allowed_extensions, max_file_size_mb, max_count_per_entity)
            VALUES (
                gen_random_uuid(),
                'portal_submission',
                'Portal Submission',
                'Attachments uploaded by external contacts via the user submission portal.',
                'jpg,jpeg,png,heic,webp,pdf',
                10,
                10
            )
            ON CONFLICT (code) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM attachment_types WHERE code = 'portal_submission'"))
    op.drop_index("ix_portal_otp_codes_created_at", table_name="portal_otp_codes")
    op.drop_index("ix_portal_otp_codes_contact_id", table_name="portal_otp_codes")
    op.drop_table("portal_otp_codes")
    op.drop_index("ix_portal_tokens_expires_at", table_name="portal_tokens")
    op.drop_index("ix_portal_tokens_contact_id", table_name="portal_tokens")
    op.drop_index("ix_portal_tokens_token", table_name="portal_tokens")
    op.drop_table("portal_tokens")
    op.drop_index("ix_purchase_requests_portal_draft_at", table_name="purchase_requests")
    op.drop_column("purchase_requests", "portal_draft_at")
    op.drop_index("ix_stock_inquiries_portal_draft_at", table_name="stock_inquiries")
    op.drop_column("stock_inquiries", "portal_draft_at")
    op.drop_index("ix_complaints_portal_draft_at", table_name="complaints")
    op.drop_column("complaints", "portal_draft_at")
    op.drop_column("attachment_types", "max_count_per_entity")
