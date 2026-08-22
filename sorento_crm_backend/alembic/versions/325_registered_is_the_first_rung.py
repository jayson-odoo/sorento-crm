"""Make Registered the project funnel's starting rung, and move the projects sitting on Identified.

A project row cannot exist without a registration: registering is the write that creates it,
and the clash check runs there. Landing new projects on "Identified" therefore described a
state they were never in, and the pre-registration state already has its own record - a lead.

Two changes, both on the DEFAULT project graph only (``scope_id IS NULL``), so a fork an admin
built for a template keeps whatever they chose:

1. `is_initial` moves from Identified to Registered. Exactly one initial per graph is enforced
   by ``status_service.validate_graph``, so these two updates must both land or neither.
2. Projects still sitting on Identified move to Registered. They are there because it used to
   be the default landing rung, not because anybody decided it. Reversible: the downgrade puts
   them back.

Identified itself is kept. It stays a rung an admin can move a project BACK to - a registration
made in error, parked rather than deleted - which is why its backward edge survives too.

Revision ID: 325_registered_is_the_first_rung
Revises: 324_spec_in_transition_label
"""
from alembic import op
import sqlalchemy as sa


revision = "325_registered_is_the_first_rung"
down_revision = "324_spec_in_transition_label"
branch_labels = None
depends_on = None


def _rung_id(key: str) -> str | None:
    return (
        op.get_bind()
        .execute(
            sa.text(
                "select id from statuses "
                "where entity_type = 'project' and scope_id is null and key = :key"
            ),
            {"key": key},
        )
        .scalar()
    )


def _flip(initial_key: str, former_key: str) -> None:
    initial_id = _rung_id(initial_key)
    former_id = _rung_id(former_key)
    if not initial_id or not former_id:
        # A graph that never got the default funnel (or one an admin has renamed the keys of)
        # has nothing to flip. Idempotent by design.
        return

    bind = op.get_bind()
    bind.execute(
        sa.text("update statuses set is_initial = false where id = :id"), {"id": former_id}
    )
    bind.execute(
        sa.text("update statuses set is_initial = true where id = :id"), {"id": initial_id}
    )
    bind.execute(
        sa.text("update projects set status_id = :to_id where status_id = :from_id"),
        {"to_id": initial_id, "from_id": former_id},
    )


def upgrade() -> None:
    _flip(initial_key="registered", former_key="identified")


def downgrade() -> None:
    _flip(initial_key="identified", former_key="registered")
