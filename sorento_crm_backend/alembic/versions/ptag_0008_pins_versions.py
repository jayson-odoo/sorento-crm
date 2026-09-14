"""r9 S5: the product data pin, its ack, and the pins a version carries.

Master data resolved live on every render (ADR 0008) meant a price edited on
Tuesday silently rewrote the proof approved on Monday. The data is pinned when
designing starts, and this revision adds the three columns that hold it plus
the version-side snapshot Restore needs.

``backfill_pins`` is a NAMED function called from ``upgrade()`` for the same
reason S3's two steps are: ``blank_session`` builds the schema from the models,
so a data step is only testable by importing the revision and calling it.

Revision ID: ptag_0008_pins_versions
Revises: ptag_0007_print_collection
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "ptag_0008_pins_versions"
down_revision = "ptag_0007_print_collection"
branch_labels = None
depends_on = None

#: Statuses with nothing left to decide. A pin on one of these is dead weight:
#: the gate never asks about a request nobody can act on.
_TERMINAL = ("collected", "rejected", "void", "ready")


def backfill_pins(bind) -> int:
    """Pin every line of every request that is still live (D16).

    Without this, an existing request in mid-design has no pin, so the gate has
    nothing to compare against and the first product edit walks onto the tag
    exactly as it did before. Pinning what the resolver answers TODAY means
    nothing changes visually on day one, which is the point.

    Deliberately a light pin: the code, name and the two prices the resolver
    would answer, read straight from the product row. The full resolve runs in
    the service and needs the app's own scope machinery, which a migration does
    not have - and the first Update replaces the pin with a full one anyway.

    Returns how many lines were pinned.
    """
    rows = bind.execute(
        text(
            """
            SELECT l.id,
                   p.product_code,
                   p.product_name,
                   p.list_price,
                   p.barcode
            FROM price_tag_request_lines l
            JOIN price_tag_requests r ON r.id = l.request_id
            LEFT JOIN products p ON p.id = l.product_id
            WHERE l.pinned_tag_data IS NULL
              AND r.status NOT IN :terminal
            """
        ).bindparams(sa.bindparam("terminal", expanding=True)),
        {"terminal": list(_TERMINAL)},
    ).fetchall()

    pinned = 0
    for line_id, code, name, list_price, barcode in rows:
        payload = {
            "line_id": str(line_id),
            "code": code or "",
            "name": name or "",
            "dimensions": "",
            "spec_lines": "",
            "specs": [],
            "set_members": "",
            "images": [],
            "list_price": float(list_price) if list_price is not None else None,
            "sell_price": None,
            "barcode": barcode,
        }
        bind.execute(
            text(
                """
                UPDATE price_tag_request_lines
                SET pinned_tag_data = CAST(:payload AS jsonb),
                    pinned_at = now() AT TIME ZONE 'utc'
                WHERE id = :line_id
                """
            ),
            {"payload": json.dumps(payload), "line_id": str(line_id)},
        )
        pinned += 1
    return pinned


def upgrade() -> None:
    op.add_column(
        "price_tag_request_lines",
        sa.Column("pinned_tag_data", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "price_tag_request_lines",
        sa.Column("pinned_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "price_tag_request_lines",
        sa.Column("data_change_ack_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "page_version",
        sa.Column("pinned_line_data", postgresql.JSONB(), nullable=True),
        schema="dealer_kit",
    )

    backfill_pins(op.get_bind())


def downgrade() -> None:
    op.drop_column("page_version", "pinned_line_data", schema="dealer_kit")
    op.drop_column("price_tag_request_lines", "data_change_ack_hash")
    op.drop_column("price_tag_request_lines", "pinned_at")
    op.drop_column("price_tag_request_lines", "pinned_tag_data")
