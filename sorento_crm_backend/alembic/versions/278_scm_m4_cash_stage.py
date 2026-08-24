"""SCM M4 Slice A - cash stage: reorder_run.budget_amount + seed cash_ranking_policy.

The M0 schema (mig 273) already created ``scm.cash_ranking_policy`` (weights) and
``scm.reorder_recommendation`` already carries ``rank_score`` / ``rank`` /
``funding_status`` / ``cash_impact`` / ``unit_cost`` (mig 273). This migration adds
the ONE missing piece for the cash stage - the chosen budget persisted on the run  - 
and seeds the single active ``cash_ranking_policy`` row (idempotent) with the M4-D1
defaults (urgency + margin dominant): urgency .40 / margin .30 / abc .15 /
priority .10 / committed .05 (Σ = 1.00).

Both steps are idempotent: ``budget_amount`` is only added when absent, and the
policy seed only inserts when NO active row exists (mirrors
``reorder_engine.ensure_reorder_policy_defaults`` - never clobbers hand-edited
values on re-run or an already-seeded tenant).

Revision ID: 278_scm_m4_cash_stage
Revises: 277_scm_m3_reorder_run_cols
Create Date: 2026-07-16
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text


revision = "278_scm_m4_cash_stage"
down_revision = "277_scm_m3_reorder_run_cols"
branch_labels = None
depends_on = None


def _has_column(bind, schema: str, table: str, column: str) -> bool:
    cols = [c["name"] for c in inspect(bind).get_columns(table, schema=schema)]
    return column in cols


def upgrade() -> None:
    bind = op.get_bind()

    # 1) budget_amount on reorder_run - the budget the "Apply budget" action persists
    #    so a shared run shows one funded set. Additive, nullable, no backfill.
    if not _has_column(bind, "scm", "reorder_run", "budget_amount"):
        op.add_column(
            "reorder_run",
            sa.Column("budget_amount", sa.Numeric(15, 2), nullable=True),
            schema="scm",
        )

    # 2) seed the single active cash_ranking_policy row (idempotent).
    active = bind.execute(text(
        "SELECT count(*) FROM scm.cash_ranking_policy WHERE is_active = true"
    )).scalar() or 0
    if not active:
        bind.execute(text(
            "INSERT INTO scm.cash_ranking_policy "
            "(id, weight_urgency, weight_margin, weight_abc, weight_priority, "
            " weight_committed, is_active, note, source_system, source_ref, "
            " created_at, updated_at) "
            "VALUES (:id, 0.40, 0.30, 0.15, 0.10, 0.05, true, "
            " 'Default cash-ranking weights (M4-D1): urgency + margin dominant.', "
            " 'scm', 'defaults', now(), now())"
        ), {"id": str(uuid.uuid4())})


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "scm", "reorder_run", "budget_amount"):
        op.drop_column("reorder_run", "budget_amount", schema="scm")
    bind.execute(text(
        "DELETE FROM scm.cash_ranking_policy WHERE source_ref = 'defaults'"
    ))
