"""Move workflow submission status onto the status engine (F1).

Replaces `workflow_submissions.current_state_code`, a VARCHAR fed by a state machine
embedded in `workflow_form_versions.schema`, with `status_id` pointing at the engine
(ADR-0001, ADR-0013). The transition log is re-keyed to status ids, the attribution
columns finally get their FKs, and the persisted list-query config that referenced the
dropped column is removed.

All five `workflow_*` tables hold 0 rows, so this is a reshape rather than a migration.
The backfill below still runs: if some environment does hold rows, mapping them by key
and failing loudly beats silently stamping every submission with the initial status.

Two deletes of persisted CONFIG, which is the part that is easy to miss because the
entity tables are empty (AC-F1-19):

* `list_query_fields` has a row compiling to `sub.current_state_code`, and
  `filter_compiler_adapters` resolves those with `getattr(WorkflowSubmission, name)`.
  Left in place, every filter or export request including that field raises
  AttributeError at runtime, on a deploy that changed no data. It is deleted rather than
  repointed: `status_key` is a Python property and not a column, so it cannot be
  compiled the same way, and `status_id` would mean asking a user to filter by UUID.
* `user_list_column_configs` for this module pin `current_state_code` as a column key.
  Two of the four are keyed to definition UUIDs that no longer exist. All are stale
  against the new grid, and a stale personalization blob renders as a missing column.

Rows are matched by predicate rather than by hardcoded id so this behaves the same in
every environment.

Revision ID: 311_wf_submission_status
Revises: 310_seed_complaint_graph
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "311_wf_submission_status"
down_revision = "310_seed_complaint_graph"
branch_labels = None
depends_on = None


_ATTRIBUTION_FKS = [
    # (table, column, constraint name)
    ("workflow_form_definitions", "created_by_user_id", "fk_wf_definitions_created_by_user"),
    ("workflow_form_versions", "created_by_user_id", "fk_wf_versions_created_by_user"),
    ("workflow_submissions", "created_by_user_id", "fk_wf_submissions_created_by_user"),
    ("workflow_submissions", "updated_by_user_id", "fk_wf_submissions_updated_by_user"),
    ("workflow_submission_transition_logs", "user_id", "fk_wf_transition_logs_user"),
]


def upgrade() -> None:
    bind = op.get_bind()

    # The graph must exist before anything can point at it.
    from app.services.workflow_submission_status_graph import (
        seed_workflow_submission_status_graph,
    )

    session = Session(bind=bind)
    try:
        seed_workflow_submission_status_graph(session)
        session.commit()
    finally:
        session.close()

    # ---- workflow_submissions.status_id ----
    op.add_column(
        "workflow_submissions",
        sa.Column("status_id", UUID(as_uuid=False), nullable=True),
    )

    # Nullable first, then backfill by KEY. The default graph's keys are the same
    # strings the old column held, so an existing row maps exactly rather than being
    # flattened onto the initial status.
    bind.execute(
        sa.text(
            """
            UPDATE workflow_submissions AS sub
               SET status_id = st.id
              FROM statuses AS st
             WHERE st.entity_type = 'workflow_submission'
               AND st.scope_id IS NULL
               AND st.key = sub.current_state_code
               AND sub.status_id IS NULL
            """
        )
    )

    unmapped = bind.execute(
        sa.text("SELECT count(*) FROM workflow_submissions WHERE status_id IS NULL")
    ).scalar()
    if unmapped:
        # Loud on purpose. Stamping these with the initial status would silently
        # rewrite real workflow state, which is worse than refusing to deploy.
        raise RuntimeError(
            f"{unmapped} workflow_submissions rows have a current_state_code with no "
            "matching status key in the default graph. Reconcile them before upgrading."
        )

    op.alter_column("workflow_submissions", "status_id", nullable=False)
    op.create_foreign_key(
        "fk_workflow_submissions_status",
        "workflow_submissions",
        "statuses",
        ["status_id"],
        ["id"],
    )
    op.create_index(
        "ix_workflow_submissions_status_id", "workflow_submissions", ["status_id"]
    )
    # Drops its index with it.
    op.drop_column("workflow_submissions", "current_state_code")

    # ---- transition log, re-keyed to status ids ----
    log = "workflow_submission_transition_logs"
    op.add_column(log, sa.Column("from_status_id", UUID(as_uuid=False), nullable=True))
    op.add_column(log, sa.Column("to_status_id", UUID(as_uuid=False), nullable=False))
    op.add_column(
        log, sa.Column("status_transition_id", UUID(as_uuid=False), nullable=True)
    )
    op.drop_column(log, "from_state_code")
    op.drop_column(log, "to_state_code")
    op.drop_column(log, "transition_id")

    # No ondelete on the status FKs: a status referenced by history must not be
    # deletable out from under it. The edge FK is SET NULL, because an admin editing a
    # graph legitimately deletes transitions and the trail must outlive that edit.
    op.create_foreign_key(
        "fk_wf_transition_logs_from_status", log, "statuses", ["from_status_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_wf_transition_logs_to_status", log, "statuses", ["to_status_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_wf_transition_logs_edge",
        log,
        "status_transitions",
        ["status_transition_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- attribution FKs (AC-F1-16) ----
    # Columns stay VARCHAR: users.id is a text column, and a uuid column cannot hold an
    # FK to it. Converting users.id belongs to the uuid-id principle work, not here.
    for table, column, name in _ATTRIBUTION_FKS:
        op.create_foreign_key(
            name, table, "users", [column], ["id"], ondelete="SET NULL"
        )

    # ---- persisted config that would break on a code-only deploy ----
    bind.execute(
        sa.text(
            """
            DELETE FROM list_query_fields
             WHERE compile_key = 'sub.current_state_code'
                OR (field_key = 'current_state_code'
                    AND resource_id IN (SELECT id FROM list_query_resources
                                         WHERE resource_key = 'workflow_form_submissions'))
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM user_list_column_configs
             WHERE listing_key LIKE '/workflow-forms-management/%'
            """
        )
    )


def downgrade() -> None:
    """Not reversible in a useful way.

    Restoring `current_state_code` is mechanical, but the state machine that gave those
    codes meaning was deleted from the schema document by this slice, so the column
    would come back with nothing to interpret it. Recovery is to restore from a backup
    taken before the upgrade.
    """
    raise NotImplementedError(
        "311_wf_submission_status is not reversible: the schema-embedded state machine "
        "that gave current_state_code its meaning no longer exists. Restore from backup."
    )
