"""Merge the two heads created by merging origin/main into this branch.

main branched `295_chat_history_state_trace` off `294_chat_latency_percentile`;
this branch branched `295_drop_mcp_tool_ownership` (→ 296 → 297) off the SAME
parent. Merging main into the branch therefore leaves two alembic heads. This is
an empty merge revision that unifies them so `alembic upgrade head` resolves to a
single head again — no schema change of its own.

Revision ID: 298_merge_main_into_remove_mcp
Revises: 295_chat_history_state_trace, 297_audit_entity_id_text
"""

revision = "298_merge_main_into_remove_mcp"
down_revision = ("295_chat_history_state_trace", "297_audit_entity_id_text")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
