"""Rename the project funnel's "Specified in" edge to "Spec in".

The seed only writes edge labels when it creates the funnel, so changing
``project_seed_service.DEFAULT_EDGES`` leaves every existing install reading the old
wording. Spec is short for specification, and "Spec in" is the phrase the trade actually
uses; "Specified in" reads as a past participle and nobody says it out loud.

Matched on the label rather than on the edge, so an admin who has already renamed it keeps
their wording, and re-running the migration changes nothing.

Revision ID: 324_spec_in_transition_label
Revises: 323_so_divergence_tables
"""
from alembic import op
import sqlalchemy as sa


revision = "324_spec_in_transition_label"
down_revision = "323_so_divergence_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "update status_transitions set label = 'Spec in' "
            "where entity_type = 'project' and label = 'Specified in'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "update status_transitions set label = 'Specified in' "
            "where entity_type = 'project' and label = 'Spec in'"
        )
    )
