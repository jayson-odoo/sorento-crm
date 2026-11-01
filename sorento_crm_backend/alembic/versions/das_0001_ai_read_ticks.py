"""DOC-ACCESS-SIMPLE: who may read a document type is two ticks, not one audience

Revision ID: das_0001_ai_read_ticks
Revises: dp_0001_cs_planning_access
Create Date: 2026-11-01 00:00:00.000000

`attachment_types.ai_read_staff` (Staff tick) and `ai_read_codes` (the access codes ticked for contacts)
replace `ai_audience`, which stays in the table, unread (dropped later, backlog BL-070). The backfill
reproduces today's rule exactly: off -> (false, []); staff -> (true, []); dealer -> (true, every ACTIVE
code except end_user); public -> (true, every ACTIVE code), codes in catalogue sort order.
`backfill(bind)` is the statement the migration runs, callable on any connection.
"""
import sqlalchemy as sa
from alembic import op

revision = "das_0001_ai_read_ticks"
down_revision = "dp_0001_cs_planning_access"
branch_labels = None
depends_on = None

_ACTIVE_CODES = (
    "(SELECT jsonb_agg(c.code ORDER BY c.sort_order, c.code) FROM contact_access_types c "
    "WHERE c.is_active IS TRUE{extra})"
)

BACKFILL_SQL = f"""
UPDATE attachment_types t SET
    ai_read_staff = (t.ai_audience <> 'off'),
    ai_read_codes = CASE t.ai_audience
        WHEN 'public' THEN COALESCE({_ACTIVE_CODES.format(extra="")}, '[]'::jsonb)
        WHEN 'dealer' THEN COALESCE({_ACTIVE_CODES.format(extra=" AND c.code <> 'end_user'")}, '[]'::jsonb)
        ELSE '[]'::jsonb
    END
"""


def backfill(bind) -> None:
    bind.execute(sa.text(BACKFILL_SQL))


def upgrade() -> None:
    op.execute("ALTER TABLE attachment_types ADD COLUMN IF NOT EXISTS ai_read_staff BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE attachment_types ADD COLUMN IF NOT EXISTS ai_read_codes JSONB NOT NULL DEFAULT '[]'::jsonb")
    backfill(op.get_bind())


def downgrade() -> None:
    op.execute("ALTER TABLE attachment_types DROP COLUMN IF EXISTS ai_read_codes")
    op.execute("ALTER TABLE attachment_types DROP COLUMN IF EXISTS ai_read_staff")
