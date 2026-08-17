"""Fulfilment Priority: turn the seeded demand weight on.

The seeded policy weighted `demand_class` at 0.0, so outstanding customer demand moved nothing:
every ranking the Loading Plan and the SPO allocation suggestion produced was purchase-order
document sequence and nothing else. Worse than merely inert - with demand absent from the
average, a purchase order feeding a customer could never overtake an older one feeding nobody,
because the older document's sequence value of 1.0 was already the maximum score available.

This revision raises the weight on databases that were seeded at 0.0 (a fresh install now seeds
3.0 directly, see migration 311's `_PRIORITY_FACTORS`). Demand at 3.0 against sequence at 1.0
gives non-overlapping score bands:

  * project      [0.75, 1.00]
  * retail       [0.30, 0.55]
  * nothing owed [0.00, 0.25]

So a line owed to a customer always outranks one owed to nobody, and purchase-order document
sequence orders the lines inside each band - the buyer's existing rule, kept, but as the
tie-break rather than the whole answer. The literals are repeated here rather than imported from
`app.services.scm.priority` (`SEEDED_WEIGHTS`, `SEEDED_CLASS_WEIGHTS`) so migrations stay
standalone; changing one means changing both.

Only a policy still carrying the seeded name AND a demand weight of 0.0 is touched. A tenant who
has already tuned their own weighting is left exactly as they set it.

Main carries two heads at the time of writing, so this revision joins them rather than needing a
separate merge.

Revision ID: 374_loading_plan_demand_weight
Revises: 373_merge_372_flyer_specs, 373_merge_media_into_main
"""
from alembic import op
import sqlalchemy as sa


revision = "374_loading_plan_demand_weight"
down_revision = ("373_merge_372_flyer_specs", "373_merge_media_into_main")
branch_labels = None
depends_on = None


_OLD_NAME = "Today's rule (PO document sequence)"
_NEW_NAME = "Today's rule (demand owed, then PO document sequence)"

_NOTES = (
    "Demand at 3.0 against sequence at 1.0 gives non-overlapping score bands: "
    "project [0.75, 1.0], retail [0.30, 0.55], nothing owed [0, 0.25]. So a line owed to a "
    "customer always outranks one owed to nobody, and PO document sequence orders the lines "
    "inside each band."
)

_OLD_NOTES = (
    "Seeded to reproduce the manual answer so week-one output is checkable against what Ms "
    "Tee would have done by hand."
)


def _has_policy_table(bind) -> bool:
    return sa.inspect(bind).has_table("priority_policy", schema="scm")


def apply(bind) -> int:
    """Raise `demand_class` to 3.0 on a policy still seeded at 0.0. Rows changed.

    Idempotent: the `demand_class = 0` guard means a second run matches nothing.
    """
    if not _has_policy_table(bind):
        return 0
    res = bind.execute(
        sa.text(
            """
            UPDATE scm.priority_policy
               SET factors = factors || CAST(:f AS jsonb),
                   name = :new_name,
                   notes = :notes
             WHERE name = :old_name
               AND COALESCE((factors->>'demand_class')::numeric, 0) = 0
            """
        ),
        {
            "f": '{"demand_class": 3.0}',
            "new_name": _NEW_NAME,
            "notes": _NOTES,
            "old_name": _OLD_NAME,
        },
    )
    return res.rowcount or 0


def revert(bind) -> int:
    """Put the weight and the name back. Rows changed."""
    if not _has_policy_table(bind):
        return 0
    res = bind.execute(
        sa.text(
            """
            UPDATE scm.priority_policy
               SET factors = factors || CAST(:f AS jsonb),
                   name = :old_name,
                   notes = :notes
             WHERE name = :new_name
            """
        ),
        {
            "f": '{"demand_class": 0.0}',
            "old_name": _OLD_NAME,
            "notes": _OLD_NOTES,
            "new_name": _NEW_NAME,
        },
    )
    return res.rowcount or 0


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
