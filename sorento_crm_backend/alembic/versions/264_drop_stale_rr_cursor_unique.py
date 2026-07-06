"""drop stale 2-col unique on agent_team_round_robin_cursors

Migration 263 meant to "swap the 2-col unique for a 3-col unique including
segment_key", but it dropped the wrong object: it ran
``DROP INDEX IF EXISTS ix_agent_team_round_robin_cursors_agent_team`` while the
real uniqueness was a table CONSTRAINT named ``uq_agent_team_cursor`` on
(agent_id, team_id). The DROP no-op'd, so the 2-col unique survived alongside
the new 3-col index — capping each (agent, team) at ONE cursor row. That breaks
segment-scoped round-robin: the moment a team needs a second cursor (a different
``segment_key`` — e.g. a '' legacy cursor plus a 'retail' cursor, or 'retail'
plus 'project'), the insert 409s with UniqueViolation on uq_agent_team_cursor.

This migration drops the stale constraint (and its backing index) idempotently.
The 3-col unique index ``ix_agent_team_rr_cursors_agent_team_segment`` (created
in 263) is the sole uniqueness guarantee going forward — matching the model.

Revision ID: 264_drop_stale_rr_cursor_unique
Revises: 263_market_segments
"""
from alembic import op


revision = "264_drop_stale_rr_cursor_unique"
down_revision = "263_market_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Constraint form (Postgres auto-creates a backing index of the same name;
    # dropping the constraint drops the index).
    op.execute(
        "ALTER TABLE agent_team_round_robin_cursors "
        "DROP CONSTRAINT IF EXISTS uq_agent_team_cursor"
    )
    # Belt-and-suspenders: if any env carried it as a plain unique index instead
    # of a constraint, drop that too. Also clean the mis-named index 263 targeted.
    op.execute("DROP INDEX IF EXISTS uq_agent_team_cursor")
    op.execute("DROP INDEX IF EXISTS ix_agent_team_round_robin_cursors_agent_team")
    # Ensure the intended 3-col unique exists (263 created it; idempotent safety).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_team_rr_cursors_agent_team_segment "
        "ON agent_team_round_robin_cursors (agent_id, team_id, segment_key)"
    )


def downgrade() -> None:
    # Best-effort restore of the old 2-col unique. Only succeeds if no team has
    # more than one segment cursor (else the unique can't be built) — acceptable
    # for a downgrade path.
    op.execute(
        "ALTER TABLE agent_team_round_robin_cursors "
        "ADD CONSTRAINT uq_agent_team_cursor UNIQUE (agent_id, team_id)"
    )
