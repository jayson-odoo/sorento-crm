"""A brand can be marked as not flowing to purchasing

Revision ID: bftp_0001_flows_to_purchasing
Revises: 526_chatbot_media_attach_type
Create Date: 2026-09-23 00:00:00.000000

`PLAN-brand-flows-to-purchasing.md` (owner ruling 22 Sep 2026, R4-R7). TP Enterprise is
bought locally by CS and must never reach purchasing; the supplier-country rule from #814
was the wrong key for this (Mocha is a local supplier whose items DO sometimes go to
purchasing), so the brand itself is the switch. Default `true` so nothing changes for an
existing brand until an admin flips one.

NOTE ON `down_revision`: the plan named `spec_vocab_close_couple` as main's head at
write time (22 Sep 2026, `2280975f9`); `525_committed_v_orderback` landed on top of it
since (`bcdf0e192`, the worktree's base), and `alembic heads` on this checkout showed
that single revision as the real current head, so this migration re-parents onto it
rather than the stale name in the plan.
"""
import sqlalchemy as sa
from alembic import op

revision = "bftp_0001_flows_to_purchasing"
down_revision = "526_chatbot_media_attach_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "brands",
        sa.Column(
            "flows_to_purchasing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("brands", "flows_to_purchasing")
