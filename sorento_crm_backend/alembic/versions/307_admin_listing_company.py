"""Admin-listing company_id columns (forms, import_logs, audit_logs).

Adds a nullable, indexed ``company_id`` to three tables that back staff-only
admin listings so those listings can be scoped to the active company. These
tables are DELIBERATELY NOT ``CompanyScopedMixin`` owned tables — their other
consumers (portal / public / workflow / embedding reads of forms; the import
worker's log writes; the global audit flush listener) must keep working under
ANY company scope, so we never globally auto-filter them. Only each staff
listing splices a MANUAL predicate (``admin_listing_company_filter``).

Backfill
--------
* ``forms`` and ``import_logs`` -> Sorento (the incumbent company; every
  pre-isolation row belongs to it, mirroring migrations 302/305/306).
* ``audit_logs`` -> LEFT NULL. Historical audit rows predate the entity-company
  copy and a reliable backfill (join each row back to its now-possibly-deleted
  entity's company) is not feasible; forward-only. New audit rows carry the
  changed entity's company via the flush listener. NULL rows stay visible in the
  scoped listing (the filter OR-s ``company_id IS NULL``).

Also a MERGE point: this branch (multi-company, 305->306) and the promo-expiry
branch (301->307_import_job_rows) were two open heads; this revision descends
from both so ``alembic heads`` collapses back to one.

Idempotent raw SQL (``ADD COLUMN IF NOT EXISTS`` / ``CREATE INDEX IF NOT
EXISTS``) — safe to re-run.

Revision ID: 307_admin_listing_company
Revises: 306_company_id_default, 307_import_job_rows
"""
from alembic import op


# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "307_admin_listing_company"
down_revision = ("306_company_id_default", "307_import_job_rows")
branch_labels = None
depends_on = None

SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

# (table, backfill_to_sorento)
_TABLES = (
    ("forms", True),
    ("import_logs", True),
    ("audit_logs", False),  # forward-only, leave NULL
)


def upgrade() -> None:
    for table, backfill in _TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS company_id uuid")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_company_id "
            f"ON {table} (company_id)"
        )
        if backfill:
            op.execute(
                f"UPDATE {table} SET company_id = '{SORENTO_COMPANY_ID}' "
                f"WHERE company_id IS NULL"
            )


def downgrade() -> None:
    for table, _backfill in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_company_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS company_id")
