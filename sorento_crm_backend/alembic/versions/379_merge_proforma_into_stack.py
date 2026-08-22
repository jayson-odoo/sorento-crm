"""Rejoin the proforma invoice revision with the integration branch's head.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI database)
has ONE target.

**Why there are two.** The proforma slice was rebased onto main's Project Sales merge
and sits directly on it, while the integration branch had meanwhile stacked the SCM
lanes above that same revision:

    375_scm_proforma_invoice     (proforma: revises 374_merge_proj_media_flyer)
    378_merge_stage2_into_stack  (integration: joins 376_merge_1c_supply_decisions
                                  and 377_merge_stage2_main, both of which sit above
                                  374_merge_proj_media_flyer as well)

They are siblings, so merging the proforma branch in leaves two heads. Two heads is
not a warning, it is a broken deploy: `alembic upgrade head` refuses to guess and
`bootstrap_env` aborts its stamp with "Multiple heads are present" before a single
test runs. This revision joins forward from both.

No `depends_on` is needed here, unlike the Stage 1C / Stage 2 join one revision back.
`375_scm_proforma_invoice` creates two tables of its own (`scm.proforma_invoice` and
`scm.proforma_invoice_line`), seeds an alias doc type and sweeps one permission; it
shares no table, view or index with anything the integration lanes touch, so the order
between the two branches genuinely does not matter.

Neither parent is renumbered or deleted; both are landed on their branches and any
database stamped with either must still be able to upgrade. Join forward, never
renumber a landed revision.

The id is 29 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under 32
(see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 379_merge_proforma_into_stack
Revises: 378_merge_stage2_into_stack, 375_scm_proforma_invoice
Create Date: 2026-08-18
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "379_merge_proforma_into_stack"
down_revision = (
    "378_merge_stage2_into_stack",
    "375_scm_proforma_invoice",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
