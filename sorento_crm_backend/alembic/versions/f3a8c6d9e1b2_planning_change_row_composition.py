"""planning change row composition

Revision ID: f3a8c6d9e1b2
Revises: d41f7a2b9c31
Create Date: 2026-08-19 12:00:00.000000

`documentation/plans/scm/PLAN-so-book-diff-replanning.md` section 0/4, the captain (19
August 2026, live): a `replan` row on the batch page could be `Accept`-ed but Apply never
executed anything for it - accepting recorded a decision, nothing more. `decision` gains
`confirm` (take the board's own proposal as is) and `amend` (the planner's own composition,
built the same way the board's own Amend dialog builds one); `composition_json` freezes the
`ConfirmLine` body Apply will post for the line either way.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f3a8c6d9e1b2'
down_revision = 'd41f7a2b9c31'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'planning_change_rows',
        sa.Column('composition_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema='projects',
    )


def downgrade() -> None:
    op.drop_column('planning_change_rows', 'composition_json', schema='projects')
