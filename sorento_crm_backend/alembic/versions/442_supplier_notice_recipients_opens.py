"""Supplier notices: who the send named, and whether the supplier opened it.

S3 / R9-R11 of `PLAN-scm-fulfilment-feedback-p4.md`.

- `recipients` (JSONB) - the addresses an email send actually went to, or the WeChat
  contact a chat send went to. `recipient` (one varchar) could only ever hold the first
  one, and the Requests sent card has to state every address the supplier's people read it
  on. Backfilled from `recipient` so an existing row reads as the one-address send it was.
- `opened_at` / `last_opened_at` / `open_count` - the supplier opening their link is an
  EVENT that repeats, so it is counted on the notice rather than promoted to a plan status
  (a status would flip back and forth or lie, plan section 10).

Numbered 442 in the part-4 chain (440 = packing-list numbering, 441 = loading-plan
lifecycle); it touches only `supplier_notices`, so it is order-independent among them.

Revision ID: 442_notice_recipients_opens
Revises: 441_loading_plan_lifecycle
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "442_notice_recipients_opens"
down_revision = "441_loading_plan_lifecycle"
branch_labels = None
depends_on = None

TABLE = "supplier_notices"


def _columns() -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = current_schema()"
            ),
            {"t": TABLE},
        )
    }


def upgrade() -> None:
    existing = _columns()

    if "recipients" not in existing:
        op.add_column(
            TABLE, sa.Column("recipients", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
        )
    if "opened_at" not in existing:
        op.add_column(TABLE, sa.Column("opened_at", sa.DateTime(timezone=False), nullable=True))
    if "last_opened_at" not in existing:
        op.add_column(
            TABLE, sa.Column("last_opened_at", sa.DateTime(timezone=False), nullable=True)
        )
    if "open_count" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "open_count", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
        )

    # Backfill: an existing send named exactly one address, and it is on the row already.
    # "Set where mismatch" rather than "update where null" so a re-run repairs a partial
    # earlier one instead of skipping it.
    op.execute(
        sa.text(
            "UPDATE supplier_notices "
            "   SET recipients = to_jsonb(ARRAY[recipient]) "
            " WHERE recipient IS NOT NULL "
            "   AND recipients IS DISTINCT FROM to_jsonb(ARRAY[recipient])"
        )
    )


def downgrade() -> None:
    for column in ("open_count", "last_opened_at", "opened_at", "recipients"):
        op.drop_column(TABLE, column)
