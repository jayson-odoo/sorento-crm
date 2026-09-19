"""Local-supplier Buy routing behind a system setting, off by default

Revision ID: lbrt_0001_local_buy_toggle
Revises: oihr_0002_undone_headline
Create Date: 2026-09-18 00:00:00.000000

`PLAN-local-buy-routing-toggle.md` S1 (owner ruling 18 Sep 2026). #814 hard-wired a Buy on
a Malaysian-supplier product to skip its Order Inquiry on confirm; the owner's finding on
prod is that this breaks the handoff to purchasing, since a local supplier does not mean CS
buys it themselves. This column puts the whole rule behind a switch, defaulted off so the
shipped state is "every Buy reaches Order Inquiries" until an admin turns it on.
"""
import sqlalchemy as sa
from alembic import op

revision = "lbrt_0001_local_buy_toggle"
down_revision = "oihr_0002_undone_headline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "local_buy_routing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "local_buy_routing_enabled")
