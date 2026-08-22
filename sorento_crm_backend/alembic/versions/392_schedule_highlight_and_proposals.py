"""Delivery schedule: cell highlight, revision proposals, per-cell date override.

Section 9.7 of PLAN-so-book-diff-replanning.md - "the revision that is prose and
colour, not a new column". Three additive, nullable columns:

- ``delivery_schedule_cells.highlight`` (``#rrggbb``): the fill colour behind a
  cell when the document itself tints it.
- ``delivery_schedule_versions.revision_proposals`` (JSONB): the per-product
  re-date suggestion built from a page's highlighted cells plus its own margin
  note (proposed | accepted | rejected).
- ``delivery_schedule_cells.delivery_date_override``: written only when a
  proposal covering that cell is accepted; read ahead of the phase's own date
  by the revision-delta engine.

Revision ID: 392_schedule_highlight_and_proposals
Revises: 391_schedule_extractor_prompt_notes
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "392_schedule_highlight_and_proposals"
down_revision = "391_schedule_extractor_prompt_notes"
branch_labels = None
depends_on = None

_SCHEMA = "projects"


def upgrade() -> None:
    op.add_column(
        "delivery_schedule_cells",
        sa.Column("highlight", sa.String(7), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "delivery_schedule_cells",
        sa.Column("delivery_date_override", sa.Date(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "delivery_schedule_versions",
        sa.Column(
            "revision_proposals", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("delivery_schedule_versions", "revision_proposals", schema=_SCHEMA)
    op.drop_column("delivery_schedule_cells", "delivery_date_override", schema=_SCHEMA)
    op.drop_column("delivery_schedule_cells", "highlight", schema=_SCHEMA)
