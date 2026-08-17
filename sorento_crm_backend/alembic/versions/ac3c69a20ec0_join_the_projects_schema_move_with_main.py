"""Join the projects schema move with main.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at.

Two heads exist after merging main into this branch:

    354_projects_schema_move   (this branch: the 309..354 project-sales lane,
                                ending in the ADR-0011 move of the module's 47
                                tables into the `projects` schema)
    368_merge_tickets_main     (main: the tip of main, itself a merge of the
                                intervention-ticket lane with the flyer /
                                SCM / dealer-kit lanes)

The two lanes are independent below this point, and deliberately so: 309..354
created and altered the project tables in `public` and then moved them, which
is true at the moment each of them runs whichever order the lanes are joined
in. Nothing on main's side names any of the 47 tables, so there is no ordering
constraint between the lanes and nothing for this revision to do.

The id is 12 characters: `scripts/bootstrap_env.py` stamps the head into an
`alembic_version` table created with `version_num varchar(32)` (see 322's
docstring), so any head id must stay <= 32.

Revision ID: ac3c69a20ec0
Revises: 354_projects_schema_move, 368_merge_tickets_main
Create Date: 2026-08-17 15:36:54.430011

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ac3c69a20ec0'
down_revision = ('354_projects_schema_move', '368_merge_tickets_main')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
