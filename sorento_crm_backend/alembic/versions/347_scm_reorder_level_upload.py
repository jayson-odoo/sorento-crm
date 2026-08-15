"""S13c: the AutoCount reorder level + reorder quantity listing becomes an upload.

> "important aspect is the reorder level and reorder quantity, which are set at autocount,
>  and they need to upload to our system"   (user, 2026-08-10)

Two pieces:

1. `scm.reorder_level.reorder_qty` - AutoCount's own reorder quantity, stored beside the
   level. Nothing in our UI edits it; it is the starting point the quantity suggestion
   offers, with the engine's computed figure shown beside it when they disagree.

2. Header aliases for the new `reorder_level` doc type. No sample export exists yet, so the
   spellings are ASSUMED (user: "you can assume the column first") - when the real file
   arrives with different headers, the fix is alias rows, not code. Covers the AutoCount
   item-maintenance vocabulary most likely to appear.

Revision ID: 347_scm_reorder_level_upload
Revises: 346_scm_demand_origin_split
"""
import sqlalchemy as sa
from alembic import op

revision = "347_scm_reorder_level_upload"
down_revision = "346_scm_demand_origin_split"
branch_labels = None
depends_on = None


#: (field, alias). Locale left NULL: these are English guesses at an AutoCount export.
_ALIASES = (
    ("item_code", "Item Code"),
    ("item_code", "ItemCode"),
    ("item_code", "Item No"),
    ("item_code", "Item No."),
    ("item_code", "Stock Code"),
    ("location", "Location"),
    ("location", "Location Code"),
    ("location", "Warehouse"),
    ("reorder_level", "Reorder Level"),
    ("reorder_level", "Re-order Level"),
    ("reorder_level", "ReorderLevel"),
    ("reorder_level", "Min Level"),
    ("reorder_qty", "Reorder Qty"),
    ("reorder_qty", "Reorder Quantity"),
    ("reorder_qty", "Re-order Qty"),
    ("reorder_qty", "ReorderQty"),
)


def upgrade() -> None:
    op.add_column(
        "reorder_level",
        sa.Column("reorder_qty", sa.Numeric(18, 4), nullable=True),
        schema="scm",
    )
    for field, alias in _ALIASES:
        op.execute(sa.text(
            "INSERT INTO import_field_alias (doc_type, field, alias, locale) "
            "VALUES ('reorder_level', :f, :a, NULL) "
            "ON CONFLICT (doc_type, field, alias) DO NOTHING"
        ).bindparams(f=field, a=alias))


def downgrade() -> None:
    op.execute("DELETE FROM import_field_alias WHERE doc_type = 'reorder_level'")
    op.drop_column("reorder_level", "reorder_qty", schema="scm")
