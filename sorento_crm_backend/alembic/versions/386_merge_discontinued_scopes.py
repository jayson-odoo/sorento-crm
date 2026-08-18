"""Rejoin main's discontinued-notice recipient scopes with the fulfilment-planning head.

No DDL of its own. A merge revision only joins lineages so `alembic upgrade head` (and
the `alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI database)
has ONE target.

**Why there are two.** Main landed the per-(company, brand) recipient scopes for the
discontinued notice (#220) as `375_user_discontinued_scopes` straight above main's own
head `374_merge_proj_media_flyer`, while this branch had stacked the fulfilment planning
lanes above the same base:

    375_user_discontinued_scopes  (main: `user_discontinued_scopes` table)
    385_fulfilment_priority_fair  (this branch: adopted planning 383, per-line
                                   committed_v 384, the fair priority policy 385)

They are siblings, so merging main in leaves two heads. Two heads is not a warning, it
is a broken deploy: `alembic upgrade head` refuses to guess and `bootstrap_env` aborts
its stamp with "Multiple heads are present" before a single test runs. This revision
joins forward from both.

No `depends_on` is needed, and that was checked rather than assumed: 375 creates one
table of its own and touches nothing the 383-385 chain reads or writes, and vice versa,
so the order between the two branches genuinely does not matter.

Neither parent is renumbered or deleted; both are landed on their branches and any
database stamped with either must still be able to upgrade. Join forward, never
renumber a landed revision. Note that a different, older `375_*` revision id
(the proforma one) also exists by filename number; ids are what alembic keys on, and
those are distinct.

The id is 29 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under 32
(see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 386_merge_discontinued_scopes
Revises: 385_fulfilment_priority_fair, 375_user_discontinued_scopes
Create Date: 2026-08-19
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "386_merge_discontinued_scopes"
down_revision = (
    "385_fulfilment_priority_fair",
    "375_user_discontinued_scopes",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
