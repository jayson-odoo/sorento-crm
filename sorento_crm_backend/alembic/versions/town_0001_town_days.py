"""SORENTO-TOWN: the `town_days` table (one frozen snapshot + event log per company per day).

Additive only, idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through
`create_all`, can take it in any order.
Plan: documentation/plans/dashboard/PLAN-sorento-town-08nov.md.

Revision ID: town_0001_town_days
Revises: ptag_0019_acc_colours
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "town_0001_town_days"
down_revision = "ptag_0019_acc_colours"
branch_labels = None
depends_on = None


UPGRADE_SQL = (
    """
    CREATE TABLE IF NOT EXISTS town_days (
        id UUID PRIMARY KEY,
        company_id UUID NOT NULL REFERENCES companies(id),
        day DATE NOT NULL,
        snapshot JSONB NOT NULL,
        events JSONB NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT uq_town_days_company_day UNIQUE (company_id, day)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_town_days_company_id ON town_days (company_id)",
)


def upgrade() -> None:
    bind = op.get_bind()
    for statement in UPGRADE_SQL:
        bind.execute(sa.text(statement))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS town_days")
