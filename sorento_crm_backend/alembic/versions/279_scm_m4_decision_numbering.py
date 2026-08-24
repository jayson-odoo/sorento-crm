"""SCM M4 Slice B - decision + PO draft/confirm/GR flow numbering rules.

The M4 decision tables (``scm.recommendation_override``, ``cash_ranking_policy``,
``override_reason``, ``reason_action_map``) already exist from the M0 module schema
(mig 273); ``purchase_orders`` supports the ``draft_recommendation`` status (mig 273)
and ``scm.on_order_v`` already excludes drafts (mig 274). So Slice B needs NO column
migration.

The only new persistent artefact is two document-numbering rules the decision flow
reuses via ``NumberingService`` (the same helper that stamps SO/PO numbers, mig 274):

  * ``purchase_order_draft`` → ``PO-DRAFT-####`` - provisional number a draft PO
    (status ``draft_recommendation``) carries until it is confirmed. Confirm assigns
    the CANONICAL ``PO-{year}/{month:02d}-####`` from the existing ``purchase_order``
    rule (mig 274) - the draft number is throwaway, so it never resets.
  * ``goods_received`` → ``GR-######`` - the reference stamped on a goods receipt
    (``picking_headers`` ``picking_type='goods_received'``) created from an active PO.

Both seeds are idempotent (``ON CONFLICT (doc_type) DO NOTHING``) so re-running never
clobbers a hand-edited sequence.

Revision ID: 279_scm_m4_decision_numbering
Revises: 278_scm_m4_cash_stage
Create Date: 2026-07-16
"""
import uuid

from alembic import op
from sqlalchemy import text


revision = "279_scm_m4_decision_numbering"
down_revision = "278_scm_m4_cash_stage"
branch_labels = None
depends_on = None


_RULES = (
    # (doc_type, prefix_template, number_digits, start_value, reset_policy)
    ("purchase_order_draft", "PO-DRAFT-", 4, 1, "none"),
    ("goods_received", "GR-", 6, 100000, "none"),
)


def upgrade() -> None:
    bind = op.get_bind()
    now = text("now()")
    for doc_type, prefix, digits, start, reset in _RULES:
        bind.execute(
            text(
                """
                INSERT INTO document_numbering_rules
                    (id, doc_type, enabled, prefix_template, number_digits,
                     next_value, start_value, reset_policy, created_at, updated_at)
                VALUES (:id, :dt, true, :prefix, :digits, :start, :start, :reset, now(), now())
                ON CONFLICT (doc_type) DO NOTHING
                """
            ),
            {"id": str(uuid.uuid4()), "dt": doc_type, "prefix": prefix,
             "digits": digits, "start": start, "reset": reset},
        )


def downgrade() -> None:
    op.get_bind().execute(
        text("DELETE FROM document_numbering_rules WHERE doc_type = ANY(:d)"),
        {"d": [r[0] for r in _RULES]},
    )
