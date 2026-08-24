"""Add verified_at to portal_tokens to gate first-visit OTP.

Previously the portal token issued by an admin (Send via Respond.io / QR /
copy-link) granted immediate access until expiry - bypassing OTP entirely.
This migration adds `verified_at`. Resolve_token rejects rows where
`verified_at IS NULL`. Verify_otp marks all unrevoked tokens for the same
contact as verified. Existing tokens are left NULL so every active contact
must verify once after deploy.

Revision ID: 184_portal_token_verified_at
Revises: 183_seed_it_support_agent
Create Date: 2026-05-10
"""
import sqlalchemy as sa
from alembic import op


revision = "184_portal_token_verified_at"
down_revision = "183_seed_it_support_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portal_tokens",
        sa.Column("verified_at", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portal_tokens", "verified_at")
