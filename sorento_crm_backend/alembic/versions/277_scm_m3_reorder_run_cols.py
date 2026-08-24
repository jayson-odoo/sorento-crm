"""SCM M3 - reorder-run lifecycle + recommendation freeze columns.

The M0 schema created ``scm.reorder_run`` / ``scm.reorder_recommendation`` with the
core shape but without the run-lifecycle + frozen-input columns the M3 run job needs:

  * ``scm.reorder_run``: ``started_at`` / ``finished_at`` / ``error_text`` /
    ``run_log`` (JSONB counts {stage, buy, disposition, exceptions,
    total_cash_impact, recommendation_count, duration_ms}) - mirrors
    ``scm.scm_analytics_run`` so a crash still leaves a 'failed'+error trace.
  * ``scm.reorder_recommendation``: ``rec_type`` (buy|disposition|exception - 
    the discriminator the results grid filters/counts on) + ``inputs`` (JSONB
    freeze bag carrying every frozen input that has no dedicated typed column:
    reason enum, min/max qty, order_up_to, safety_stock(+method),
    lead_time(+source), policy_ref, chosen supplier + alternatives, sample_size,
    disposition_action, transfer_flag, plus the raw engine inputs that reproduce
    ROP/qty - AC-M3.11). The existing ``allocation`` JSONB keeps the network
    per-warehouse breakdown.

All columns are nullable - additive, no backfill.

Revision ID: 277_scm_m3_reorder_run_cols
Revises: 276_seed_scm_analytics_task
Create Date: 2026-07-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "277_scm_m3_reorder_run_cols"
down_revision = "276_seed_scm_analytics_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reorder_run", sa.Column("started_at", sa.DateTime(timezone=False), nullable=True), schema="scm")
    op.add_column("reorder_run", sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True), schema="scm")
    op.add_column("reorder_run", sa.Column("error_text", sa.Text(), nullable=True), schema="scm")
    op.add_column("reorder_run", sa.Column("run_log", JSONB(), nullable=True), schema="scm")

    op.add_column("reorder_recommendation", sa.Column("rec_type", sa.String(length=20), nullable=True), schema="scm")
    op.add_column("reorder_recommendation", sa.Column("inputs", JSONB(), nullable=True), schema="scm")
    op.create_index(
        "ix_scm_reorder_recommendation_rec_type",
        "reorder_recommendation",
        ["run_id", "rec_type"],
        schema="scm",
    )


def downgrade() -> None:
    op.drop_index("ix_scm_reorder_recommendation_rec_type", table_name="reorder_recommendation", schema="scm")
    op.drop_column("reorder_recommendation", "inputs", schema="scm")
    op.drop_column("reorder_recommendation", "rec_type", schema="scm")

    op.drop_column("reorder_run", "run_log", schema="scm")
    op.drop_column("reorder_run", "error_text", schema="scm")
    op.drop_column("reorder_run", "finished_at", schema="scm")
    op.drop_column("reorder_run", "started_at", schema="scm")
