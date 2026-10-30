"""PORTAL-P4-REQUESTS: complaint revisions (owner card v1.1 Q6 a).

Plan: documentation/plans/portal/PLAN-portal-p4-requests-28oct.md (slice S2).

The complaint becomes a revisable portal submission type (a RevisionAdapter in
app/services/portal_revision_service.py), so the per-form revision setting governs complaints in the
portal and in the CRM alike. Its `portal_revision_configs` row already exists (seeded by
portal_rev_0001); the only schema the revision engine still needs is the denormalized pair every
revisable type carries: `revision_no` (the contact-initiated revision count, the cap counter) and
`last_revised_at`. Same columns as `stock_inquiries` / `purchase_request_headers`.

Strictly additive; downgrade drops the two columns.

Revision ID: pp4_0002_complaint_revision
Revises: pp4_0001_request_view_own
Create Date: 2026-10-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Kept <= 32 chars: alembic_version.version_num is varchar(32).
revision = "pp4_0002_complaint_revision"
down_revision = "pp4_0001_request_view_own"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column("revision_no", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "complaints",
        sa.Column("last_revised_at", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("complaints", "last_revised_at")
    op.drop_column("complaints", "revision_no")
