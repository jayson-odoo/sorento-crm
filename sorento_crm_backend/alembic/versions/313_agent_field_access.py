"""Field-level access per agent, replacing the container-status agent.

The first cut of the clearance gate minted a whole access agent
(`container_status_enquiries`) whose only job was to unlock a hardcoded list of
fields. Wrong level: the contact asking "when does my container arrive" is already
routed to `incoming_stock_enquiries`, held by 53 contacts. Gating on a second
agent means 53 re-grants, an agent n8n never routes to, and a new agent for every
future sensitive field.

This moves the granularity down one level: the agent stays the FUNCTION, and the
fields it may reveal become rows. `contact_id IS NULL` is the agent-wide default;
a row naming a contact overrides it for that contact alone.

Seeds one row per gated field so an admin opens the screen to a complete
checklist rather than a blank one. Denied by default - a field that has never been
reviewed must not be readable, and the 53 contacts must not gain ETA delay and
CIDB dates the moment this deploys.

`estimated_arrival_date` is the exception, seeded ALLOWED: those contacts already
receive it every day, so a denied seed would REMOVE an answer rather than withhold
a new one. It is listed here so an admin can revoke it, not so the deploy does.

Drops `container_status_enquiries`; its grants go with it via ON DELETE CASCADE.

Revision ID: 313_agent_field_access
Revises: 312_container_status_checkpoints
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "313_agent_field_access"
down_revision = "312_container_status_checkpoints"
branch_labels = None
depends_on = None


#: Mirrors `app.services.field_access.GATED_FIELDS["incoming_stock"]`. Duplicated
#: rather than imported: a migration must keep describing the world as it was the
#: day it ran, even after the registry grows.
INCOMING_STOCK_FIELDS = (
    "estimated_arrival_date",
    "eta_delay_date",
    "inspection_date",
    "approval_date",
    "gatepass_date",
    "warehouse_arrival_date",
    "informed_collection_date",
    "collection_date",
    "loading_date",
    "etc_date",
    "etd_date",
    "liner_code",
    "china_forwarder",
    "malaysia_forwarder",
    "consignee",
    "delivery_warehouse",
    "free_days_available",
    "loc",
    "stacked",
    "coa_permit_no",
    "source_sheet",
)

OWNING_AGENT = "incoming_stock_enquiries"
DEAD_AGENT = "container_status_enquiries"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "agent_field_access" not in inspector.get_table_names():
        op.create_table(
            "agent_field_access",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("agent_code", sa.Text(), nullable=False),
            sa.Column("resource", sa.Text(), nullable=False),
            sa.Column("field_key", sa.Text(), nullable=False),
            sa.Column("contact_id", sa.Text(), nullable=True),
            sa.Column(
                "is_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("created_by", sa.Text(), nullable=True),
            # Separate from created_by: rows are pre-seeded denied, so the insert
            # never has a human behind it and created_by would be NULL on every
            # grant anyone ever makes.
            sa.Column("updated_by", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["agent_code"],
                ["access_agents.code"],
                ondelete="CASCADE",
                onupdate="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["contact_id"], ["respond_contacts.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_agent_field_access_lookup", "agent_field_access", ["resource", "agent_code"]
        )
        op.create_index(
            "ix_agent_field_access_contact_id", "agent_field_access", ["contact_id"]
        )
        # NULLs are distinct in Postgres, so one UNIQUE over all four columns would
        # still allow a second agent-wide row for the same field.
        op.create_index(
            "uq_agent_field_access_default",
            "agent_field_access",
            ["agent_code", "resource", "field_key"],
            unique=True,
            postgresql_where=sa.text("contact_id IS NULL"),
        )
        op.create_index(
            "uq_agent_field_access_override",
            "agent_field_access",
            ["agent_code", "resource", "field_key", "contact_id"],
            unique=True,
            postgresql_where=sa.text("contact_id IS NOT NULL"),
        )

    # The owning agent may not exist yet on a fresh install; the FK would reject
    # the seed rows, so only seed once it is there. `container_status_bootstrap`
    # ensures it on startup either way.
    agent_exists = bind.execute(
        sa.text("SELECT 1 FROM access_agents WHERE code = :code"), {"code": OWNING_AGENT}
    ).scalar()

    if agent_exists:
        for field in INCOMING_STOCK_FIELDS:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO agent_field_access
                        (id, agent_code, resource, field_key, contact_id, is_allowed)
                    VALUES (:id, :agent, 'incoming_stock', :field, NULL, :allowed)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "agent": OWNING_AGENT,
                    "field": field,
                    # ETA ships ALLOWED: contacts already receive it, so a denied
                    # seed would remove an answer rather than withhold a new one.
                    "allowed": field == "estimated_arrival_date",
                },
            )

    # The agent this replaces. Its contact grants cascade away with it.
    bind.execute(
        sa.text("DELETE FROM access_agents WHERE code = :code"), {"code": DEAD_AGENT}
    )


def downgrade() -> None:
    # The dead agent is deliberately NOT recreated: nothing reads it any more, and
    # resurrecting it empty would only look like a live grant surface.
    op.drop_table("agent_field_access")
