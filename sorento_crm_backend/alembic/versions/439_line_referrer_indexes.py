"""Index the purchase-line referrers on a database that stamped 420 before it indexed them

Revision ID: 439_line_referrer_indexes
Revises: 438_merge_price_supplier_sets
Create Date: 2026-08-27 21:10:00.000000

PR #353 taught migration 420 to index the four foreign keys its delete has to check
(`scm.order_link_claim.po_line_id`, `scm.loading_plan_line.po_line_id`,
`scm.shipment_line_spo_link.purchase_order_line_id`, `scm.plan_exception.purchase_order_id`)
before it deletes 80k lines. Production had already run 420 by the time that landed, so
alembic never revisits it there, and the models now declare indexes prod does not have.
This revision runs the same guarded step; a database that came through the fixed 420 or
through `create_all` finds nothing to do.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "439_line_referrer_indexes"
down_revision = "438_merge_price_supplier_sets"
branch_labels = None
depends_on = None


def _migration_420():
    """The step lives in 420 so there is one copy of the list; version files are not
    importable by name (they start with a digit), hence the spec load."""
    path = Path(__file__).with_name("420_spo_docs_in_allocations.py")
    spec = importlib.util.spec_from_file_location("migration_420_for_439", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    _migration_420().index_line_referrers(op.get_bind())


def downgrade() -> None:
    m = _migration_420()
    bind = op.get_bind()
    for module, table, _column, name in m._LINE_REFERRER_INDEXES:
        schema = m._schema(bind, module)
        if m._has_index(bind, name, schema=schema):
            op.drop_index(name, table_name=table, schema=schema)
