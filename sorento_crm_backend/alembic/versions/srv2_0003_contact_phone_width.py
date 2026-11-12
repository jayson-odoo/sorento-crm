"""SAMPLE-REQUEST-V2: a sample request's contact phone holds every chosen contact's phone.

Owner hand test 12 Nov ~15:45 ("I added 2 contacts but why got 1 phone only"): the contact phone
now lists each chosen contact's phone ("012-345 6789 & 011-1111 1111", or "Name phone" when some
have none), which outgrows the old 60 characters. Widened to 255, the size of the contact name
beside it. A widening only: no row changes, and Postgres rewrites nothing for a longer varchar.

Revision ID: srv2_0003_contact_phone_width
Revises: srv2_0002_status_ruling
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "srv2_0003_contact_phone_width"
down_revision = "srv2_0002_status_ruling"
branch_labels = None
depends_on = None

_T = "projects.sample_requests"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_T} ALTER COLUMN site_contact_phone TYPE VARCHAR(255)")


def downgrade() -> None:
    # A list longer than the old width keeps its first 60 characters.
    op.execute(
        f"ALTER TABLE {_T} ALTER COLUMN site_contact_phone TYPE VARCHAR(60) "
        "USING left(site_contact_phone, 60)"
    )
