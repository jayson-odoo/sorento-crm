"""PROJECT-LEADS-REASSIGN: the primary lead on a project.

Revision ID: plr_0001_primary_owner
Revises: ocn_0001_order_change_notice

Additive and idempotent: `projects.projects.primary_owner_user_id` (nullable, FK users.id ON
DELETE SET NULL), then the UAC A6 backfill, which fills NULLs only, so a second run changes
nothing. The backfill statements live in `app.services.project_primary_owner` (shared with
`project_service.backfill_primary_owner`, which the tests drive); that module imports only
SQLAlchemy, never the model graph. A count per rule is printed.
"""

from alembic import op

revision = "plr_0001_primary_owner"
down_revision = "ocn_0001_order_change_notice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.project_primary_owner import backfill

    bind = op.get_bind()
    # projects and users are read on every request: a DDL queued behind a long transaction would
    # queue them all behind itself, so the wait is bounded (transaction-local, put back below).
    previous_lock_timeout = bind.exec_driver_sql("SHOW lock_timeout").scalar()
    bind.exec_driver_sql("SELECT set_config('lock_timeout', '5s', true)")
    op.execute(
        "ALTER TABLE projects.projects "
        "ADD COLUMN IF NOT EXISTS primary_owner_user_id VARCHAR(100)"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'projects_primary_owner_user_id_fkey'
                  AND conrelid = 'projects.projects'::regclass
            ) THEN
                ALTER TABLE projects.projects
                    ADD CONSTRAINT projects_primary_owner_user_id_fkey
                    FOREIGN KEY (primary_owner_user_id) REFERENCES public.users (id)
                    ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    bind.exec_driver_sql(
        "SELECT set_config('lock_timeout', %(value)s, true)", {"value": previous_lock_timeout}
    )
    counts = backfill(bind)
    print(
        "[plr_0001_primary_owner] primary lead backfilled: "
        f"earliest reassignment {counts['earliest_reassign']}, "
        f"lead owner {counts['lead_owner']}, "
        f"current owner {counts['current_owner']}"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE projects.projects DROP CONSTRAINT IF EXISTS projects_primary_owner_user_id_fkey"
    )
    op.execute("ALTER TABLE projects.projects DROP COLUMN IF EXISTS primary_owner_user_id")
