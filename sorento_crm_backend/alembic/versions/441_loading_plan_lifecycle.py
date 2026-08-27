"""the loading plan becomes a record: status, cut-off, document, typed quantities

Revision ID: 441_loading_plan_lifecycle
Revises: 438_merge_price_supplier_sets
Create Date: 2026-08-28

`PLAN-scm-fulfilment-feedback-p4.md` R1. A container plan was React state on one page: leave
it and it was gone, two people could not see the same one, and there was nothing to cancel,
delete or reopen. It becomes a row in the table that already exists for it - `scm.loading_plan`,
which `supplier_notices.loading_plan_id` already points at.

The stage-2 CBM columns (`container_cbm`, `capacity_cbm`) are relaxed to NULL rather than
dropped: they are still written by `loading_plan_service.build`, and a plan started from a
stock list simply has no container chosen yet, because the supplier decides that when they
pack.

No backfill body is needed. Every added column carries a server default, so the rows already
in the table read `planning` / `none` / `{}` - which is exactly what they are: plans nobody
ever sent, from before the lifecycle existed.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "441_loading_plan_lifecycle"
down_revision = "438_merge_price_supplier_sets"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("status", sa.Column("status", sa.String(20), nullable=False, server_default="planning")),
    ("plan_horizon_date", sa.Column("plan_horizon_date", sa.Date(), nullable=True)),
    (
        "document_kind",
        sa.Column("document_kind", sa.String(20), nullable=False, server_default="none"),
    ),
    (
        "source_attachment_id",
        sa.Column("source_attachment_id", postgresql.UUID(as_uuid=False), nullable=True),
    ),
    (
        "line_edits",
        sa.Column(
            "line_edits",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    ),
    ("to_request_qty", sa.Column("to_request_qty", sa.Numeric(), nullable=True)),
    ("to_request_cbm", sa.Column("to_request_cbm", sa.Numeric(), nullable=True)),
    ("sent_at", sa.Column("sent_at", sa.DateTime(timezone=False), nullable=True)),
    ("cancelled_at", sa.Column("cancelled_at", sa.DateTime(timezone=False), nullable=True)),
    ("cancelled_by", sa.Column("cancelled_by", sa.String(), nullable=True)),
)


def _existing(bind) -> set[str]:
    return {
        r[0]
        for r in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'scm' AND table_name = 'loading_plan'"
            )
        )
    }


def upgrade() -> None:
    bind = op.get_bind()
    have = _existing(bind)
    # Idempotent: the shared local database converges through `create_all`, so the model's
    # columns can already be there before this body ever runs (see the backend CLAUDE.md).
    for name, column in _COLUMNS:
        if name not in have:
            op.add_column("loading_plan", column, schema="scm")

    op.alter_column("loading_plan", "container_cbm", nullable=True, schema="scm")
    op.alter_column("loading_plan", "capacity_cbm", nullable=True, schema="scm")

    # The list reads one page of one status, newest first, and nothing else.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scm_loading_plan_status_created "
        "ON scm.loading_plan (status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS scm.ix_scm_loading_plan_status_created")
    for name, _column in _COLUMNS:
        op.drop_column("loading_plan", name, schema="scm")
    # Left nullable: rows written while the lifecycle existed have no container volume, so
    # restoring NOT NULL would refuse to run.
