"""Reorder plan Re-plan supersede link (PLAN-scm-reorder-oi-feedback-1sep.md S5, G8).

Two nullable self-referential columns on ``scm.reorder_run`` so a re-planned run can point
both ways: ``supersedes_run_id`` is stamped on the NEW run at creation (the RQ job needs it to
find the old run's decisions to carry once its own recommendations exist); ``superseded_by_run_id``
is stamped on the OLD run once the new run actually completes, so a still-running or failed
re-plan never makes the old (still-valid) run look superseded.

No new table - a run's whole history is two columns and a self-join, and the plan doc names
this as the "simplest thing that works" option explicitly.

Numbering note: four lanes minted a "454" independently the same night. The captain assigned
the batch's real order as 454 (S1, order_inquiry_born_ack) -> 455 (S4, saved_views_and_perms)
-> 456 (S3, reorder_perf_quickwins) -> 457 (this one). ``down_revision`` was pinned to 453 (this
PR's actual base) while 456 did not yet exist on this branch - pointing at a missing revision
breaks the alembic graph load and fails CI. S3 (#491) has since merged, so this merge flips it to
its real chain position, "456_reorder_perf_quickwins", leaving exactly one head.

Revision ID: 457_reorder_replan
Revises: 456_reorder_perf_quickwins
"""
from alembic import op
import sqlalchemy as sa

revision = "457_reorder_replan"
down_revision = "456_reorder_perf_quickwins"
branch_labels = None
depends_on = None


def _columns(table: str, schema: str) -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = :s"
            ),
            {"t": table, "s": schema},
        )
    }


def upgrade() -> None:
    cols = _columns("reorder_run", "scm")
    if "supersedes_run_id" not in cols:
        op.add_column(
            "reorder_run",
            sa.Column(
                "supersedes_run_id",
                sa.dialects.postgresql.UUID(as_uuid=False),
                nullable=True,
            ),
            schema="scm",
        )
        op.create_foreign_key(
            "fk_scm_reorder_run_supersedes_run_id",
            "reorder_run",
            "reorder_run",
            ["supersedes_run_id"],
            ["id"],
            source_schema="scm",
            referent_schema="scm",
            ondelete="SET NULL",
        )
    if "superseded_by_run_id" not in cols:
        op.add_column(
            "reorder_run",
            sa.Column(
                "superseded_by_run_id",
                sa.dialects.postgresql.UUID(as_uuid=False),
                nullable=True,
            ),
            schema="scm",
        )
        op.create_foreign_key(
            "fk_scm_reorder_run_superseded_by_run_id",
            "reorder_run",
            "reorder_run",
            ["superseded_by_run_id"],
            ["id"],
            source_schema="scm",
            referent_schema="scm",
            ondelete="SET NULL",
        )


def downgrade() -> None:
    cols = _columns("reorder_run", "scm")
    if "superseded_by_run_id" in cols:
        op.drop_constraint(
            "fk_scm_reorder_run_superseded_by_run_id", "reorder_run",
            schema="scm", type_="foreignkey",
        )
        op.drop_column("reorder_run", "superseded_by_run_id", schema="scm")
    if "supersedes_run_id" in cols:
        op.drop_constraint(
            "fk_scm_reorder_run_supersedes_run_id", "reorder_run",
            schema="scm", type_="foreignkey",
        )
        op.drop_column("reorder_run", "supersedes_run_id", schema="scm")
