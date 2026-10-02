"""DO-ASK-SIMPLIFY rule 2: every contact that exists today keeps the five DO fields.

Revision ID: do_ask_0001_reveals
Revises: grn_pull_0001_perm
Create Date: 2026-10-02

The DO list's Status, Pickup Time, Transporter, Driver and Lorry Plate became per-contact
reveals (`contact_field_reveals`, keys `delivery_orders.*`), hidden by default. Owner, 2 Oct
2026: every current respond contact is internal and keeps seeing them, so each one is granted
the five here; a contact created after this migration starts with them hidden, and the owner
adjusts per contact on Contacts > Access > Field reveals.

Owner rule change (2 Oct 2026): every EXISTING contact ends with ALL five switched on, so no
current user sees any change; a DO switch already off (an earlier seed, a test copy) is turned
on (`ON CONFLICT ... DO UPDATE SET granted = true`), and the owner adjusts per contact after.
Dealer contacts are not in yet, so none is left out. Data only and idempotent. A create_all
database has no contacts to seed, so `scripts.bootstrap_env` needs nothing.

The downgrade deletes EVERY row for the five keys, including grants and revocations an
admin made after the upgrade; that is safe because the code before this lane never reads
these keys.
"""
import sqlalchemy as sa
from alembic import op

revision = "do_ask_0001_reveals"
down_revision = "grn_pull_0001_perm"
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
    """Switch the five keys ON for every existing respond contact."""
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
