"""DO-ASK-SIMPLIFY rule 2: every contact that exists today keeps the five DO fields.

Revision ID: do_ask_0001_reveals
Revises: selfref_0001_n8n_sales_view
Create Date: 2026-10-02

The DO list's Status, Pickup Time, Transporter, Driver and Lorry Plate became per-contact
reveals (`contact_field_reveals`, keys `delivery_orders.*`), hidden by default. Owner, 2 Oct
2026: every current respond contact is internal and keeps seeing them, so each one is granted
the five here; a contact created after this migration starts with them hidden, and the owner
adjusts per contact on Contacts > Access > Field reveals.

Data only, idempotent: `ON CONFLICT DO NOTHING` on (contact, key), so a key an admin already
revoked stays revoked. A create_all database has no contacts to seed, so
`scripts.bootstrap_env` needs nothing.
"""
import sqlalchemy as sa
from alembic import op

revision = "do_ask_0001_reveals"
down_revision = "selfref_0001_n8n_sales_view"
branch_labels = None
depends_on = None

KEYS = (
    "delivery_orders.status",
    "delivery_orders.pickup_time",
    "delivery_orders.transporter",
    "delivery_orders.driver",
    "delivery_orders.lorry_plate",
)


def seed_do_reveals(bind) -> None:
    """Grant the five keys to every existing respond contact."""
    for key in KEYS:
        bind.execute(
            sa.text(
                "INSERT INTO contact_field_reveals (id, respond_contact_id, field_key, granted, created_by) "
                "SELECT gen_random_uuid(), c.id, :key, true, 'migration:do_ask_0001_reveals' "
                "FROM respond_contacts c "
                "ON CONFLICT (respond_contact_id, field_key) DO NOTHING"
            ),
            {"key": key},
        )


def drop_do_reveals(bind) -> None:
    bind.execute(
        sa.text("DELETE FROM contact_field_reveals WHERE field_key = ANY(:keys)"),
        {"keys": list(KEYS)},
    )


def upgrade() -> None:
    seed_do_reveals(op.get_bind())


def downgrade() -> None:
    drop_do_reveals(op.get_bind())
