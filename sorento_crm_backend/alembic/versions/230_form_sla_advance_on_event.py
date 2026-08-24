"""Form SLA: advance_on_event - spawn the next stage only on a specific resolve event.

Lets a stage close on multiple resolve events (e.g. 'approved,rejected') while
advancing to the next stage (next_config_id) only on one of them (e.g. 'approved'),
so rejected complaints don't spawn the customer-service stage. NULL = advance on
any resolve (backward-compatible).

Revision ID: 230_form_sla_advance_on_event
Revises: 229_seed_complaint_numbering
Create Date: 2026-06-09
"""

import sqlalchemy as sa
from alembic import op


revision = "230_form_sla_advance_on_event"
down_revision = "229_seed_complaint_numbering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("form_sla_configs", sa.Column("advance_on_event", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("form_sla_configs", "advance_on_event")
