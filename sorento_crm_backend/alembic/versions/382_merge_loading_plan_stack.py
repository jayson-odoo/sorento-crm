"""Rejoin the loading-plan demand-ranking lane with the integration branch's head.

No DDL of its own. A merge revision only joins lineages so `alembic upgrade head` (and
the `alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI database)
has ONE target.

**Why there are two.** The demand-ranking lane cut its revision straight across main's
two 373 heads, while the integration branch had stacked seven SCM lanes above them:

    374_loading_plan_demand_weight  (ranking: joins 373_merge_372_flyer_specs and
                                     373_merge_media_into_main, and re-weights the
                                     seeded `scm.priority_policy` row)
    381_merge_container_into_stack  (integration: the head after Stage 0/1A, 1B, 1C,
                                     Stage 2, proforma, the Kailu aliases and the
                                     multi-supplier container)

They are siblings, so merging the ranking branch in leaves two heads. Two heads is not
a warning, it is a broken deploy: `alembic upgrade head` refuses to guess and
`bootstrap_env` aborts its stamp with "Multiple heads are present" before a single
test runs. This revision joins forward from both.

No `depends_on` is needed, and that was checked rather than assumed. Only three
revisions in the whole tree touch `scm.priority_policy` - 311 (creates and seeds it),
336, and 374_loading_plan_demand_weight - and the first two sit far below both parents,
so the chain already orders them. Nothing else in this stack reads or writes that
table, so the order between the two branches genuinely does not matter.

Neither parent is renumbered or deleted; both are landed on their branches and any
database stamped with either must still be able to upgrade. Join forward, never
renumber a landed revision.

The id is 28 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under 32
(see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 382_merge_loading_plan_stack
Revises: 381_merge_container_into_stack, 374_loading_plan_demand_weight
Create Date: 2026-08-18
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "382_merge_loading_plan_stack"
down_revision = (
    "381_merge_container_into_stack",
    "374_loading_plan_demand_weight",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
