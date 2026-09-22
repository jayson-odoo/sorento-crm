"""Dealer stock verdict S0: the low-stock threshold is a setting, not a constant (D7).

`verdict()` (`app/services/stock_verdict.py`) compares an ask against available,
incoming and purchase using ONE threshold percent, T, in every one of its three
`running_low` / `limited` comparisons. The owner ruled it configurable rather than a
code constant ("make the T configurable", plan page markup, 22 Sep 2026) - a card on
Settings > Chatbot, same pattern as every other owner-operated chatbot switch this
table already carries.

Additive, NOT NULL, server default 50 (the owner's own matrix threshold, verified
against all 18 rows in `tests/test_stock_verdict.py`). No backfill: this is a new
decision with no prior value anywhere to copy from, and 50 is the safe landing state
for every existing tenant.

Guarded by a column-existence check (the `453_shared_brand_attach` precedent):
`tests/test_dsv_threshold_setting.py` runs `upgrade()` against `blank_session`'s
scratch schema, which is built from `Base.metadata.create_all` off the CURRENT models
(the column is already on `SystemSetting`) - so on that schema `upgrade()` is exercised
as an idempotent re-run, and on a real database replaying every migration in order it
is the one call that actually adds the column.

Revision ID: dsv_0001
Revises: spec_vocab_close_couple
"""
import sqlalchemy as sa
from alembic import op

revision = "dsv_0001"
down_revision = "spec_vocab_close_couple"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    if "chatbot_stock_low_threshold_pct" not in _columns("system_settings"):
        op.add_column(
            "system_settings",
            sa.Column(
                "chatbot_stock_low_threshold_pct",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("50"),
            ),
        )


def downgrade() -> None:
    if "chatbot_stock_low_threshold_pct" in _columns("system_settings"):
        op.drop_column("system_settings", "chatbot_stock_low_threshold_pct")
