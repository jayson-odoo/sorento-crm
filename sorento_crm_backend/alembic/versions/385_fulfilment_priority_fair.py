"""Fulfilment Priority: seed a policy that can actually rank, and switch it on.

The captain, looking at a planning board where every contribution scored 0.00: "I need a fair
policy please".

The active rule weights `po_document_sequence` at 1.0 and everything else at 0.0. A purchase
order has a document sequence; a SALES-ORDER line does not, so on the fulfilment board every
weighted factor is absent, `rank_score` divides by a zero denominator, and every row scores
0.00. The scorer is behaving exactly as designed - a factor with no value is dropped from both
sums rather than counted as zero - and the result is a ranking that ranks nothing.

So this seeds a policy weighted on what a demand row actually carries, and makes it the active
one. It does NOT edit the previous row's weights: that row stays, inactive, so undoing this is
`downgrade` (or one UPDATE), not an act of memory.

What is switched on, factor by factor:

  * `need_by_date` 3.0      - delivery date, and the strongest voice: it outweighs document
                                age and customer credit together.
  * `demand_class` 3.0      - unchanged from what migration 374 deliberately switched on for
                                the purchase-order path. ONE policy serves three moments
                                (`app/services/scm/priority.py`), so a change made for the board
                                reaches container loading and the arriving-stock suggestion;
                                keeping demand weighted is what stops this quietly rewriting
                                which purchase order gets a container slot. On the board it
                                separates nothing, because every row there is project-class by
                                construction - it shifts every score by the same amount.
  * `document_age` 1.0      - document date, older first.
  * `customer_credit` 1.0   - shorter payment terms first. Absent for a purchase-order
                                candidate and for a customer nobody has assessed; absent means
                                DROPPED from the average, never scored zero.
  * `po_document_sequence` 1.0 - the buyer's original rule, kept as a tie-break. Structurally
                                absent on every board row, so it costs the board nothing.

The literals are repeated here rather than imported from `app.services.scm.priority`
(`FAIR_POLICY_NAME`, `FAIR_WEIGHTS`, `FAIR_CLASS_WEIGHTS`) so migrations stay standalone - the
same rule migration 374 states. A test asserts the two copies agree, because duplicated
literals drift.

Idempotent: re-running finds the row by name and re-asserts the activation. The partial unique
index `uq_scm_priority_policy_one_active` allows exactly one active policy, so the deactivation
runs first and the activation second, in one transaction.

Revision ID: 385_fulfilment_priority_fair
Revises: 384_committed_v_line_decision
"""
from alembic import op
import sqlalchemy as sa


revision = "385_fulfilment_priority_fair"
down_revision = "384_committed_v_line_decision"
branch_labels = None
depends_on = None


_FAIR_NAME = "Fair fulfilment priority (delivery date, document date, customer credit)"
_FAIR_FACTORS = {
    "po_document_sequence": 1.0,
    "demand_class": 3.0,
    "need_by_date": 3.0,
    "document_age": 1.0,
    "customer_credit": 1.0,
}
_FAIR_CLASS_WEIGHTS = {"project": 1.0, "retail": 0.4}

_FAIR_NOTES = (
    "Delivery date leads at 3.0, so the line due soonest wins; demand class stays at 3.0 so a "
    "purchase order owed to a customer still outranks one owed to nobody on the loading plan; "
    "document age and customer payment terms break what is left, and PO document sequence "
    "remains the final tie-break. A factor with no value is dropped from the average rather "
    "than scored zero, so an unassessed customer is neither the safest nor the riskiest."
)

#: The rows this revision may deactivate. Named rather than "everything currently active", so a
#: tenant who has already tuned and activated a policy of their own is not silently overridden -
#: they are left active and the fair row is seeded inactive beside them.
_REPLACEABLE = (
    "Today's rule (PO document sequence)",
    "Today's rule (demand owed, then PO document sequence)",
)


def _json(value: dict) -> str:
    """JSONB payloads as text, cast in the statement. `json` is imported here rather than at
    module scope so the file stays the shape every other revision in this tree has."""
    import json

    return json.dumps(value)


def _has_policy_table(bind) -> bool:
    return sa.inspect(bind).has_table("priority_policy", schema="scm")


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_policy_table(bind):
        return

    existing = bind.execute(
        sa.text(
            "SELECT id FROM scm.priority_policy WHERE name = :name "
            "ORDER BY created_at LIMIT 1"
        ),
        {"name": _FAIR_NAME},
    ).scalar()
    if existing is None:
        bind.execute(
            sa.text(
                "INSERT INTO scm.priority_policy "
                "(id, name, is_active, factors, demand_class_weights, notes) "
                "VALUES (gen_random_uuid(), :name, false, CAST(:factors AS jsonb), "
                "CAST(:classes AS jsonb), :notes)"
            ),
            {
                "name": _FAIR_NAME,
                "factors": _json(_FAIR_FACTORS),
                "classes": _json(_FAIR_CLASS_WEIGHTS),
                "notes": _FAIR_NOTES,
            },
        )

    # Only a policy nobody has tuned is displaced. If the active row is somebody's own, the
    # fair row is seeded and left inactive, and switching over stays their decision.
    active_name = bind.execute(
        sa.text("SELECT name FROM scm.priority_policy WHERE is_active LIMIT 1")
    ).scalar()
    if active_name is not None and active_name not in _REPLACEABLE:
        return

    # Activate by ID, never by name. Nothing makes the name unique, and a database that has
    # been re-seeded genuinely carries two rows under one name - activating "the fair policy"
    # by name then sets `is_active` on both and the one-active index refuses the whole
    # migration. Found by the downgrade test against the shared database, which holds exactly
    # that duplicate.
    fair_id = bind.execute(
        sa.text(
            "SELECT id FROM scm.priority_policy WHERE name = :name "
            "ORDER BY created_at LIMIT 1"
        ),
        {"name": _FAIR_NAME},
    ).scalar()
    if fair_id is None:
        return
    bind.execute(sa.text("UPDATE scm.priority_policy SET is_active = false WHERE is_active"))
    bind.execute(
        sa.text("UPDATE scm.priority_policy SET is_active = true WHERE id = :id"),
        {"id": fair_id},
    )


def downgrade() -> None:
    """Flip back: the previous rule becomes active again and the fair row stays, inactive."""
    bind = op.get_bind()
    if not _has_policy_table(bind):
        return

    # By id, for the same reason the upgrade activates by id: a name is not unique.
    previous_id = bind.execute(
        sa.text(
            "SELECT id FROM scm.priority_policy WHERE name = ANY(:names) "
            "ORDER BY created_at LIMIT 1"
        ),
        {"names": list(_REPLACEABLE)},
    ).scalar()
    bind.execute(
        sa.text("UPDATE scm.priority_policy SET is_active = false WHERE name = :name"),
        {"name": _FAIR_NAME},
    )
    if previous_id is not None:
        bind.execute(
            sa.text("UPDATE scm.priority_policy SET is_active = true WHERE id = :id"),
            {"id": previous_id},
        )
