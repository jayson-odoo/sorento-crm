"""SUPPLIER-ASK: the `supplier` entity kind gets its `chatbot_entity_kinds` row (1 Nov 2026).

Owner, 1 Nov 2026: "outstanding for supplier X" is the open POs not yet received, and the
design is "allowing supplier as entity in the span pass and the tool". `contracts.ENTITY_HINTS`
gains `supplier`; the AC-1502 contract (one `chatbot_entity_kinds` row per entity hint,
`tests/chatbot/test_rearch_s0_entity_kinds_seed.py`) needs its row. The resolver source is
the `suppliers` table the shared resolver already probes (`entity_resolver._probe_supplier`).

Data only, no schema change, no parser publish. A parser version that renders
`{{entity_kinds}}` / `{{entity_kinds_detail}}` from this table gains the `supplier` hint value
and one "Entity kind" line on the next turn after this runs. Idempotent: a kind already present
is left alone, so bootstrap calls `insert_kind(bind)` too.

Revision ID: sask_0001_supplier_kind
Revises: akn_0001_knowledge
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "sask_0001_supplier_kind"
down_revision = "akn_0001_knowledge"
branch_labels = None
depends_on = None

#: Frozen here, not imported: a migration's data must not move when the seed module does.
KIND_ROW = {
    "kind": "supplier",
    "label": "Supplier",
    "resolver_source": "suppliers",
    "did_you_mean": True,
    "default_narrowing": "optional_filter",
}


def insert_kind(bind) -> bool:
    """Insert the `supplier` kind row when absent. True when it inserted one."""
    present = bind.execute(
        sa.text("SELECT 1 FROM chatbot_entity_kinds WHERE kind = :kind"), {"kind": KIND_ROW["kind"]}
    ).first()
    if present is not None:
        return False
    next_order = bind.execute(sa.text("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM chatbot_entity_kinds")).scalar()
    bind.execute(
        sa.text(
            "INSERT INTO chatbot_entity_kinds "
            "(id, kind, label, resolver_source, did_you_mean, default_narrowing, family_grouping, "
            "base_property_words, sort_order) "
            "VALUES (:id, :kind, :label, :resolver_source, :did_you_mean, :default_narrowing, "
            "NULL, CAST('{}' AS jsonb), :sort_order)"
        ),
        {**KIND_ROW, "id": str(uuid.uuid4()), "sort_order": int(next_order or 0)},
    )
    return True


def upgrade() -> None:
    insert_kind(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM chatbot_entity_kinds WHERE kind = 'supplier'"))
