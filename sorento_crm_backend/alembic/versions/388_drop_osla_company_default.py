"""SCM: drop the hard-coded company default on the location-allocation table.

Migration 376 created `scm.order_summary_location_allocation` with `company_id` defaulting
to the Sorento company id. No other `CompanyScopedMixin` table carries a server default: the
application stamps `company_id` from the request's company scope on every insert, and a
default that silently files an unstamped row under Sorento hides exactly the write that
forgot to. The ORM model never declared the default either, so a `create_all` database and a
migrated one disagreed on this one column until now.

Downgrade restores the default exactly as 376 set it. 376 itself is landed and is not
edited.

Revision ID: 388_drop_osla_company_default
Revises: 387_scm_reco_keyed_status
"""
from alembic import op


revision = "388_drop_osla_company_default"
down_revision = "387_scm_reco_keyed_status"
branch_labels = None
depends_on = None

_TABLE = "scm.order_summary_location_allocation"
_SORENTO = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} ALTER COLUMN company_id DROP DEFAULT")


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE {_TABLE} ALTER COLUMN company_id SET DEFAULT '{_SORENTO}'::uuid"
    )
