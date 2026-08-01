"""Status and disposition on submission lines, plus the derived-header config (F1a).

Lines gain `status_id` (nullable: line status is opt-in per definition), `disposition`
and `disposition_reason`. Definitions gain the derivation opt-in: one boolean plus two
status KEYS, never ids, because a definition that forks its header graph re-keys every
id for the same rungs, so a stored id would resolve to nothing the moment it forked.

No backfill. Every existing line legitimately holds `status_id IS NULL`, because no
definition derives yet and the flag defaults off.

**Written defensively on purpose.** These columns are applied by hand to the shared local
development database, which is stamped on another worktree's chain and so cannot be
brought forward with `alembic upgrade`. A plain `add_column` would abort there on a
column that already exists. The repo already carries this pattern for the same reason
(see `305`/`306`, made resilient to legacy schema drift). Being idempotent also makes a
re-run after a partial failure safe, which a plain DDL script is not.

Revision ID: 312_wf_line_status
Revises: 311_wf_submission_status
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "312_wf_line_status"
down_revision = "311_wf_submission_status"
branch_labels = None
depends_on = None


_LINES = "workflow_submission_lines"
_DEFS = "workflow_form_definitions"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set:
    return {c["name"] for c in _inspector().get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if name not in {ix["name"] for ix in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def _create_fk_if_missing(name: str, table: str, referent: str, local: list, remote: list) -> None:
    existing = {fk.get("name") for fk in _inspector().get_foreign_keys(table)}
    if name not in existing:
        # No ondelete: a status a line holds must not be deletable out from under it.
        # That is what count_records and migrate_records exist to mediate.
        op.create_foreign_key(name, table, referent, local, remote)


def upgrade() -> None:
    _add_column_if_missing(_LINES, sa.Column("status_id", UUID(as_uuid=False), nullable=True))
    _add_column_if_missing(_LINES, sa.Column("disposition", sa.String(length=150), nullable=True))
    # Free text rather than a lookup: R3's "nothing to collect" needs a reason, and the
    # reason is prose, not a code.
    _add_column_if_missing(_LINES, sa.Column("disposition_reason", sa.Text(), nullable=True))
    _create_index_if_missing("ix_workflow_submission_lines_status_id", _LINES, ["status_id"])
    _create_fk_if_missing(
        "fk_workflow_submission_lines_status", _LINES, "statuses", ["status_id"], ["id"]
    )

    # Derivation opt-in. NOT NULL with a server default so every existing definition is
    # explicitly off rather than ambiguously null.
    _add_column_if_missing(
        _DEFS,
        sa.Column(
            "derives_status_from_lines",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    _add_column_if_missing(_DEFS, sa.Column("derived_open_status_key", sa.String(length=64), nullable=True))
    _add_column_if_missing(
        _DEFS, sa.Column("derived_resolved_status_key", sa.String(length=64), nullable=True)
    )

    # Seeds go through the same functions the app and its tests use, so the graph and the
    # lookup cannot drift between what a test asserts and what a deploy creates
    # (ADR-0013 rule 10). Both converge on a re-run rather than inserting again.
    from app.services.workflow_submission_line_disposition import (
        seed_workflow_submission_line_disposition_lookup,
    )
    from app.services.workflow_submission_line_status_graph import (
        seed_workflow_submission_line_status_graph,
    )

    session = Session(bind=op.get_bind())
    try:
        seed_workflow_submission_line_status_graph(session)
        # After the column exists: attaching a lookup binding validates existing values
        # in the bound column.
        seed_workflow_submission_line_disposition_lookup(session)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    """Drops the columns. The seeded graph and lookup rows are deliberately left.

    They are inert configuration that a re-run of `upgrade` converges, and deleting a
    status graph would strand any line still referencing it.
    """
    for table, name in (
        (_LINES, "fk_workflow_submission_lines_status"),
    ):
        existing = {fk.get("name") for fk in _inspector().get_foreign_keys(table)}
        if name in existing:
            op.drop_constraint(name, table, type_="foreignkey")

    if "ix_workflow_submission_lines_status_id" in {
        ix["name"] for ix in _inspector().get_indexes(_LINES)
    }:
        op.drop_index("ix_workflow_submission_lines_status_id", table_name=_LINES)

    for table, columns in (
        (_LINES, ("status_id", "disposition", "disposition_reason")),
        (_DEFS, ("derives_status_from_lines", "derived_open_status_key", "derived_resolved_status_key")),
    ):
        present = _columns(table)
        for column in columns:
            if column in present:
                op.drop_column(table, column)
