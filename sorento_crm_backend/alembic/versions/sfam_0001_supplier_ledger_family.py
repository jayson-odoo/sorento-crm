"""SUPPLIER-PARTY-SIDE: supplier records of one name are one supplier (7 Nov 2026).

Crew live check on #2120 (parser v74, md5 d29c1983): HANLIM TRADING SDN BHD is one customer and
two supplier records (403-H007, 400-H018). "PO for hanlim" read the supplier side, then
`turn/narrow.decide` ("ambiguous_filter_asks") asked "Which one do you mean?" over the two records
of one name. The `customer` kind already groups ledgers of one trading name (`ledger_family`,
owner hand pass 2 item 1, "Delivery for hanlim"); the `supplier` kind gets the same rule, so the
records of one name are one choice and the PO list runs for every one of them. Suppliers of
different names still ask.

Data only, no schema change. A value an admin already set is kept (only a NULL moves).
`policy_rows.SUPPLIER_KIND_ROW` carries the same value for a blank schema.

Revision ID: sfam_0001_supplier_ledger_family
Revises: slb_0001_leaderboard_perm
"""
from __future__ import annotations

from alembic import op

revision = "sfam_0001_supplier_ledger_family"
down_revision = "slb_0001_leaderboard_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE chatbot_entity_kinds SET family_grouping = 'ledger_family' "
        "WHERE kind = 'supplier' AND family_grouping IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE chatbot_entity_kinds SET family_grouping = NULL "
        "WHERE kind = 'supplier' AND family_grouping = 'ledger_family'"
    )
