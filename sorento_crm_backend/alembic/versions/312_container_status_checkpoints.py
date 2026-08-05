"""Seed the container clearance checkpoints as configurable `statuses` rows.

The Clearance & Delivery card was a hardcoded array in a React component: eleven
milestones, their labels, their groupings and their captions all literals. Renaming
"Gatepass" to "Released from port", reordering a step, hiding one, or adding a new
one all meant a code change and a deploy.

These rows move that into System Management -> Status Graphs. The mapping needs no
new schema:

    key         the `inbound_shipments` date column this checkpoint reads
    label       what the timeline shows
    description the muted caption under it
    sort_order  timeline order
    color_hex   the dot colour once reached
    is_active   uncheck to hide the checkpoint

`key` is frozen on update by the statuses API, so an admin can rename a checkpoint
freely without breaking the link to its column.

`is_system=false` ON PURPOSE. A system row is non-deletable with immutable flags,
and the whole point here is that purchasing can change this list themselves. The
`count_records` hook still blocks deleting a checkpoint that containers have
already reached.

Deliberately NOT seeded: `is_initial` / `is_terminal` on any row, and no
`status_transitions` at all. This is a timeline of independent checkpoints, not a
single-position graph - the real workbook has containers with a gatepass and no
inspection, so there is no straight line to model. Nothing auto-advances; a
checkpoint is reached because its date column is filled.

Idempotent: re-running inserts only the keys that are missing, so an admin's edits
to labels, colours and order survive a re-deploy.

Revision ID: 312_container_status_checkpoints
Revises: 311_container_status_columns
"""
import uuid

import sqlalchemy as sa
from alembic import op


revision = "312_container_status_checkpoints"
down_revision = "311_container_status_columns"
branch_labels = None
depends_on = None


ENTITY_TYPE = "inbound_shipment"

# (key, label, caption, colour). Order here IS the timeline order.
#
# There is deliberately NO grouping column. An earlier version grouped these into
# ORIGIN / SEA / CLEARANCE / DELIVERY, but those four names were a hardcoded map in
# the component - an admin adding a checkpoint had nowhere to put it, and renaming a
# group meant a release. One flat ordered list has no such trap (D35).
#
# The captions are the real intervals from the sheet and from CIDB's published
# procedure, not invented SLAs.
CHECKPOINTS = [
    ("loading_date", "Loading", "2-4 days before ETD", "#94a3b8"),
    ("etc_date", "ETC", "China forwarder", "#94a3b8"),
    ("etd_date", "ETD", "China forwarder", "#94a3b8"),
    ("eta_date", "ETA", "Liner, first published", "#0ea5e9"),
    ("eta_delay_date", "ETA Delay", "Liner, revised - the accurate one", "#0284c7"),
    ("inspection_date", "Inspection", "CIDB officer at port", "#f59e0b"),
    (
        "approval_date",
        "Approval (COA)",
        "CIDB, within 3 working days of inspection",
        "#f59e0b",
    ),
    (
        "gatepass_date",
        "Gatepass",
        "Malaysia forwarder, same day as duty paid",
        "#f97316",
    ),
    ("warehouse_arrival_date", "Warehouse Arrival", "Yard", "#22c55e"),
    ("informed_collection_date", "Informed Collection", "48h after gatepass", "#22c55e"),
    ("collection_date", "Collection", "Within 6 days of exit gate", "#16a34a"),
]


def upgrade() -> None:
    connection = op.get_bind()
    existing = {
        row[0]
        for row in connection.execute(
            sa.text("SELECT key FROM statuses WHERE entity_type = :e"),
            {"e": ENTITY_TYPE},
        )
    }

    for index, (key, label, caption, colour) in enumerate(CHECKPOINTS):
        if key in existing:
            continue
        connection.execute(
            sa.text(
                """
                INSERT INTO statuses (
                    id, entity_type, key, label, color_hex, description,
                    sort_order, is_initial, is_terminal, is_active, is_archived,
                    is_default, is_system
                ) VALUES (
                    :id, :entity_type, :key, :label, :color_hex, :description,
                    :sort_order, false, false, true, false, false, false
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "entity_type": ENTITY_TYPE,
                "key": key,
                "label": label,
                "color_hex": colour,
                "description": caption,
                "sort_order": (index + 1) * 10,
            },
        )


def downgrade() -> None:
    # Only the seeded keys, so a checkpoint an admin added by hand survives.
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM statuses WHERE entity_type = :e AND key = ANY(:keys)"),
        {"e": ENTITY_TYPE, "keys": [key for key, *_ in CHECKPOINTS]},
    )
