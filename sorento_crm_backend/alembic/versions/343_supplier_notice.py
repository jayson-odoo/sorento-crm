"""S8: the Supplier Notice - what was sent to a supplier, on which channel, and when.

Two tables and three columns.

`supplier_notices` is in `public`, not `scm`, on purpose. The loading plan is planning: it is
re-run in place every time the container count changes, and a plan nobody sent can be deleted
without consequence. A notice is not planning. It is a thing that left the building, and the
outcomes of the SCM module (SPO allocations, sent notices) live in core so that dropping the
scm schema never destroys the record of what a supplier was told.

`supplier_notice_lines` copies the loading-plan lines the notice was built from. The plan stays
mutable so a different container count remains one decision (AC-E6); the copy is what makes the
sent document still readable after the plan moves underneath it. Without it, "what did we ask
for last month" is answerable only by whatever the plan happens to say today.

The three `email_outbox` columns let ONE producer keep owning SMTP. The drainer already holds
the backoff, the rate limiter and the per-event kill switch, and `send_mime_email` already
accepts attachments - the outbox was simply the one path that could not pass any. A nullable
storage reference resolved at drain time is generic: the next document-bearing email needs no
second mechanism, and the notice PDF is stored exactly once whether it is emailed, downloaded,
or both.

Revision ID: 343_supplier_notice
Revises: 342_sales_order_source_doc_no
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "343_supplier_notice"
down_revision = "342_sales_order_source_doc_no"
branch_labels = None
depends_on = None

SORENTO = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "supplier_notices",
        sa.Column("id", PG_UUID(as_uuid=False), primary_key=True),
        sa.Column("supplier_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        # SET NULL, not CASCADE: deleting a superseded plan must not erase the record of what
        # was sent from it. The snapshot below is what the notice actually reads.
        sa.Column("loading_plan_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("scm.loading_plan.id", ondelete="SET NULL"), nullable=True),

        # What the notice is FOR. One value today; named rather than assumed so a second kind
        # of supplier notice does not need a second table.
        sa.Column("notice_type", sa.String(40), nullable=False,
                  server_default=sa.text("'loading'")),

        # Channel-abstract by design (AC-F4). `email` sends today; `chat` is a declared row that
        # stays dark until a WeChat channel exists in the Respond workspace, at which point it
        # lights up with no change to the trigger, the content or this record.
        sa.Column("channel", sa.String(20), nullable=False, server_default=sa.text("'email'")),
        sa.Column("recipient", sa.String(320), nullable=True),

        # pending -> sent | failed | skipped. `skipped` is a real outcome, not an error: a
        # supplier with no email address still gets a notice and a downloadable document.
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("status_reason", sa.String(255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),

        # The document, stored once. Present before any send is queued: a notice with no
        # document is never sent.
        sa.Column("document_filename", sa.String(255), nullable=True),
        sa.Column("storage_provider", sa.String(16), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),

        # Header figures frozen for the list, so reading the history costs no joins.
        sa.Column("container_type", sa.String(30), nullable=True),
        sa.Column("container_count", sa.Integer(), nullable=True),
        sa.Column("planned_cbm", sa.Numeric(), nullable=True),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("production_line_count", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),

        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("company_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False,
                  server_default=sa.text(f"'{SORENTO}'::uuid")),

        sa.CheckConstraint("channel IN ('email', 'chat')", name="ck_supplier_notice_channel"),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed', 'skipped')",
                           name="ck_supplier_notice_status"),
    )
    op.create_index("ix_supplier_notices_supplier", "supplier_notices",
                    ["supplier_id", "created_at"])
    op.create_index("ix_supplier_notices_plan", "supplier_notices", ["loading_plan_id"])

    op.create_table(
        "supplier_notice_lines",
        sa.Column("id", PG_UUID(as_uuid=False), primary_key=True),
        sa.Column("notice_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("supplier_notices.id", ondelete="CASCADE"), nullable=False),

        # Codes and text, not foreign keys, apart from the product. This is a copy of what was
        # SAID; renaming a product later must not rewrite a notice that already went out.
        sa.Column("product_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_code", sa.String(100), nullable=True),
        sa.Column("product_name", sa.String(500), nullable=True),
        sa.Column("po_number", sa.String(100), nullable=True),

        sa.Column("qty", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("cbm", sa.Numeric(), nullable=True),

        # `pack` = load it. `produce` = the supplier has to make it first, which the document
        # states separately because it is a different ask (AC-F2).
        sa.Column("kind", sa.String(20), nullable=False, server_default=sa.text("'pack'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),

        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("company_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False,
                  server_default=sa.text(f"'{SORENTO}'::uuid")),

        sa.CheckConstraint("kind IN ('pack', 'produce')", name="ck_supplier_notice_line_kind"),
    )
    op.create_index("ix_supplier_notice_lines_notice", "supplier_notice_lines",
                    ["notice_id", "sort_order"])

    # The outbox learns to carry a document. Nullable throughout, so every existing row and
    # every existing producer is unaffected.
    op.add_column("email_outbox",
                  sa.Column("attachment_filename", sa.String(255), nullable=True))
    op.add_column("email_outbox",
                  sa.Column("attachment_storage_provider", sa.String(16), nullable=True))
    op.add_column("email_outbox",
                  sa.Column("attachment_storage_key", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("email_outbox", "attachment_storage_key")
    op.drop_column("email_outbox", "attachment_storage_provider")
    op.drop_column("email_outbox", "attachment_filename")
    op.drop_index("ix_supplier_notice_lines_notice", table_name="supplier_notice_lines")
    op.drop_table("supplier_notice_lines")
    op.drop_index("ix_supplier_notices_plan", table_name="supplier_notices")
    op.drop_index("ix_supplier_notices_supplier", table_name="supplier_notices")
    op.drop_table("supplier_notices")
