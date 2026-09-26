"""Chatbot memory lane A, S0 (chatbot-memory-lane-a-contract.md section 3/5/7).

One migration for the lane, per contract section 8 ruling 6:

* `conversation_frames.is_test` (D14's third named exception - a console dry run may
  write an `is_test = true` frame), an index for the newest-first per-contact-and-world
  read, and a unique functional index on the range's first turn id so
  `write_episode_for_reset`'s `ON CONFLICT DO NOTHING` insert is idempotent under a
  concurrent close.
* `respond_contacts.chatbot_memory_level` - the contact's own context level, NULL =
  follow the system default.
* `ai_assistant_usage_logs.chatbot_turn_id` - which `chatbot.turns` row a parser-usage
  row bills.
* `system_settings.chatbot_memory` reset to the new two-key shape (`enabled`,
  `default_level`) - the four dead keys the chatbot turn re-architecture shipped
  (`recall_default`/`episode_retention_days`/`profile_fields`/`focus_reset_events`) were
  never read by anything.

Every column here is also a plain model column (`app/models/access.py`,
`app/models/conversation_frame.py`, `app/models/ai_assistant.py`), and the two indexes
are declared in `ConversationFrame.__table_args__` - so `Base.metadata.create_all`
(the test suite's blank scratch schema) already carries all of it; this migration is
what a REAL migrated database needs.

Revision ID: mem_0001_frames_level
Revises: sales_0002_team_leader
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "mem_0001_frames_level"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

_NEW_CHATBOT_MEMORY = '{"enabled": false, "default_level": "full"}'
_OLD_CHATBOT_MEMORY = (
    '{"recall_default": false, "episode_retention_days": 180, '
    '"profile_fields": ["tier", "language", "default_ledgers"], '
    '"focus_reset_events": ["topic_switch"]}'
)


def upgrade() -> None:
    op.add_column(
        "conversation_frames",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "ix_conversation_frames_contact_test_last",
        "conversation_frames",
        ["contact_respond_id", "is_test", sa.text("last_activity_at DESC")],
    )
    # A functional expression index (`turn_ids[1]`) - `op.create_index` emits it
    # verbatim from the `sa.text(...)` element, matching `ConversationFrame.
    # __table_args__` so `create_all` and this migration build the identical index.
    op.create_index(
        "uq_conversation_frames_contact_test_first_turn",
        "conversation_frames",
        ["contact_respond_id", "is_test", sa.text("(turn_ids[1])")],
        unique=True,
    )

    op.add_column(
        "respond_contacts",
        sa.Column("chatbot_memory_level", sa.String(length=16), nullable=True),
    )

    op.add_column(
        "ai_assistant_usage_logs",
        sa.Column("chatbot_turn_id", sa.String(length=64), nullable=True),
    )

    # Idempotent: an UPDATE to a fixed literal produces the same row whether this
    # runs once or twice. Q1 ruling: no migration turns memory ON - `enabled` stays
    # false.
    op.execute(
        sa.text(
            f"UPDATE system_settings SET chatbot_memory = '{_NEW_CHATBOT_MEMORY}'::jsonb"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"UPDATE system_settings SET chatbot_memory = '{_OLD_CHATBOT_MEMORY}'::jsonb"
        )
    )
    op.drop_column("ai_assistant_usage_logs", "chatbot_turn_id")
    op.drop_column("respond_contacts", "chatbot_memory_level")
    op.drop_index("uq_conversation_frames_contact_test_first_turn", table_name="conversation_frames")
    op.drop_index("ix_conversation_frames_contact_test_last", table_name="conversation_frames")
    op.drop_column("conversation_frames", "is_test")
