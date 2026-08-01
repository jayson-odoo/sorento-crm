"""Form SLA reaches workflow submissions, scoped per definition (F2a).

Adds `form_sla_configs.definition_id` and seeds one stage for `workflow_submission`.

**Why the scope column.** `emit_event` selects every active config for an entity TYPE, and
`workflow_submission` is one type for every form definition, so a single chain would apply
identically to an RMA form, a warranty claim and a satisfaction survey. Worse,
`start_event` names status KEYS, and keys are deliberately shared across forked graphs, so
a forked definition that renames a rung silently stops matching while one that reuses a key
inherits another form's stage. NULL means "every definition", so the five pre-existing form
types are untouched.

**The unique index has to widen with it.** Migration 178 created
`uq_form_sla_configs_type_stage_active` on `(source_entity_type, stage_code) WHERE
is_active`. Adding the column alone leaves the scope unusable: two definitions each wanting
a stage called `main` collide. Coalescing NULL to a sentinel keeps the old guarantee inside
each scope (including the NULL scope, where two rows must still collide) while letting
different definitions reuse a stage name. This was missed when the slice was specified and
found by writing the tests.

The stage itself is seeded through the same function the app and tests use, not restated as
SQL: the house idiom for seeds is raw SQL (see `179_seed_form_sla_overdue_scan`), but
restating the stage shape here would re-create exactly the drift the seeder exists to
prevent (ADR-0013 rule 10).

**The seeded stage is inert until an admin configures tier teams** for the
`workflow_submission` agent under team set `main`. A migration cannot invent team members,
and the failure mode is silent: `_start_for_config` raises a 422 that `emit_event` swallows.
After-sales S1 owns that configuration.

Revision ID: 313_wf_submission_sla
Revises: 312_wf_line_status
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "313_wf_submission_sla"
down_revision = "312_wf_line_status"
branch_labels = None
depends_on = None

_TABLE = "form_sla_configs"
_UQ = "uq_form_sla_configs_type_stage_active"
# Any constant uuid works; it only has to be a value no real definition_id can take.
_NULL_SCOPE = "00000000-0000-0000-0000-000000000000"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set:
    return {c["name"] for c in _inspector().get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # Defensive, like 311 and 312: the shared development database is stamped on another
    # worktree's chain and cannot be brought forward, so columns get applied there by hand.
    if "definition_id" not in _columns(_TABLE):
        op.add_column(_TABLE, sa.Column("definition_id", UUID(as_uuid=False), nullable=True))

    fks = {fk.get("name") for fk in _inspector().get_foreign_keys(_TABLE)}
    if "fk_form_sla_configs_definition_id" not in fks:
        # CASCADE: a stage scoped to a deleted definition is meaningless, and leaving it
        # behind would make it fire for nothing.
        op.create_foreign_key(
            "fk_form_sla_configs_definition_id",
            _TABLE,
            "workflow_form_definitions",
            ["definition_id"],
            ["id"],
            ondelete="CASCADE",
        )

    indexes = {ix["name"] for ix in _inspector().get_indexes(_TABLE)}
    if "ix_form_sla_configs_definition_id" not in indexes:
        op.create_index("ix_form_sla_configs_definition_id", _TABLE, ["definition_id"])

    # Widen the active-stage uniqueness to include the scope. Expression index, so it is
    # created with raw SQL rather than op.create_index.
    bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ}"))
    bind.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX {_UQ}
                ON {_TABLE} (
                    source_entity_type,
                    stage_code,
                    COALESCE(definition_id, '{_NULL_SCOPE}'::uuid)
                )
             WHERE is_active = true
            """
        )
    )

    from app.services.workflow_submission_sla import seed_workflow_submission_sla_configs

    session = Session(bind=bind)
    try:
        seed_workflow_submission_sla_configs(session)  # flushes only
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    """Restores the narrower unique index and drops the column.

    The seeded policy, agent and stage rows are left: they are inert configuration that a
    re-run of `upgrade` converges, and deleting a stage would orphan any tracker that
    already points at it.
    """
    bind = op.get_bind()
    bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ}"))
    bind.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX {_UQ}
                ON {_TABLE} (source_entity_type, stage_code)
             WHERE is_active = true
            """
        )
    )

    indexes = {ix["name"] for ix in _inspector().get_indexes(_TABLE)}
    if "ix_form_sla_configs_definition_id" in indexes:
        op.drop_index("ix_form_sla_configs_definition_id", table_name=_TABLE)

    fks = {fk.get("name") for fk in _inspector().get_foreign_keys(_TABLE)}
    if "fk_form_sla_configs_definition_id" in fks:
        op.drop_constraint("fk_form_sla_configs_definition_id", _TABLE, type_="foreignkey")

    if "definition_id" in _columns(_TABLE):
        op.drop_column(_TABLE, "definition_id")
