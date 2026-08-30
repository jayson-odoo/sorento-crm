"""A record action's entity id is a KEY, not necessarily a uuid (S6b).

`sla_form_actions.source_entity_id` was typed `uuid` because the only thing it ever held
was a form submission's id. S6b parks record actions on the same table, and three of the
records the sweep reaches are not keyed by a uuid at all:

* `scm.currency_rate`'s primary key IS the three-letter code, and the table has no
  surrogate id to fall back on.
* a stock-visibility policy at the access-type tier is addressed by `contact_access_types.code`
  (`dealer`), the same key its DELETE route takes.
* the sign-in background is a singleton setting, so the frontend names it by a constant
  rather than by an id no reader ever sees.

Parking any of those raised `invalid input syntax for type uuid` from inside the route -
a 500 on the click, for a button that looks like every other Delete. Widening the column
is one change; the alternative was five bespoke id remappings, each of which had to be
understood separately and none of which helped the sixth case.

Widening only. Every value already stored is a uuid string, which is valid text, so the
cast is total and no row moves. The partial unique index (one pending action per record)
and the sweep index are rebuilt by the type change and keep their meaning.

Revision ID: s6b_record_action_entity_id
Revises: s6_deferred_action_windows
"""
import sqlalchemy as sa
from alembic import op


revision = "s6b_record_action_entity_id"
down_revision = "s6_deferred_action_windows"
branch_labels = None
depends_on = None

TABLE = "sla_form_actions"
COLUMN = "source_entity_id"


def _column_type() -> str | None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": TABLE, "c": COLUMN},
    ).first()
    return row[0] if row else None


def upgrade() -> None:
    # Guarded like 445 and 446: this branch is applied to databases that converge through
    # `create_all` as well as through alembic, and re-typing an already-text column would
    # be a needless table rewrite.
    if _column_type() != "uuid":
        return
    op.execute(
        f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} TYPE VARCHAR(64) "
        f"USING {COLUMN}::text"
    )


def downgrade() -> None:
    # Only reversible while every value is still a uuid string. A row parked against a
    # currency code or the sign-in background's constant would fail the cast, and that is
    # the correct outcome: those actions cannot exist under the narrower type.
    if _column_type() == "uuid":
        return
    op.execute(
        f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} TYPE UUID "
        f"USING {COLUMN}::uuid"
    )
