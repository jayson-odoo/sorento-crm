"""Rejoin the three lanes that each cut their own merge off the ticket tip.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** Three feature branches were open at once and all of them
branched off the same tip of main (`368_merge_tickets_main`). Each cut its own
merge revision to rejoin the ticket work, and each landed on main:

    PR #198 (onboarding intake)      ---- 369_merge_onboarding_tickets
    PR #195 (spec verification lane) ---- 370_merge_tickets_spec_verif
    PR #197 (brand member routing)   ---- 371_brand_member_routing

None of the three is an ancestor of the others, so main now carries three heads.
That is not a warning, it is a broken deploy: CI's "Bootstrap the database" step
runs `scripts/bootstrap_env.py`, which aborts its `alembic stamp head` with
"Multiple heads are present; please specify a single target revision" before a
single test runs.

Join forward, never renumber a landed revision - rewriting one strands every
database that already recorded the old id.

The id is 21 characters. `bootstrap_env` stamps the head into an `alembic_version`
table alembic creates as `version_num varchar(32)` (see 322's docstring and
`tests/test_alembic_revision_ids.py`), so any head id must stay <= 32. A 33-char id
once ran every migration and then failed writing its own id.

Revision ID: 372_merge_three_heads
Revises: 369_merge_onboarding_tickets, 370_merge_tickets_spec_verif, 371_brand_member_routing
Create Date: 2026-08-17
"""

from __future__ import annotations

revision = "372_merge_three_heads"
down_revision = (
    "369_merge_onboarding_tickets",
    "370_merge_tickets_spec_verif",
    "371_brand_member_routing",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
