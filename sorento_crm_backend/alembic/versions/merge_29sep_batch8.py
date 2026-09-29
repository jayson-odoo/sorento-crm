"""Join the heads left on main by the #1145, #1329, #1372 and #1373 merges.

All four landed a single revision hung off `ideation_status_events_s1` (#1357,
itself on `merge_29sep_batch7`): #1145 `527_committed_v_uncapped`, #1329
`eta1_0001_contact_eta_offset`, #1372 `spo_cascade_0001_set_null`, #1373
`chatbot_po_spo_warehouse_vocab`, so main carried four heads. Schema-free
merge point.

Revision ID: merge_29sep_batch8
Revises: 527_committed_v_uncapped, chatbot_po_spo_warehouse_vocab,
         eta1_0001_contact_eta_offset, spo_cascade_0001_set_null
"""
from __future__ import annotations

revision = "merge_29sep_batch8"
down_revision = (
    "527_committed_v_uncapped",
    "chatbot_po_spo_warehouse_vocab",
    "eta1_0001_contact_eta_offset",
    "spo_cascade_0001_set_null",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
