"""Rejoin the three lanes that each cut their own head off 453_shared_brand_attach.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at - same shape as `372_merge_three_heads`, same reason: three
branches were open at once, each cut its own chain onto the same tip, and
each landed on `integration/price-tag-r2` without knowing about the others.

    price-tag-r3-fix-xco  ---- 457_ptag_line_xco_repair
    reorder perf/S4        ---- 456_reorder_perf_quickwins
    spec registry labels    ---- 455_spec_registry_value_labels

Join forward, never renumber a landed revision - rewriting one strands every
database that already recorded the old id.

Revision ID: 458_merge_xco_reorder_specs
Revises: 457_ptag_line_xco_repair, 456_reorder_perf_quickwins, 455_spec_registry_value_labels
Create Date: 2026-09-02 00:00:00.000000
"""
from __future__ import annotations

revision = "458_merge_xco_reorder_specs"
down_revision = (
    "457_ptag_line_xco_repair",
    "456_reorder_perf_quickwins",
    "455_spec_registry_value_labels",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
