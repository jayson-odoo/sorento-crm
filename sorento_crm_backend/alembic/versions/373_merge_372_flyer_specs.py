"""Rejoin main's three-head merge with the flyer spec proposals lane.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** This branch cut its own merge (`372_merge_flyer_specs_heads`)
joining the same three landed heads that main's `372_merge_three_heads` joins,
plus `370_flyer_spec_proposals`. Both merges then existed for the same three
parents, which leaves two heads again. Ours had never been pushed, so it is
deleted and replaced by this one, which chains FORWARD off main's merge:

    372_merge_three_heads (main)  ----\
                                       373_merge_372_flyer_specs
    370_flyer_spec_proposals      ----/

Join forward, never renumber a landed revision - rewriting one strands every
database that already recorded the old id.

The id is 25 characters. `bootstrap_env` stamps the head into an `alembic_version`
table alembic creates as `version_num varchar(32)` (see 322's docstring and
`tests/test_alembic_revision_ids.py`), so any head id must stay <= 32.

Revision ID: 373_merge_372_flyer_specs
Revises: 372_merge_three_heads, 370_flyer_spec_proposals
Create Date: 2026-08-17
"""

from __future__ import annotations

revision = "373_merge_372_flyer_specs"
down_revision = (
    "372_merge_three_heads",
    "370_flyer_spec_proposals",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
