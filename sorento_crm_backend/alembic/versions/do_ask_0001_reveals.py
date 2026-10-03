"""DO-ASK-SIMPLIFY rule 2: every contact that exists today keeps every DO field.

Revision ID: do_ask_0001_reveals
Revises: item_type_0001
Create Date: 2026-10-02

Every field the DO list prints (owner hand test 3 Oct 2026: Order Number, Customer, Order
Date, Actual Delivery Date, Status, Pickup Time, Transporter, Driver, Lorry Plate, Warehouse,
Products) became a per-contact reveal (`contact_field_reveals`, keys `delivery_orders.*`), hidden by default. Owner, 2 Oct
2026: every current respond contact is internal and keeps seeing them, so each one is granted
the five here; a contact created after this migration starts with them hidden, and the owner
adjusts per contact on Contacts > Access > Field reveals.

Owner rule change (2 Oct 2026): every EXISTING contact ends with ALL five switched on, so no
current user sees any change; a DO switch already off (an earlier seed, a test copy) is turned
on (`ON CONFLICT ... DO UPDATE SET granted = true`), and the owner adjusts per contact after.
Dealer contacts are not in yet, so none is left out. Data only and idempotent. A create_all
database has no contacts to seed, so `scripts.bootstrap_env` needs nothing.

The downgrade deletes EVERY row for every DO key, including grants and revocations an
admin made after the upgrade; that is safe because the code before this lane never reads
these keys.
"""
import sqlalchemy as sa
from alembic import op

revision = "do_ask_0001_reveals"
down_revision = "item_type_0001"
branch_labels = None
depends_on = None

KEYS = (
    "delivery_orders.status",
    "delivery_orders.pickup_time",
    "delivery_orders.transporter",
    "delivery_orders.driver",
    "delivery_orders.lorry_plate",
    "delivery_orders.order_number",
    "delivery_orders.customer",
    "delivery_orders.order_date",
    "delivery_orders.delivery_date",
    "delivery_orders.warehouse",
    "delivery_orders.products",
)


def seed_do_reveals(bind) -> None:
    """Switch every DO key ON for every existing respond contact."""
    for key in KEYS:
        bind.execute(
            sa.text(
                "INSERT INTO contact_field_reveals (id, respond_contact_id, field_key, granted, created_by) "
                "SELECT gen_random_uuid(), c.id, :key, true, 'migration:do_ask_0001_reveals' "
                "FROM respond_contacts c "
                "ON CONFLICT (respond_contact_id, field_key) DO UPDATE SET granted = true"
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
