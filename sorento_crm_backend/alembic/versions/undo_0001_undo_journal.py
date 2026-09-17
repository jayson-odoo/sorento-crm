"""Undo last confirm on the fulfilment planning board: the journal column.

Revision ID: undo_0001_undo_journal
Revises: 512_committed_v_redirect_exclude
Create Date: 2026-09-17

`PLAN-board-undo-last-confirm.md` S1 (#978): every board Confirm now runs inside a
journal that records what the unit of work is about to do, so a later undo can replay
it backwards. One column, no table (PRINCIPLES: one preference does not need a table) -
the journal belongs to the decision it was minted for, and its own insert is correctly
part of the journal (replay deletes it).

Nullable and JSONB: a decision minted anywhere other than the two board confirm routes
(`uncover_lines`, a pre-lane revision) carries no journal and is simply not undoable.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "undo_0001_undo_journal"
down_revision = "512_committed_v_redirect_exclude"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "so_supply_decisions",
        sa.Column("undo_journal", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="projects",
    )


def downgrade() -> None:
    op.drop_column("so_supply_decisions", "undo_journal", schema="projects")
