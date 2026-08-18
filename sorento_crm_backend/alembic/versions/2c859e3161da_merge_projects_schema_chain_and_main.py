"""Rejoin the projects lineage with main's, after the Project Sales merge.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** `feat/project-lead-to-so` branched off main before the SCM and
Dealer Kit work landed and grew its own chain, ending at the projects schema move:

    feat/project-lead-to-so ---- 354_projects_schema_move
    main (front-planning)   ---- 366_merge_363_365

Neither is an ancestor of the other, so the tree after the merge carries two heads and
`scripts/bootstrap_env.py` would abort its `alembic stamp head` with "Multiple heads are
present; please specify a single target revision" before a single test ran.

The default hash id is kept rather than a numbered prefix: the numbering is per-lineage
and this revision belongs to neither. It is well under the 32 characters
`alembic_version.version_num` allows (see `tests/test_alembic_revision_ids.py`).

Revision ID: 2c859e3161da
Revises: 354_projects_schema_move, 366_merge_363_365
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c859e3161da'
down_revision = ('354_projects_schema_move', '366_merge_363_365')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
