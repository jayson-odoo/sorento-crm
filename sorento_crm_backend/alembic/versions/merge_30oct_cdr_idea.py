"""Join the heads left on main by the #1625 and #1980 merges.

#1625 landed `idea_capture_fields_0001` hung off `pmt_0001_parser_max_tokens`
(#1970); #1980 then landed `cdr_0001_chat_delivery_trace`, whose down_revision is
the same `pmt_0001_parser_max_tokens`, so main carried two heads. Schema-free
merge point; ITEM-CLASS (`item_class_0001`) hangs off it.

Revision ID: merge_30oct_cdr_idea
Revises: cdr_0001_chat_delivery_trace, idea_capture_fields_0001
"""
from __future__ import annotations

revision = "merge_30oct_cdr_idea"
down_revision = ("cdr_0001_chat_delivery_trace", "idea_capture_fields_0001")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
