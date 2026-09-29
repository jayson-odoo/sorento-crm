"""spo_allocations.inbound_shipment_id: ON DELETE SET NULL, not CASCADE (SPO-CASCADE).

Incident, production, 28 Sep 2026: SPO-2026/09-0104 (AutoCount DocKey
`AED_SORENTO:45897229`, 18 lines, container DFSU7408507) was pushed by the ESB at 04:04:51
and linked to packing list PL-2609-059 by container. At 06:57:46 a user deleted that packing
list, and `ON DELETE CASCADE` on this column hard-deleted all 18 lines. The AutoCount sync
never re-pushes a document it has already pushed, so the shipping order was gone, and
`spo_allocations` was on the audit skip list, so nothing recorded it. Re-uploading a packing
list for the same container is routine (PL-2609-033 deleted 03:00, PL-2609-059 uploaded
03:00:55), so this recurs.

Owner ruling: "we shouldn't delete on cascade". A shipping order is a document in its own
right (`SPOAllocation` docstring, migration 420): `inbound_shipment_id` NULL means "promised,
not yet on a named shipment", and `container_number` keeps the raw fact a later shipment
relinks on (`shipping_order_rules.relink_allocations_for_container`, D6). Deleting the
shipment a document was booked on now returns its lines to that state instead of deleting
them.

Additive and non-destructive: the constraint is found by its constrained column, not by
name, because a create_all database names it `spo_allocations_inbound_shipment_id_fkey` and
a migrated one may not; it is dropped and re-created with the new ON DELETE rule in the same
transaction. No row changes. Idempotent: a database whose FK already reads SET NULL is left
alone.

Revision ID: spo_cascade_0001_set_null
Revises: merge_29sep_batch7
"""
import logging

from alembic import op
from sqlalchemy import inspect

revision = "spo_cascade_0001_set_null"
# Parented on main's merge revision (#1374 joined eml_0002_seed_layouts and
# mem_0003_parser_history after they merged back to back), re-parented by the lane
# on each main merge per scripts/alembic-reparent.sh.
down_revision = "merge_29sep_batch7"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "spo_allocations"
COLUMN = "inbound_shipment_id"
REFERRED_TABLE = "inbound_shipments"
FK_NAME = "fk_spo_allocations_inbound_shipment_id"


def _current_fk(bind) -> dict | None:
    for fk in inspect(bind).get_foreign_keys(TABLE):
        if list(fk.get("constrained_columns") or []) == [COLUMN]:
            return fk
    return None


def _set_ondelete(rule: str) -> None:
    bind = op.get_bind()
    fk = _current_fk(bind)
    if fk is not None:
        current = ((fk.get("options") or {}).get("ondelete") or "NO ACTION").upper()
        if current == rule:
            logger.info("%s.%s already ON DELETE %s, nothing to do", TABLE, COLUMN, rule)
            return
        if fk.get("name"):
            op.drop_constraint(fk["name"], TABLE, type_="foreignkey")
    op.create_foreign_key(
        (fk or {}).get("name") or FK_NAME,
        TABLE,
        REFERRED_TABLE,
        [COLUMN],
        ["id"],
        ondelete=rule,
    )


def upgrade() -> None:
    _set_ondelete("SET NULL")


def downgrade() -> None:
    # The rule the incident happened under; kept only so the chain reverses cleanly.
    _set_ondelete("CASCADE")
