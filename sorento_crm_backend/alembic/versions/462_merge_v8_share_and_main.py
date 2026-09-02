"""Rejoin ladder v8's policy migration with the two heads main was already carrying.

No DDL. Three lineages were open at once on 2 September 2026 and none of them
descends from the others:

    price tag r3 / reorder perf / spec labels  ---- 458_merge_xco_reorder_specs
    spec value labels + reorder replan         ---- 460_merge_spec_labels_replan
    fulfilment share + immediate window (S1)   ---- 460_fulfilment_immediate_share

`460_fulfilment_immediate_share` chains onto `456_reorder_perf_quickwins` and is
already RECORDED in the dev database, so it keeps its id: renumbering a landed
revision strands every database that wrote the old one down. This joins forward
instead, which is what `458_merge_xco_reorder_specs` and `372_merge_three_heads`
both did for the same reason.

Revision ID: 462_merge_v8_share_and_main
Revises: 458_merge_xco_reorder_specs, 460_merge_spec_labels_replan,
         460_fulfilment_immediate_share
Create Date: 2026-09-02 00:00:00.000000
"""
from __future__ import annotations

revision = "462_merge_v8_share_and_main"
down_revision = (
    "458_merge_xco_reorder_specs",
    "460_merge_spec_labels_replan",
    "460_fulfilment_immediate_share",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
