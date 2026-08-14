"""Dealer Kit export requests - the viewer context a PDF was asked for with.

``user_downloads`` deliberately has no params column: it is a generic "a file is
being made for you" row shared by every export in the system. A catalogue PDF
needs more than that. It has to be rendered AS SOMEBODY - a dealer's copy and a
consumer's copy of the same page carry different prices - and that decision is
made when the export is REQUESTED, not when the worker happens to run it.

So the request snapshot lives here, one row per download, holding exactly the
inputs a render needs to be reproducible: which page, which version, and who it
is for. The worker reads this and never has to guess, which is what stops it
falling back to a system principal and quietly rendering staff prices into a
document a consumer asked for.

The version id is pinned at enqueue too. Publishing again while a PDF is
queued must not change what that PDF contains.

Numbered 311 rather than 310: another branch already holds 310, and colliding
revision ids is a merge conflict that only shows up at deploy time.

Revision ID: 311_dealer_kit_export_request
Revises: 309_dealer_kit_module
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "311_dealer_kit_export_request"
down_revision = "309_dealer_kit_module"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"
TABLE = "export_request"


def _exists(conn) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = :t"
            ),
            {"s": SCHEMA, "t": TABLE},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))

    # Guarded like migration 309: this branch's schema may already have been
    # built by create_all on a legacy install.
    if _exists(conn):
        return

    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        # The download this request belongs to. Deleting the download takes the
        # snapshot with it - it has no meaning on its own.
        sa.Column("download_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=False), nullable=False),
        # Pinned at enqueue: publishing again while a PDF is queued must not
        # change what that PDF contains.
        sa.Column("page_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        # WHO the render is for. Not the requester's identity - the audience.
        sa.Column("audience", sa.String(20), nullable=False, server_default="staff"),
        sa.Column(
            "show_invoice_price",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("requested_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["download_id"], ["user_downloads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["page_id"], [f"{SCHEMA}.page.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["page_version_id"], [f"{SCHEMA}.page_version.id"], ondelete="CASCADE"
        ),
        # One snapshot per download. A second would mean two answers to "who is
        # this for", and nothing could say which the worker should believe.
        sa.UniqueConstraint("download_id", name="uq_dealer_kit_export_request_download"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_export_request_page_id", TABLE, ["page_id"], schema=SCHEMA
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not _exists(conn):
        return
    op.drop_index("ix_dealer_kit_export_request_page_id", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
