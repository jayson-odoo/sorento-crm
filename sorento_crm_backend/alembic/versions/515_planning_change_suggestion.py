"""`projects.planning_change_rows` gains `suggestion_json`; the retired decisions are remapped.

`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`, Slice C contract D. A
change is a re-run at the new state diffed against what the line holds, and that diff IS
the suggestion, so the row stores it (`suggestion_json`) instead of the rule table's verb.
The verb columns (`suggested` / `why`) are NOT dropped - a batch is a record (AC-R10) and
every row written before this migration carries its own reaction in them - they simply
lose their NOT NULL, because nothing writes them again.

`decision` is remapped in the same pass: `accept` / `keep` -> `confirm`, `board` -> NULL.
`accept` existed because the suggestion was a verb a row could agree with, and agreeing
with a verb executed nothing; `board` ("leave it on the board") is what an undecided row
already means. The remap is ONE-WAY on purpose, and the downgrade says so rather than
pretending otherwise: `board` collapsing to NULL cannot be told apart afterwards from a
row that was always NULL.

The DML half is built with SQLAlchemy Core against the mapped `PlanningChangeRow.__table__`
for 513's own Reviewer S2 reason (a scratch-schema test's `schema_translate_map` rewrites
the `projects` schema on Core/ORM constructs, and a raw string naming the schema would
silently write into whichever real `projects` tables the test runs against). The DDL half
CANNOT use that trick - a translate map does not reach an `ALTER TABLE` - so the effective
schema is resolved off the bind's own execution options first, and the statement names
that. Idempotent both ways (`IF NOT EXISTS` / `IF EXISTS`), because the scratch schema is
built from the model and therefore already has the column when the test calls `apply`.

Revision ID: 515_planning_change_suggestion
Revises: 514_plan_change_kind_cancelled
Create Date: 2026-09-13
"""
import sqlalchemy as sa
from alembic import op

from app.models.planning_change import PlanningChangeRow

revision = "515_planning_change_suggestion"
down_revision = "514_plan_change_kind_cancelled"
branch_labels = None
depends_on = None


def _qualified(bind) -> str:
    """`"<schema>"."planning_change_rows"`, with the schema the BIND actually writes to.

    A scratch-schema test hands this function a connection carrying
    `schema_translate_map={"projects": "zzs_blank_..._projects"}`; SQLAlchemy applies that
    map when it compiles a Core construct, and not at all to DDL text. Reading it back off
    the connection is what keeps `ALTER TABLE` in the same schema as the UPDATE below.
    """
    table = PlanningChangeRow.__table__
    options = bind.get_execution_options() if hasattr(bind, "get_execution_options") else {}
    translate = (options or {}).get("schema_translate_map") or {}
    schema = translate.get(table.schema, table.schema)
    return f'"{schema}"."{table.name}"'


def apply(bind) -> None:
    rows = PlanningChangeRow.__table__
    target = _qualified(bind)
    bind.exec_driver_sql(
        f"ALTER TABLE {target} ADD COLUMN IF NOT EXISTS suggestion_json JSONB"
    )
    # Nothing writes these two again (`compose_suggestion` replaced `suggest()`), so a row
    # built from now on leaves them NULL and the NOT NULL would refuse every new batch.
    bind.exec_driver_sql(f"ALTER TABLE {target} ALTER COLUMN suggested DROP NOT NULL")
    bind.exec_driver_sql(f"ALTER TABLE {target} ALTER COLUMN why DROP NOT NULL")
    bind.execute(
        sa.update(rows)
        .where(rows.c.decision.in_(("accept", "keep")))
        .values(decision="confirm")
    )
    bind.execute(
        sa.update(rows).where(rows.c.decision == "board").values(decision=None)
    )


def revert(bind) -> None:
    """Drops the column only.

    The decision remap is deliberately NOT reversed (see the module docstring), and the two
    retired columns stay nullable: rows written after this migration have NULL in both, so
    restoring their NOT NULL would fail on the data the upgrade itself created.
    """
    bind.exec_driver_sql(f"ALTER TABLE {_qualified(bind)} DROP COLUMN IF EXISTS suggestion_json")


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
