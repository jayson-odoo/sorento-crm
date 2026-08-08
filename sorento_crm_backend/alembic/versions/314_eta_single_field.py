"""One ETA field, gated but allowed by default.

Migration 311 added `eta_date` alongside the `estimated_arrival_date` that packing
lists already had. That was a mistake: they are the same fact from two sources. On
the dev data 11 of 12 rows held identical values and the twelfth had drifted (06/05
vs 01/05) - which is what two writers for one fact always produce eventually.

It also made the access gate incoherent. `eta_date` was gated and
`estimated_arrival_date` was not, so a contact denied the ETA read the same date
from the ungated column. The restriction protected nothing.

So: drop `eta_date`, point the importer and the ETA checkpoint at
`estimated_arrival_date`, and gate THAT instead.

**Seeded allowed, unlike every other gated field.** Default-deny is right for a
field nobody could see before; it is wrong here. `estimated_arrival_date` is what
the 53 contacts holding `incoming_stock_enquiries` already ask about every day, and
shipping a deny would take away an answer they have today. The row exists so an
admin CAN revoke it; it ships `true` so the deploy changes nothing.

Values are copied across before the drop, but only where the destination is empty -
`estimated_arrival_date` is the incumbent and a packing list's own ETA must not be
overwritten by a sheet import retroactively.

Revision ID: 314_eta_single_field
Revises: 313_agent_field_access
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "314_eta_single_field"
down_revision = "313_agent_field_access"
branch_labels = None
depends_on = None

OWNING_AGENT = "incoming_stock_enquiries"
ENTITY_TYPE = "inbound_shipment"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("inbound_shipments")}

    if "eta_date" in columns:
        # Only fill the gaps. Where both are set, the packing list's own value wins:
        # it was entered against the shipment, not transcribed into a spreadsheet.
        bind.execute(
            sa.text(
                """
                UPDATE inbound_shipments
                SET estimated_arrival_date = eta_date
                WHERE estimated_arrival_date IS NULL AND eta_date IS NOT NULL
                """
            )
        )
        op.drop_column("inbound_shipments", "eta_date")

    # The ETA checkpoint now reads the surviving column. Checkpoints are
    # `statuses` rows scoped by entity_type (see migration 312), and `key` IS the
    # shipment column the checkpoint reads.
    bind.execute(
        sa.text(
            """
            UPDATE statuses
            SET key = 'estimated_arrival_date'
            WHERE entity_type = :e AND key = 'eta_date'
              AND NOT EXISTS (
                  SELECT 1 FROM statuses s2
                  WHERE s2.entity_type = :e AND s2.key = 'estimated_arrival_date'
              )
            """
        ),
        {"e": ENTITY_TYPE},
    )

    # Retire the old field-access row and seed the new one ALLOWED.
    bind.execute(
        sa.text("DELETE FROM agent_field_access WHERE field_key = 'eta_date'")
    )
    agent_exists = bind.execute(
        sa.text("SELECT 1 FROM access_agents WHERE code = :code"), {"code": OWNING_AGENT}
    ).scalar()
    if agent_exists:
        # Delete-then-insert, NOT `ON CONFLICT DO NOTHING`. If the app booted before
        # this migration ran, its bootstrap already seeded the row - and on a build
        # where the bootstrap still defaulted to deny, that row says false. Skipping
        # on conflict would leave ETA denied and the deploy would silently STOP
        # answering a question contacts ask every day. The migration must assert the
        # value, not defer to whatever got there first.
        bind.execute(
            sa.text(
                """
                DELETE FROM agent_field_access
                WHERE resource = 'incoming_stock'
                  AND field_key = 'estimated_arrival_date'
                  AND contact_id IS NULL
                """
            )
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO agent_field_access
                    (id, agent_code, resource, field_key, contact_id, is_allowed)
                VALUES (:id, :agent, 'incoming_stock', 'estimated_arrival_date', NULL, true)
                """
            ),
            {"id": str(uuid.uuid4()), "agent": OWNING_AGENT},
        )


def downgrade() -> None:
    op.add_column("inbound_shipments", sa.Column("eta_date", sa.Date(), nullable=True))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE statuses SET key = 'eta_date'
            WHERE entity_type = :e AND key = 'estimated_arrival_date'
            """
        ),
        {"e": ENTITY_TYPE},
    )
    # The copied values are NOT unpicked: there is no record of which rows were
    # empty beforehand, and guessing would blank real ETAs.
