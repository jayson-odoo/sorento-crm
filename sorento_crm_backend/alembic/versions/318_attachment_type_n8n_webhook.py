"""Per-type control over whether an upload calls the n8n intake webhook.

Every attachment upload fires the n8n webhook, and the upload-activity drawer
reads the resulting `integration_log` to decide what to show. A type n8n does
not handle therefore never gets a reply, and the row sits on "Processing"
forever - the drawer has no way to tell "n8n is still working" from "n8n was
never going to answer".

That was already known and already worked around: `upload_activity.py` hardcoded
`type_name IN ('Stock List','Stock_List')` with a comment saying exactly this.
The workaround was right and its scope was wrong - it names one type in Python,
so every future one needs a code change, and it suppresses the drawer row while
still firing the pointless webhook.

This makes it a property of the type, admin-editable, driving both sides:

* `create_and_send_webhook` returns early - no log row, no wasted call
* the drawer skips the type instead of showing a permanent "Processing"

Default TRUE, so every existing type behaves exactly as it does today.

Seeded FALSE for the types n8n does not entertain:

* `Stock List` / `Stock_List` - preserves the hardcoded behaviour being replaced
* `Container Status` - published by the importer as a byproduct, and it was
  producing a SECOND "Processing" row beside the import job's own
* `Direct Access` - dealer-downloadable documents; n8n serves them, it does not
  intake them
* `Response Attachment` - staff images posted into a reply
* `[DONT USE THIS] SPO Allocations` - retired

Revision ID: 318_attachment_type_n8n_webhook
Revises: 317_picking_header_spo_width
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "318_attachment_type_n8n_webhook"
down_revision = "317_picking_header_spo_width"
branch_labels = None
depends_on = None

#: Matched on `type_name` because most of these have no `code`. Names that do
#: not exist are simply not updated - the list is deliberately a superset so a
#: tenant missing one of them is not a migration failure.
OPT_OUT_TYPE_NAMES = (
    "Stock List",
    "Stock_List",
    "Container Status",
    "Direct Access",
    "Response Attachment",
    "[DONT USE THIS] SPO Allocations",
)


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("attachment_types")}

    if "triggers_n8n_webhook" not in columns:
        op.add_column(
            "attachment_types",
            sa.Column(
                "triggers_n8n_webhook",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )

    bind.execute(
        sa.text(
            """
            UPDATE attachment_types
            SET triggers_n8n_webhook = false
            WHERE type_name = ANY(:names)
            """
        ),
        {"names": list(OPT_OUT_TYPE_NAMES)},
    )


def downgrade() -> None:
    op.drop_column("attachment_types", "triggers_n8n_webhook")
