"""SO amendments: per-row accept/decline (PLAN-so-book-diff-replanning.md section 9.3).

Nullable JSONB map keyed by the delta row's ``row_key`` (its index within
``delta_json["rows"]``, which never reorders once the amendment is created):
``{"<row_key>": {"decision": "accepted" | "declined", "reason": "<text or null>"}}``.
Absent rows default to accepted, so today's all-or-nothing behaviour is unchanged.

Revision ID: 390_so_amendment_row_decisions
Revises: 389_item_classification_abc_by_demand_class
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "390_so_amendment_row_decisions"
down_revision = "389_item_classification_abc_by_demand_class"
branch_labels = None
depends_on = None

_TABLE = "so_amendments"
_SCHEMA = "projects"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("row_decisions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "row_decisions", schema=_SCHEMA)
