"""SAMPLE-REQUEST-V2, owner hand test 12 Nov ("i added 2 contacts but why got 1 phone only"):
`sample_requests.site_contact_phone` keeps every picked contact's phone, " & " between, so it
widens from 60 to 255 characters. Widening only; no data changes.

Revision ID: srv2_0003_contact_phone_width
Revises: srv2_0002_status_ruling
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "srv2_0003_contact_phone_width"
down_revision = "srv2_0002_status_ruling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sample_requests",
        "site_contact_phone",
        existing_type=sa.String(60),
        type_=sa.String(255),
        existing_nullable=True,
        schema="projects",
    )


def downgrade() -> None:
    # Values longer than 60 characters would not fit back; cut them rather than fail.
    op.execute(
        "UPDATE projects.sample_requests SET site_contact_phone = left(site_contact_phone, 60) "
        "WHERE length(site_contact_phone) > 60"
    )
    op.alter_column(
        "sample_requests",
        "site_contact_phone",
        existing_type=sa.String(255),
        type_=sa.String(60),
        existing_nullable=True,
        schema="projects",
    )
