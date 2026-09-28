"""Finance S1: a billing document's sales order type, and the parser that can say "invoiced".

Plan: documentation/plans/finance/PLAN-finance-billing-documents-27sep.md 3.4, round 3
(#1309). The owner's ruling Q14 ("2 by the sales order type") puts the invoiced basis in the
same DEALER and PROJECT TEAM blocks as the order bases, read off the demand class. A billing
document has no order type of its own, so it stores the one the ingest decides:

1. `finance.billing_documents.demand_class`, nullable, with the closed vocabulary's CHECK
   built by `demand_class.check_constraint_sql` (the `sales_agents` one), so the model and
   this migration cannot disagree. No backfill: S0 has not shipped, and a row already on a
   hand-test database is re-decided by its next push (a push is the whole document).
2. The chatbot parser prompt republished (its body now teaches `sales_basis` "invoiced",
   UAC S1-6) and the `production` label moved onto it, `sales_s1_reports_module`'s
   `republish_and_promote` loaded by path and run under this revision's own marker key
   (the owner ruling of 21 Sep 2026: the deploy ships the config).

Downgrade drops the column and its CHECK, and moves the label back to where this revision
found it. The published version itself stays (versions are immutable; `chatbot_rearch_s4`).

Revision ID: fin_0002_billing_demand_class
Revises: fin_0001_billing_documents
Create Date: 2026-09-27
"""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.sales import translated_schema
from app.services.scm.demand_class import check_constraint_sql

revision = "fin_0002_billing_demand_class"
down_revision = "fin_0001_billing_documents"
branch_labels = None
depends_on = None

SCHEMA = "finance"
TABLE = "billing_documents"
CHECK = "ck_finance_billing_documents_demand_class"
PROMPT_NAME = "chatbot_semantic_parser"
#: Stamped on the version this revision promotes: where `production` pointed before.
PRIOR_PRODUCTION_KEY = "fin_0002_prior_production_version_id"


def _load_sales_s1():
    """`sales_s1_reports_module`, for its republish-and-promote (the chatbot_rearch_s12
    precedent: reuse a sibling migration, never restate it). Importing runs no DDL."""
    spec = importlib.util.spec_from_file_location(
        "_fin_0002_sales_s1", Path(__file__).resolve().parent / "sales_s1_reports_module.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def republish_parser(bind) -> None:
    """Publish today's parser (constant plus policy blocks) and point `production` at it,
    recording the version it pointed at before under this revision's key."""
    sales_s1 = _load_sales_s1()
    sales_s1.PRIOR_PRODUCTION_KEY = PRIOR_PRODUCTION_KEY
    sales_s1.republish_and_promote(bind)


def restore_parser_label(bind) -> None:
    """Move `production` back to the version this revision found it on, if it still points
    at the one this revision promoted."""
    session = Session(bind=bind)
    try:
        label = (
            session.query(AIPromptLabel)
            .filter(AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production")
            .first()
        )
        promoted = (
            session.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).first()
            if label is not None
            else None
        )
        if promoted is None:
            return
        config = dict(promoted.config_json or {})
        prior_id = config.pop(PRIOR_PRODUCTION_KEY, None)
        if prior_id:
            promoted.config_json = config
            label.version_id = prior_id
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upgrade() -> None:
    bind = op.get_bind()
    # `finance`, or the migration test's scratch copy of it: alembic's ALTER TABLE ignores
    # `schema_translate_map`, so the schema is named explicitly (`sales_0002_team_leader`).
    schema = translated_schema(bind, SCHEMA)
    op.add_column(TABLE, sa.Column("demand_class", sa.String(32), nullable=True), schema=schema)
    op.create_check_constraint(CHECK, TABLE, check_constraint_sql(), schema=schema)
    republish_parser(bind)


def downgrade() -> None:
    bind = op.get_bind()
    schema = translated_schema(bind, SCHEMA)
    restore_parser_label(bind)
    op.drop_constraint(CHECK, TABLE, type_="check", schema=schema)
    op.drop_column(TABLE, "demand_class", schema=schema)
