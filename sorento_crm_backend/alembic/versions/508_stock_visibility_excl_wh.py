"""stock visibility policies: an "all except these" location rule

`warehouse_ids` names an include list; this adds its sibling,
`excluded_warehouse_ids` - every ACTIVE warehouse except the ones named, so a
warehouse created after the policy was saved stays visible without the row
ever being touched again. The CHECK
`ck_stock_visibility_policies_one_location_rule` keeps the two lists from ever
naming a rule at the same time - a row that tried both would have no defined
precedence between "only these" and "all but these".

Revision ID: 508_stock_visibility_excl_wh
Revises: 507_pi_link_packing_row
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "508_stock_visibility_excl_wh"
down_revision = "507_pi_link_packing_row"
branch_labels = None
depends_on = None

TABLE = "stock_visibility_policies"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("excluded_warehouse_ids", ARRAY(UUID(as_uuid=False)), nullable=True),
    )
    op.create_check_constraint(
        "ck_stock_visibility_policies_one_location_rule",
        TABLE,
        "warehouse_ids IS NULL OR excluded_warehouse_ids IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_stock_visibility_policies_one_location_rule", TABLE, type_="check"
    )
    op.drop_column(TABLE, "excluded_warehouse_ids")
